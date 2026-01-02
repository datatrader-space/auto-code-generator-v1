<template>
  <div class="agent-runner">
    <div class="header">
      <h3>🤖 Autonomous Agent Runner</h3>
      <div v-if="isRunning" class="status-badge running">
        <span class="pulse">●</span> Running
      </div>
      <div v-else class="status-badge idle">
        ● Idle
      </div>
    </div>

    <!-- Agent Feed -->
    <div class="agent-feed" ref="feed">
      <div v-if="events.length === 0" class="empty-feed">
        <div class="icon">✨</div>
        <p>Ready to work. Describe a task below.</p>
      </div>
      
      <div v-for="event in events" :key="event.id" class="feed-item" :class="event.type">
        <!-- Planning Phase -->
        <div v-if="event.type === 'plan'" class="event-card plan">
          <div class="event-icon">📝</div>
          <div class="event-content">
            <strong>Plan Created:</strong>
            <pre>{{ event.data.plan }}</pre>
          </div>
        </div>

        <!-- Tool Execution -->
        <div v-if="event.type === 'tool_call'" class="event-card tool">
          <div class="event-icon">🛠️</div>
          <div class="event-content">
            <strong>Using Tool:</strong> {{ event.data.tool }}
            <div class="tool-params">{{ event.data.params }}</div>
          </div>
        </div>

        <!-- Reasoning/Thought -->
        <div v-if="event.type === 'thought'" class="event-card thought">
          <div class="event-icon">🤔</div>
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
        Agent is thinking...
      </div>
    </div>

    <!-- Input Area -->
    <div class="input-area">
      <textarea
        v-model="userRequest"
        placeholder="Describe a task (e.g., 'Refactor the login view to use class-based views')"
        :disabled="isRunning"
        @keydown.enter.prevent="startAgent"
      ></textarea>
      <button 
        @click="startAgent" 
        :disabled="isRunning || !userRequest.trim()"
        class="run-btn"
      >
        {{ isRunning ? 'Running...' : 'Run Agent' }}
      </button>
    </div>
  </div>
</template>

<script>
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
      events: [],
      ws: null,
      sessionId: null
    }
  },
  mounted() {
    this.connectWebSocket()
  },
  beforeUnmount() {
    if (this.ws) {
      this.ws.close()
    }
  },
  methods: {
    connectWebSocket() {
      const wsUrl = `ws://localhost:8000/ws/agent/${this.repositoryId}/`
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
    
    startAgent() {
        if (!this.userRequest.trim()) return
        
        this.isRunning = true
        this.events = [] // Clear previous run
        
        this.ws.send(JSON.stringify({
            type: 'execute',
            request: this.userRequest
        }))
    },
    
    handleEvent(data) {
        if (data.type === 'agent_session_created') {
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
}

.header {
  padding: 16px 20px;
  border-bottom: 1px solid #e5e7eb;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.header h3 {
  margin: 0;
  font-size: 1.1rem;
  color: #111827;
}

.status-badge {
  font-size: 0.875rem;
  padding: 4px 12px;
  border-radius: 9999px;
  font-weight: 500;
  display: flex;
  align-items: center;
  gap: 6px;
}

.status-badge.running {
  background: #ecfdf5;
  color: #059669;
}

.status-badge.idle {
  background: #f3f4f6;
  color: #6b7280;
}

.pulse {
  animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: .5; }
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

.empty-feed .icon {
  font-size: 3rem;
  margin-bottom: 1rem;
}

.feed-item {
  margin-bottom: 16px;
}

.event-card {
  background: white;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 12px;
  display: flex;
  gap: 12px;
}

.plan { border-left: 4px solid #3b82f6; }
.tool { border-left: 4px solid #f59e0b; }
.thought { border-left: 4px solid #8b5cf6; }
.success { border-left: 4px solid #10b981; background: #ecfdf5; }
.error { border-left: 4px solid #ef4444; background: #fef2f2; }

.event-icon {
  font-size: 1.25rem;
}

.event-content {
  flex: 1;
  font-size: 0.95rem;
  line-height: 1.5;
}

.tool-params {
  font-family: monospace;
  background: #f3f4f6;
  padding: 4px 8px;
  border-radius: 4px;
  margin-top: 4px;
  font-size: 0.85rem;
  white-space: pre-wrap;
}

pre {
  background: #f3f4f6;
  padding: 8px;
  border-radius: 4px;
  overflow-x: auto;
  margin-top: 6px;
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
</style>
