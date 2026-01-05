<template>
  <div class="agent-runner">
    <div class="header">
      <div class="header-left">
        <h3>🤖 Autonomous Agent Runner</h3>
        <div v-if="isValidating" class="status-badge validating">
           Validating...
        </div>
        <div v-else-if="isRunning" class="status-badge running">
          <span class="pulse">●</span> Running
        </div>
        <div v-else class="status-badge idle">
          ● Idle
        </div>
      </div>
      <div class="header-right">
        <button class="icon-btn" @click="toggleFilePanel" title="Context Files">
            📎 {{ contextFiles.length }}
        </button>
      </div>
    </div>

    <!-- File Context Panel -->
    <div v-if="showFilePanel" class="file-panel">
        <h4>Context Files</h4>
        <div class="file-list">
            <div v-for="file in contextFiles" :key="file.id" class="file-item">
                <span class="file-name">{{ file.name }}</span>
                <button @click="removeFile(file.id)" class="remove-btn">×</button>
            </div>
            <div v-if="contextFiles.length === 0" class="no-files">
                No context files uploaded.
            </div>
        </div>
        <div class="upload-area">
            <input 
                type="file" 
                multiple 
                @change="handleFileUpload" 
                ref="fileInput"
                style="display: none"
            />
            <button @click="$refs.fileInput.click()" class="upload-btn">
                + Upload Files
            </button>
        </div>
    </div>

    <!-- Agent Feed -->
    <div class="agent-feed" ref="feed">
      <div v-if="events.length === 0" class="empty-feed">
        <div class="icon">✨</div>
        <p>Ready to work. Chat or describe a task below.</p>
        <div class="context-hint">
            Upload files to provide context.
        </div>
      </div>
      
      <div v-for="event in events" :key="event.id" class="feed-item" :class="event.type">
        <!-- User Message -->
        <div v-if="event.type === 'user'" class="message-card user">
            <div class="message-content">{{ event.content }}</div>
        </div>

        <!-- Assistant Message -->
        <div v-if="event.type === 'assistant'" class="message-card assistant">
            <div class="message-content" v-html="formatMarkdown(event.content)"></div>
        </div>

        <!-- Planning Phase -->
        <div v-if="event.type === 'plan'" class="event-card plan">
          <div class="event-title">📝 Plan Created</div>
          <div class="event-content">
            <pre>{{ event.data.plan }}</pre>
          </div>
        </div>

        <!-- Tool Execution -->
        <div v-if="event.type === 'tool_call'" class="event-card tool">
          <div class="event-title">🛠️ Using Tool: {{ event.data.tool }}</div>
          <div class="event-content">
            <div class="tool-params">{{ event.data.params }}</div>
          </div>
        </div>

        <!-- Tool Result -->
        <div v-if="event.type === 'tool_result'" class="event-card tool-result">
            <div class="event-title">📄 Tool Result: {{ event.data.tool_name }}</div>
            <div class="event-content">
                <pre class="result-preview">{{ formatToolResult(event.data.result) }}</pre>
            </div>
        </div>

        <!-- Reasoning/Thought -->
        <div v-if="event.type === 'thought'" class="event-card thought">
          <div class="event-title">🤔 Thinking</div>
          <div class="event-content">
            {{ event.data.content }}
          </div>
        </div>
        
        <!-- Error -->
        <div v-if="event.type === 'error'" class="event-card error">
          <div class="event-icon">❌</div>
          <div class="event-content">
            {{ event.data.message }}
          </div>
        </div>

        <!-- Success -->
        <div v-if="event.type === 'success'" class="event-card success">
          <div class="event-icon">✅</div>
          <div class="event-content">
            <strong>Task Complete!</strong>
            <p>{{ event.data.summary }}</p>
          </div>
        </div>
      </div>
      
      <div v-if="isRunning" class="typing-indicator">
        <span class="dot">.</span><span class="dot">.</span><span class="dot">.</span>
      </div>
    </div>

    <!-- Input Area -->
    <div class="input-area">
      <textarea
        v-model="userRequest"
        placeholder="Chat or describe a task..."
        :disabled="isRunning"
        @keydown.enter.prevent="sendMessage"
      ></textarea>
      <button 
        @click="sendMessage" 
        :disabled="isRunning || !userRequest.trim()"
        class="run-btn"
      >
        {{ isRunning ? 'Stop' : 'Send' }}
      </button>
    </div>
  </div>
</template>

<script>
import { marked } from 'marked'
import api from '../services/api'

export default {
  name: 'AgentRunnerDashboard',
  props: {
    repositoryId: {
      type: Number,
      required: true
    }
  },
  data() {
    return {
      userRequest: '',
      isRunning: false,
      isValidating: false,
      events: [],
      ws: null,
      sessionId: null,
      conversationId: null, // Track conversation ID
      contextFiles: [],
      showFilePanel: false,
      currentAssistantMessage: '', // For streaming
    }
  },
  async mounted() {
    this.connectWebSocket()
    
    // Try to load latest conversation
    try {
        const res = await api.getConversations({ repository: this.repositoryId })
        if (res.data.results && res.data.results.length > 0) {
            this.conversationId = res.data.results[0].id
            this.loadContextFiles()
        }
    } catch (e) {
        console.error("Failed to load conversations", e)
    }
  },
  beforeUnmount() {
    if (this.ws) {
      this.ws.close()
    }
  },
  methods: {
    formatMarkdown(text) {
        return marked(text || '')
    },
    formatToolResult(result) {
        if (typeof result === 'object') return JSON.stringify(result, null, 2)
        return result
    },
    toggleFilePanel() {
        this.showFilePanel = !this.showFilePanel
    },
    async loadContextFiles() {
        if (!this.conversationId) return
        try {
            const response = await api.getContextFiles(this.conversationId)
            this.contextFiles = response.data
        } catch (e) {
            console.error('Failed to load context files', e)
        }
    },
    async handleFileUpload(event) {
        const files = event.target.files
        if (!files.length) return

        this.isValidating = true // reuse badge for "Uploading" state conceptually
        
        try {
            // Create conversation if not exists
            if (!this.conversationId) {
                 const res = await api.createConversation({
                    repository_id: this.repositoryId,
                    title: 'Agent Chat'
                })
                this.conversationId = res.data.id
            }

            for (let i = 0; i < files.length; i++) {
                await api.uploadContextFile(this.conversationId, files[i])
            }
            await this.loadContextFiles()
        } catch (e) {
            this.addEvent({
                type: 'error',
                data: { message: 'Failed to upload files: ' + e.message }
            })
        } finally {
            this.isValidating = false
            // Reset input
            this.$refs.fileInput.value = null
        }
    },
    async removeFile(fileId) {
         if (!this.conversationId) return
         try {
             await api.deleteContextFile(this.conversationId, fileId)
             await this.loadContextFiles()
         } catch (e) {
             console.error('Failed to remove file', e)
         }
    },

    connectWebSocket() {
      // Changed to Repository Chat URL
      const wsUrl = `ws://localhost:8000/ws/chat/repository/${this.repositoryId}/`
      this.ws = new WebSocket(wsUrl)
      
      this.ws.onopen = () => {
        console.log('Agent WebSocket connected')
      }
      
      this.ws.onmessage = (e) => {
        const data = JSON.parse(e.data)
        this.handleEvent(data)
      }
      
      this.ws.onerror = (err) => {
        console.error('Agent WebSocket error:', err)
        this.addEvent({
            type: 'error',
            data: { message: 'Connection error. Please refresh.' }
        })
      }
    },
    
    sendMessage() {
        if (this.isRunning) {
            // TODO: Implement stop logic if needed
            return
        }
        if (!this.userRequest.trim()) return
        
        const message = this.userRequest
        this.userRequest = '' // Clear input immediately
        this.isRunning = true
        
        // Add user message to feed immediately
        this.addEvent({
            type: 'user',
            content: message
        })

        // Prepare payload - include conversation_id if we have one
        const payload = {
            type: 'chat_message',
            message: message,
            conversation_id: this.conversationId
        }

        this.ws.send(JSON.stringify(payload))
    },
    
    handleEvent(data) {
        // --- CHAT EVENTS ---
        if (data.type === 'conversation_created') {
            this.conversationId = data.conversation_id
            this.loadContextFiles() // Load files for this conversation
        }
        else if (data.type === 'assistant_typing') {
            // Already handled by isRunning mostly, but could show specific indicator
        }
        else if (data.type === 'assistant_message_chunk') {
             // Basic streaming handling: update last event if it's assistant, or add new
             if (this.events.length > 0 && this.events[this.events.length - 1].type === 'assistant') {
                 this.events[this.events.length - 1].content += data.chunk
             } else {
                 this.addEvent({
                     type: 'assistant',
                     content: data.chunk
                 })
             }
        }
        else if (data.type === 'assistant_message_complete') {
             this.isRunning = false
             // Ensure we have the full message
             if (this.events.length > 0 && this.events[this.events.length - 1].type === 'assistant') {
                 this.events[this.events.length - 1].content = data.full_message
             } else {
                 this.addEvent({
                     type: 'assistant',
                     content: data.full_message
                 })
             }
        }
        else if (data.type === 'tool_result') {
            this.addEvent({
                type: 'tool_result',
                data: { 
                    tool_name: data.tool_name,
                    result: data.result 
                }
            })
        }

        // --- AGENT RUNNER EVENTS (Backward Compatibility) ---
        else if (data.type === 'agent_session_created') {
            this.sessionId = data.session_id
            this.addEvent({
                type: 'thought',
                data: { content: `Session started: ${this.sessionId}` }
            })
        }
        else if (data.type === 'agent_plan') {
            this.addEvent({
                type: 'plan',
                data: { plan: data.plan }
            })
        }
        else if (data.type === 'agent_step') {
            this.addEvent({
                type: 'thought',
                data: { content: data.thought }
            })
            if (data.tool) {
                this.addEvent({
                    type: 'tool_call',
                    data: { tool: data.tool, params: data.tool_input }
                })
            }
        }
        else if (data.type === 'agent_complete') {
            this.isRunning = false
            this.addEvent({
                type: 'success',
                data: { summary: data.summary }
            })
        }
        else if (data.type === 'agent_error' || data.type === 'agent_session_error') {
            this.isRunning = false
            this.addEvent({
                type: 'error',
                data: { message: data.error }
            })
        }
        else if (data.type === 'error') {
             this.isRunning = false
             this.addEvent({
                type: 'error',
                data: { message: data.error }
            })
        }
        
        // Auto-scroll
        this.$nextTick(() => {
            const feed = this.$refs.feed
            if (feed) feed.scrollTop = feed.scrollHeight
        })
    },
    
    addEvent(event) {
        this.events.push({
            id: Date.now() + Math.random(),
            ...event
        })
    }
  }
}
</script>

<style scoped>
.agent-runner {
  background: white;
  border-radius: 8px;
  box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
  display: flex;
  flex-direction: column;
  height: 600px;
  position: relative;
}

.header {
  padding: 16px 20px;
  border-bottom: 1px solid #e5e7eb;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.header-left {
    display: flex;
    align-items: center;
    gap: 12px;
}

.header h3 {
  margin: 0;
  font-size: 1.1rem;
  color: #111827;
}

.icon-btn {
    background: none;
    border: 1px solid #e5e7eb;
    border-radius: 6px;
    padding: 6px 10px;
    cursor: pointer;
    font-size: 0.9rem;
    color: #4b5563;
}
.icon-btn:hover {
    background: #f9fafb;
    color: #111827;
}

.status-badge {
  font-size: 0.75rem;
  padding: 2px 8px;
  border-radius: 9999px;
  font-weight: 500;
  display: flex;
  align-items: center;
  gap: 4px;
}

.status-badge.running { background: #ecfdf5; color: #059669; }
.status-badge.idle { background: #f3f4f6; color: #6b7280; }
.status-badge.validating { background: #eff6ff; color: #2563eb; }

.pulse {
  animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: .5; }
}

.file-panel {
    background: #f9fafb;
    border-bottom: 1px solid #e5e7eb;
    padding: 12px;
    max-height: 150px;
    overflow-y: auto;
}
.file-panel h4 {
    margin: 0 0 8px 0;
    font-size: 0.85rem;
    color: #6b7280;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}
.file-list {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-bottom: 8px;
}
.file-item {
    background: white;
    border: 1px solid #e5e7eb;
    border-radius: 4px;
    padding: 4px 8px;
    font-size: 0.85rem;
    display: flex;
    align-items: center;
    gap: 6px;
}
.remove-btn {
    border: none;
    background: none;
    color: #ef4444;
    cursor: pointer;
    font-weight: bold;
    padding: 0;
}
.upload-btn {
    background: white;
    border: 1px dashed #d1d5db;
    border-radius: 4px;
    padding: 4px 8px;
    font-size: 0.85rem;
    color: #4b5563;
    cursor: pointer;
}
.upload-btn:hover {
    border-color: #3b82f6;
    color: #3b82f6;
}

.agent-feed {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
  background: #f9fafb;
}

.empty-feed {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #9ca3af;
}

.empty-feed .icon { font-size: 3rem; margin-bottom: 1rem; }
.context-hint { margin-top: 1rem; font-size: 0.85rem; color: #6b7280; }

.feed-item { margin-bottom: 16px; width: 100%; }

.message-card {
    padding: 12px 16px;
    border-radius: 12px;
    max-width: 85%;
    line-height: 1.5;
    font-size: 0.95rem;
}
.message-card.user {
    background: #3b82f6;
    color: white;
    margin-left: auto;
    border-bottom-right-radius: 4px;
}
.message-card.assistant {
    background: white;
    border: 1px solid #e5e7eb;
    margin-right: auto;
    border-bottom-left-radius: 4px;
}

.event-card {
  background: white;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 10px;
  margin: 8px 0;
  font-size: 0.9rem;
}

.event-title {
    font-weight: 600;
    margin-bottom: 6px;
    color: #4b5563;
    font-size: 0.85rem;
}

.plan { border-left: 3px solid #3b82f6; }
.tool { border-left: 3px solid #f59e0b; }
.tool-result { border-left: 3px solid #8b5cf6; background: #fdfbff; }
.thought { border-left: 3px solid #8b5cf6; background: #fdfbff; }
.success { border-left: 3px solid #10b981; background: #ecfdf5; }
.error { border-left: 3px solid #ef4444; background: #fef2f2; }

.result-preview {
    max-height: 200px;
    overflow-y: auto;
    font-size: 0.8rem;
    background: #f3f4f6;
    padding: 8px;
    border-radius: 4px;
}

.tool-params {
  font-family: monospace;
  background: #f3f4f6;
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 0.85rem;
  white-space: pre-wrap;
}

pre {
  background: #f3f4f6;
  padding: 8px;
  border-radius: 4px;
  overflow-x: auto;
  margin: 0;
  font-size: 0.85rem;
}

.input-area {
  padding: 16px;
  border-top: 1px solid #e5e7eb;
  display: flex;
  gap: 12px;
  background: white;
  border-bottom-left-radius: 8px;
  border-bottom-right-radius: 8px;
}

textarea {
  flex: 1;
  padding: 10px;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  resize: none;
  height: 60px;
  font-family: inherit;
}

textarea:focus {
  outline: none;
  border-color: #3b82f6;
  ring: 2px solid #3b82f6;
}

.run-btn {
  padding: 0 24px;
  background: #3b82f6;
  color: white;
  border: none;
  border-radius: 6px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s;
}

.run-btn:hover:not(:disabled) {
  background: #2563eb;
}

.run-btn:disabled {
  background: #9ca3af;
  cursor: not-allowed;
}

.typing-indicator {
    padding: 8px 16px;
    color: #6b7280;
}
.dot {
    animation: bounce 1.4s infinite ease-in-out both;
}
.dot:nth-child(1) { animation-delay: -0.32s; }
.dot:nth-child(2) { animation-delay: -0.16s; }
@keyframes bounce {
    0%, 80%, 100% { transform: scale(0); }
    40% { transform: scale(1); }
}
</style>
