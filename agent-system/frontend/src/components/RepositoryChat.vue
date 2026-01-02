<template>
  <div class="repository-chat">
    <!-- Chat Header -->
    <div v-if="!hideHeader" class="chat-header">
      <div class="flex items-center justify-between">
        <div>
          <h3 class="font-semibold text-gray-900">{{ repository.name }}</h3>
          <p class="text-xs text-gray-500">Repository Chat</p>
        </div>
        <div class="flex items-center gap-2">
          <select
            v-model="selectedModelId"
            class="text-xs border rounded px-2 py-1 text-gray-600"
          >
            <option :value="null">Default Model</option>
            <option
              v-for="model in activeModels"
              :key="model.id"
              :value="model.id"
            >
              {{ model.provider_name }} • {{ model.name }}
            </option>
          </select>
          <!-- Connection Status -->
          <div v-if="connected" class="flex items-center text-xs text-green-600">
            <span class="w-2 h-2 bg-green-500 rounded-full mr-1"></span>
            Connected
          </div>
          <div v-else class="flex items-center text-xs text-gray-400">
            <span class="w-2 h-2 bg-gray-300 rounded-full mr-1"></span>
            Disconnected
          </div>

          <!-- Clear Chat -->
          <button
            @click="clearMessages"
            class="text-xs text-gray-500 hover:text-gray-700"
          >
            Clear
          </button>
        </div>
      </div>
    </div>

    <!-- Messages Container -->
    <div ref="messagesContainer" class="messages-container">
      <!-- Welcome Message -->
      <div v-if="messages.length === 0" class="welcome-message">
        <div class="text-center py-8">
          <svg class="w-12 h-12 mx-auto text-gray-300 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
          </svg>
          <p class="text-gray-500 font-medium">Ask me about this repository</p>
          <p class="text-xs text-gray-400 mt-1">I have access to all code, artifacts, and relationships</p>
        </div>
      </div>

      <!-- Message List -->
      <div
        v-for="(message, index) in messages"
        :key="index"
        :class="['message', `message-${message.role}`]"
      >
        <!-- User Message -->
        <div v-if="message.role === 'user'" class="message-content user-message">
          <div class="message-bubble">
            {{ message.content }}
          </div>
        </div>

        <!-- Assistant Message -->
        <div v-else-if="message.role === 'assistant'" class="message-content assistant-message">
          <div class="flex items-start gap-2 w-full">
            <div class="assistant-avatar">
              <svg class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                <path d="M2 5a2 2 0 012-2h7a2 2 0 012 2v4a2 2 0 01-2 2H9l-3 3v-3H4a2 2 0 01-2-2V5z" />
                <path d="M15 7v2a4 4 0 01-4 4H9.828l-1.766 1.767c.28.149.599.233.938.233h2l3 3v-3h2a2 2 0 002-2V9a2 2 0 00-2-2h-1z" />
              </svg>
            </div>
            <div class="flex-1">
              <div class="message-bubble">
                <div v-html="formatMessage(message.content)"></div>
              </div>

              <!-- Trace Information -->
              <div v-if="message.trace && message.trace.length > 0" class="mt-2 text-xs">
                <details class="trace-details">
                  <summary class="cursor-pointer text-gray-500 hover:text-gray-700">
                    🔍 View trace ({{ message.trace.length }} steps)
                  </summary>
                  <div class="trace-content mt-2 space-y-1">
                    <div
                      v-for="(step, idx) in message.trace"
                      :key="idx"
                      class="text-gray-600 font-mono"
                    >
                      {{ step }}
                    </div>
                  </div>
                </details>
              </div>

              <!-- Tool Results -->
              <div v-if="message.toolResults && message.toolResults.length > 0" class="mt-2">
                <details class="tool-results-details">
                  <summary class="cursor-pointer text-xs text-gray-500 hover:text-gray-700">
                    🔧 Tool calls ({{ message.toolResults.length }})
                  </summary>
                  <div class="tool-results-content mt-2 space-y-2">
                    <div
                      v-for="(toolResult, idx) in message.toolResults"
                      :key="idx"
                      class="tool-result-item"
                    >
                      <div class="font-semibold text-xs text-blue-600">{{ toolResult.tool }}</div>
                      <pre class="text-xs bg-gray-50 p-2 rounded mt-1 overflow-x-auto">{{ toolResult.result }}</pre>
                    </div>
                  </div>
                </details>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Typing Indicator -->
      <div v-if="isTyping" class="message message-assistant">
        <div class="message-content assistant-message">
          <div class="flex items-start gap-2">
            <div class="assistant-avatar">
              <svg class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                <path d="M2 5a2 2 0 012-2h7a2 2 0 012 2v4a2 2 0 01-2 2H9l-3 3v-3H4a2 2 0 01-2-2V5z" />
              </svg>
            </div>
            <div class="typing-indicator">
              <span></span>
              <span></span>
              <span></span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Input Container -->
    <div class="input-container">
      <!-- Model Selector -->
      <div class="flex items-center justify-between mb-2 px-1">
        <div class="flex items-center gap-2">
          <svg class="w-3.5 h-3.5 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19.428 15.428a2 2 0 00-1.022-.547l-2.384-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z" /></svg>
          <select 
            v-model="selectedModelId" 
            class="text-xs border-none bg-transparent font-medium text-gray-600 hover:text-gray-900 focus:ring-0 cursor-pointer transition-colors outline-none pr-2 py-0"
          >
              <option :value="null">Default Model</option>
              <option v-for="model in activeModels" :key="model.id" :value="model.id">
                  {{ model.provider_name }} • {{ model.name }}
              </option>
          </select>
        </div>
      </div>

      <form @submit.prevent="sendMessage" class="flex gap-2">
        <textarea
          ref="messageInput"
          v-model="currentMessage"
          @keydown.enter.exact.prevent="sendMessage"
          @keydown.enter.shift.exact="currentMessage += '\n'"
          placeholder="Ask a question..."
          class="message-input shadow-sm bg-white"
          rows="3"
          :disabled="!connected || isTyping"
        ></textarea>
        <button
          type="submit"
          :disabled="!currentMessage.trim() || !connected || isTyping"
          class="send-button"
        >
          <svg v-if="!isTyping" class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
          </svg>
          <svg v-else class="w-5 h-5 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
        </button>
      </form>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import api from '../services/api'
import { Marked } from 'marked'
import { markedHighlight } from 'marked-highlight'
import hljs from 'highlight.js'
import 'highlight.js/styles/atom-one-dark.css'

const marked = new Marked(
  markedHighlight({
    langPrefix: 'hljs language-',
    highlight(code, lang) {
      const language = hljs.getLanguage(lang) ? lang : 'plaintext'
      return hljs.highlight(code, { language }).value
    }
  })
)

const props = defineProps({
  repository: {
    type: Object,
    required: true
  },
  systemId: {
    type: Number,
    required: true
  },
  hideHeader: {
    type: Boolean,
    default: false
  }
})

// State
const messages = ref([])
const currentMessage = ref('')
const isTyping = ref(false)
const connected = ref(false)
const messagesContainer = ref(null)
const messageInput = ref(null)
const conversationId = ref(null)
const loadingHistory = ref(false)
const models = ref([])
const selectedModelId = ref(null)

let ws = null
let currentStreamingMessage = ''
let wsRepositoryId = null
let isConnecting = false
let autoReconnect = true
let reconnectTimeout = null
let incomingMessageCounter = 0

// Load conversation history
const loadConversationHistory = async () => {
  try {
    loadingHistory.value = true
    messages.value = []
    const response = await api.get(`/conversations/?repository=${props.repository.id}&type=repository`)
    const latestConv = response.data.results && response.data.results.length > 0
      ? response.data.results[0]
      : null

    if (!latestConv) {
      conversationId.value = null
      console.log('No conversation history found for repository')
      return
    }

    conversationId.value = latestConv.id
    const detailResponse = await api.get(`/conversations/${conversationId.value}/`)
    const historyMessages = detailResponse.data?.messages || []
    selectedModelId.value = detailResponse.data?.llm_model || null

    messages.value = historyMessages.map(msg => ({
      role: msg.role,
      content: msg.content,
      streaming: false
    }))

    if (messages.value.length > 0) {
      await nextTick()
      scrollToBottom()
    }

    console.log(`Loaded conversation ${conversationId.value} with ${historyMessages.length} messages`)
  } catch (error) {
    console.error('Failed to load conversation history:', error)
  } finally {
    loadingHistory.value = false
  }
}

const loadModels = async () => {
  const response = await api.getLlmModels()
  models.value = response.data.results || response.data
}

// WebSocket connection
const connectWebSocket = (repositoryId = props.repository.id) => {
  if (
    ws &&
    (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) &&
    wsRepositoryId === repositoryId
  ) {
    console.log('WebSocket already connected or connecting for repository', repositoryId)
    return
  }

  if (isConnecting) {
    console.log('WebSocket connection already in progress')
    return
  }

  isConnecting = true
  autoReconnect = true
  const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const wsHost = import.meta.env.VITE_WS_HOST || 'localhost:8000'
  const wsUrl = `${wsProtocol}//${wsHost}/ws/chat/repository/${repositoryId}/`

  ws = new WebSocket(wsUrl)
  wsRepositoryId = repositoryId

  ws.onopen = () => {
    connected.value = true
    isConnecting = false
    console.log('WebSocket connected')
  }

  ws.onclose = () => {
    connected.value = false
    isConnecting = false
    ws = null
    console.log('WebSocket disconnected')

    // Attempt reconnection after 3 seconds
    if (autoReconnect) {
      if (reconnectTimeout) {
        clearTimeout(reconnectTimeout)
      }
      reconnectTimeout = setTimeout(() => {
        if (!connected.value) {
          console.log('Attempting to reconnect...')
          connectWebSocket(repositoryId)
        }
      }, 3000)
    }
  }

  ws.onerror = (error) => {
    console.error('WebSocket error:', error)
    isConnecting = false
  }

  ws.onmessage = (event) => {
    try {
      const messageId = `ws-${Date.now()}-${incomingMessageCounter++}`
      console.log('WebSocket message received', { message_id: messageId, data: event.data })
      const data = JSON.parse(event.data)
      handleWebSocketMessage(data)
    } catch (error) {
      console.error('Error parsing WebSocket message:', error)
    }
  }
}

const closeWebSocket = ({ disableReconnect = false } = {}) => new Promise((resolve) => {
  if (!ws) {
    resolve()
    return
  }

  if (reconnectTimeout) {
    clearTimeout(reconnectTimeout)
  }

  if (disableReconnect) {
    autoReconnect = false
  }

  const socket = ws
  const handleClose = () => {
    socket.removeEventListener('close', handleClose)
    resolve()
  }

  socket.addEventListener('close', handleClose)

  if (socket.readyState === WebSocket.CLOSED) {
    handleClose()
    return
  }

  socket.close()
})

const handleWebSocketMessage = (data) => {
  switch (data.type) {
    case 'conversation_created':
      // Store conversation ID for future messages
      conversationId.value = data.conversation_id
      console.log('Conversation created:', conversationId.value)
      break

    case 'assistant_typing':
      isTyping.value = data.typing
      if (data.typing) {
        currentStreamingMessage = ''
      }
      break

    case 'assistant_message_chunk':
      // Append chunk to current streaming message
      currentStreamingMessage += data.chunk

      // Update or create the streaming message
      const lastMessage = messages.value[messages.value.length - 1]
      if (lastMessage && lastMessage.role === 'assistant' && lastMessage.streaming) {
        lastMessage.content = currentStreamingMessage
      } else {
        messages.value.push({
          role: 'assistant',
          content: currentStreamingMessage,
          streaming: true
        })
      }

      scrollToBottom()
      break

    case 'assistant_message_complete':
      // Mark message as complete
      const completedMessage = messages.value[messages.value.length - 1]
      if (completedMessage && completedMessage.streaming) {
        completedMessage.streaming = false
        completedMessage.content = data.full_message
        completedMessage.trace = data.trace || []
      }
      currentStreamingMessage = ''
      break

    case 'tool_result':
      // Store tool results for display
      const lastMsg = messages.value[messages.value.length - 1]
      if (lastMsg && lastMsg.role === 'assistant') {
        if (!lastMsg.toolResults) {
          lastMsg.toolResults = []
        }
        lastMsg.toolResults.push({
          tool: data.tool_name,
          result: data.result
        })
      }
      break

    case 'error':
      console.error('Chat error:', data.error)
      // Show error message
      messages.value.push({
        role: 'system',
        content: `Error: ${data.error}`
      })
      break

    case 'pong':
      // Heartbeat response
      break

    default:
      console.log('Unknown message type:', data.type)
  }
}

const sendMessage = () => {
  if (!currentMessage.value.trim() || !connected.value || isTyping.value) {
    return
  }

  const messageText = currentMessage.value.trim()
  const messageId = `client-${Date.now()}-${Math.random().toString(16).slice(2)}`

  // Add user message to display
  messages.value.push({
    role: 'user',
    content: messageText
  })

  // Send to WebSocket with conversation_id if available
  ws.send(JSON.stringify({
    type: 'chat_message',
    message: messageText,
    conversation_id: conversationId.value,
    model_id: selectedModelId.value,
    message_id: messageId
  }))

  // Clear input
  currentMessage.value = ''

  scrollToBottom()
}

const clearMessages = () => {
  if (confirm('Clear all messages? This cannot be undone.')) {
    messages.value = []
    currentStreamingMessage = ''
  }
}

const scrollToBottom = async () => {
  await nextTick()
  if (messagesContainer.value) {
    messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
  }
}

const formatMessage = (content) => {
  if (!content) return ''
  return marked.parse(content)
}

const activeModels = computed(() => models.value.filter((model) => model.is_active))

// Lifecycle
onMounted(async () => {
  // Load conversation history first
  await loadConversationHistory()
  await loadModels()
  // Then connect WebSocket
  connectWebSocket(props.repository.id)
})

onUnmounted(() => {
  autoReconnect = false
  closeWebSocket({ disableReconnect: true })
})

// Watch for repository changes
watch(() => props.repository.id, async (nextRepositoryId, previousRepositoryId) => {
  if (nextRepositoryId === previousRepositoryId) {
    return
  }
  // Reconnect if repository changes
  await closeWebSocket({ disableReconnect: true })
  messages.value = []
  currentStreamingMessage = ''
  selectedModelId.value = null
  await loadConversationHistory()
  await loadModels()
  connectWebSocket(nextRepositoryId)
})
</script>

<style scoped>
.repository-chat {
  @apply flex flex-col h-full bg-white;
}

.chat-header {
  @apply px-4 py-3 border-b bg-gray-50;
}

.messages-container {
  @apply flex-1 overflow-y-auto p-4 space-y-4;
}

.message {
  @apply w-full;
}

.message-content {
  @apply flex;
}

.user-message {
  @apply justify-end;
}

.assistant-message {
  @apply justify-start;
}

.message-bubble {
  @apply max-w-[80%] rounded-lg px-4 py-2;
}

/* Message Bubbles */
.user-message .message-bubble {
  @apply bg-zinc-800 text-white rounded-2xl rounded-tr-sm px-5 py-3 shadow-sm;
}

.assistant-message .message-bubble {
  @apply bg-transparent text-gray-800 p-0 max-w-full;
}

.assistant-avatar {
  @apply w-8 h-8 rounded-full bg-green-100 text-green-600 flex items-center justify-center flex-shrink-0 mt-1;
}

/* Markdown Content Styling */
:deep(.message-bubble p) {
  @apply mb-3 last:mb-0 leading-relaxed;
}

:deep(.message-bubble ul) {
  @apply mb-3 pl-5 list-disc space-y-1;
}

:deep(.message-bubble ol) {
  @apply mb-3 pl-5 list-decimal space-y-1;
}

:deep(.message-bubble h1),
:deep(.message-bubble h2),
:deep(.message-bubble h3) {
  @apply font-bold text-gray-900 mt-4 mb-2;
}

:deep(.message-bubble h1) { @apply text-xl; }
:deep(.message-bubble h2) { @apply text-lg; }
:deep(.message-bubble h3) { @apply text-base; }

:deep(.message-bubble a) {
  @apply text-blue-600 hover:underline;
}

:deep(.message-bubble blockquote) {
  @apply border-l-4 border-gray-300 pl-4 italic text-gray-600 my-3;
}

:deep(.message-bubble table) {
  @apply w-full border-collapse border border-gray-200 mb-4 text-sm;
}

:deep(.message-bubble th),
:deep(.message-bubble td) {
  @apply border border-gray-200 px-3 py-2 text-left;
}

:deep(.message-bubble th) {
  @apply bg-gray-50 font-semibold text-gray-700;
}

/* Code Formatting */
:deep(code) {
  @apply font-mono text-sm bg-gray-100 text-gray-800 px-1.5 py-0.5 rounded;
}

:deep(pre) {
  @apply bg-[#282c34] text-gray-100 rounded-lg overflow-x-auto my-3 p-0;
}

:deep(pre code) {
  @apply block p-4 bg-transparent text-inherit overflow-x-auto;
}

/* Tool Styling */
.tool-result-item {
  @apply bg-gray-50 border border-gray-200 rounded-lg p-3 my-2 text-xs font-mono overflow-hidden;
}

/* Restored Input Styles */
.typing-indicator {
  @apply flex gap-1 px-4 py-3 bg-gray-100 rounded-lg;
}

.typing-indicator span {
  @apply w-2 h-2 bg-gray-400 rounded-full animate-bounce;
}

.typing-indicator span:nth-child(2) {
  animation-delay: 0.2s;
}

.typing-indicator span:nth-child(3) {
  animation-delay: 0.4s;
}

.input-container {
  @apply px-4 py-3 border-t bg-gray-50;
}

.message-input {
  @apply flex-1 px-3 py-2 border rounded-lg resize-none focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white;
  max-height: 200px;
}

.send-button {
  @apply px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors;
}

.welcome-message {
  @apply text-center;
}

</style>
