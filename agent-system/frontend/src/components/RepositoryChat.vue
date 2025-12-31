<template>
  <div class="repository-chat">
    <!-- Chat Header -->
    <div class="chat-header">
      <div class="flex items-center justify-between">
        <div>
          <h3 class="font-semibold text-gray-900">{{ repository.name }}</h3>
          <p class="text-xs text-gray-500">Repository Chat</p>
        </div>
        <div class="flex items-center gap-2">
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
          <div class="flex items-start gap-2">
            <div class="assistant-avatar">
              <svg class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                <path d="M2 5a2 2 0 012-2h7a2 2 0 012 2v4a2 2 0 01-2 2H9l-3 3v-3H4a2 2 0 01-2-2V5z" />
                <path d="M15 7v2a4 4 0 01-4 4H9.828l-1.766 1.767c.28.149.599.233.938.233h2l3 3v-3h2a2 2 0 002-2V9a2 2 0 00-2-2h-1z" />
              </svg>
            </div>
            <div class="message-bubble">
              <div v-html="formatMessage(message.content)"></div>
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
      <form @submit.prevent="sendMessage" class="flex gap-2">
        <textarea
          ref="messageInput"
          v-model="currentMessage"
          @keydown.enter.exact.prevent="sendMessage"
          @keydown.enter.shift.exact="currentMessage += '\n'"
          placeholder="Ask about this repository... (Shift+Enter for new line)"
          class="message-input"
          rows="1"
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

const props = defineProps({
  repository: {
    type: Object,
    required: true
  },
  systemId: {
    type: Number,
    required: true
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
      }
      currentStreamingMessage = ''
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
  // Basic markdown-like formatting
  let formatted = content
    .replace(/`([^`]+)`/g, '<code class="inline-code">$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\n/g, '<br>')

  // Code blocks
  formatted = formatted.replace(/```(\w+)?\n([\s\S]+?)```/g, (match, lang, code) => {
    return `<pre class="code-block"><code class="language-${lang || 'text'}">${code.trim()}</code></pre>`
  })

  return formatted
}

// Lifecycle
onMounted(async () => {
  // Load conversation history first
  await loadConversationHistory()
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
  await loadConversationHistory()
  connectWebSocket(nextRepositoryId)
})
</script>

<style scoped>
.repository-chat {
  @apply flex flex-col h-full bg-white rounded-lg border;
  height: 600px;
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

.user-message .message-bubble {
  @apply bg-blue-600 text-white;
}

.assistant-message .message-bubble {
  @apply bg-gray-100 text-gray-900;
}

.assistant-avatar {
  @apply w-8 h-8 rounded-full bg-purple-100 text-purple-600 flex items-center justify-center flex-shrink-0;
}

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
  @apply flex-1 px-3 py-2 border rounded-lg resize-none focus:ring-2 focus:ring-blue-500 focus:border-transparent;
  max-height: 120px;
}

.send-button {
  @apply px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors;
}

.welcome-message {
  @apply text-center;
}

/* Code formatting */
:deep(.inline-code) {
  @apply bg-gray-800 text-gray-100 px-1 py-0.5 rounded text-sm font-mono;
}

:deep(.code-block) {
  @apply bg-gray-900 text-gray-100 p-3 rounded-lg overflow-x-auto my-2;
}

:deep(.code-block code) {
  @apply font-mono text-sm;
}

:deep(strong) {
  @apply font-semibold;
}
</style>
