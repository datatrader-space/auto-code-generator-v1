<template>
  <div class="planner-chat">
    <!-- Chat Header -->
    <div class="chat-header">
      <div class="flex items-center justify-between">
        <div>
          <h3 class="font-semibold text-gray-900">System Planner</h3>
          <p class="text-xs text-gray-500">Multi-Repository Planning & Architecture</p>
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

          <!-- Repository Count -->
          <div class="text-xs text-gray-500 px-2 py-1 bg-gray-100 rounded">
            {{ repositoryCount }} repos
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
          <svg class="w-12 h-12 mx-auto text-purple-300 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01" />
          </svg>
          <p class="text-gray-500 font-medium">Plan changes across your system</p>
          <p class="text-xs text-gray-400 mt-1">I have access to all repositories, their code, and relationships</p>
          <div class="mt-4 space-y-2">
            <button
              v-for="suggestion in quickSuggestions"
              :key="suggestion"
              @click="sendQuickMessage(suggestion)"
              class="block mx-auto text-xs text-blue-600 hover:text-blue-800 hover:underline"
            >
              {{ suggestion }}
            </button>
          </div>
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
                <path d="M9 2a1 1 0 000 2h2a1 1 0 100-2H9z" />
                <path fill-rule="evenodd" d="M4 5a2 2 0 012-2 3 3 0 003 3h2a3 3 0 003-3 2 2 0 012 2v11a2 2 0 01-2 2H6a2 2 0 01-2-2V5zm3 4a1 1 0 000 2h.01a1 1 0 100-2H7zm3 0a1 1 0 000 2h3a1 1 0 100-2h-3zm-3 4a1 1 0 100 2h.01a1 1 0 100-2H7zm3 0a1 1 0 100 2h3a1 1 0 100-2h-3z" clip-rule="evenodd" />
              </svg>
            </div>
            <div class="message-bubble">
              <div v-html="formatMessage(message.content)"></div>
            </div>
          </div>
        </div>

        <!-- System Message -->
        <div v-else-if="message.role === 'system'" class="message-content system-message">
          <div class="system-bubble">
            <svg class="w-4 h-4 inline mr-1" fill="currentColor" viewBox="0 0 20 20">
              <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clip-rule="evenodd" />
            </svg>
            {{ message.content }}
          </div>
        </div>
      </div>

      <!-- Typing Indicator -->
      <div v-if="isTyping" class="message message-assistant">
        <div class="message-content assistant-message">
          <div class="flex items-start gap-2">
            <div class="assistant-avatar">
              <svg class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                <path d="M9 2a1 1 0 000 2h2a1 1 0 100-2H9z" />
                <path fill-rule="evenodd" d="M4 5a2 2 0 012-2 3 3 0 003 3h2a3 3 0 003-3 2 2 0 012 2v11a2 2 0 01-2 2H6a2 2 0 01-2-2V5zm3 4a1 1 0 000 2h.01a1 1 0 100-2H7zm3 0a1 1 0 000 2h3a1 1 0 100-2h-3zm-3 4a1 1 0 100 2h.01a1 1 0 100-2H7zm3 0a1 1 0 100 2h3a1 1 0 100-2h-3z" clip-rule="evenodd" />
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
          placeholder="Plan changes across repositories... (Shift+Enter for new line)"
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
  systemId: {
    type: Number,
    required: true
  },
  repositoryCount: {
    type: Number,
    default: 0
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

const quickSuggestions = [
  'What is the overall architecture of this system?',
  'How do these repositories interact with each other?',
  'What would be the impact of changing the authentication system?',
  'Help me plan a new feature across multiple repos'
]

// Load conversation history
const loadConversationHistory = async () => {
  try {
    loadingHistory.value = true
    const response = await api.get(`/conversations/?system=${props.systemId}&type=planner`)

    if (response.data.results && response.data.results.length > 0) {
      const latestConv = response.data.results[0]
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

      console.log(`Loaded planner conversation ${conversationId.value} with ${historyMessages.length} messages`)
    }
  } catch (error) {
    console.error('Failed to load planner conversation history:', error)
  } finally {
    loadingHistory.value = false
  }
}

const loadModels = async () => {
  const response = await api.getLlmModels()
  models.value = response.data.results || response.data
}

// WebSocket connection
const connectWebSocket = () => {
  const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const wsHost = import.meta.env.VITE_WS_HOST || 'localhost:8000'
  const wsUrl = `${wsProtocol}//${wsHost}/ws/chat/planner/${props.systemId}/`

  ws = new WebSocket(wsUrl)

  ws.onopen = () => {
    connected.value = true
    console.log('Planner WebSocket connected')
  }

  ws.onclose = () => {
    connected.value = false
    console.log('Planner WebSocket disconnected')

    // Attempt reconnection after 3 seconds
    setTimeout(() => {
      if (!connected.value) {
        console.log('Attempting to reconnect planner...')
        connectWebSocket()
      }
    }, 3000)
  }

  ws.onerror = (error) => {
    console.error('Planner WebSocket error:', error)
  }

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)
      handleWebSocketMessage(data)
    } catch (error) {
      console.error('Error parsing WebSocket message:', error)
    }
  }
}

const handleWebSocketMessage = (data) => {
  switch (data.type) {
    case 'conversation_created':
      // Store conversation ID for future messages
      conversationId.value = data.conversation_id
      console.log('Planner conversation created:', conversationId.value)
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

    case 'info':
      // System info message
      messages.value.push({
        role: 'system',
        content: data.message
      })
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
    model_id: selectedModelId.value
  }))

  // Clear input
  currentMessage.value = ''

  scrollToBottom()
}

const sendQuickMessage = (suggestion) => {
  currentMessage.value = suggestion
  sendMessage()
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

const activeModels = computed(() => models.value.filter((model) => model.is_active))

// Lifecycle
onMounted(async () => {
  // Load conversation history first
  await loadConversationHistory()
  await loadModels()
  // Then connect WebSocket
  connectWebSocket()
})

onUnmounted(() => {
  if (ws) {
    ws.close()
  }
})

// Watch for system changes
watch(() => props.systemId, () => {
  // Reconnect if system changes
  if (ws) {
    ws.close()
  }
  messages.value = []
  currentStreamingMessage = ''
  selectedModelId.value = null
  loadConversationHistory()
  loadModels()
  connectWebSocket()
})
</script>

<style scoped>
.planner-chat {
  @apply flex flex-col h-full bg-white rounded-lg border;
  height: 600px;
}

.chat-header {
  @apply px-4 py-3 border-b bg-purple-50;
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

.system-message {
  @apply justify-center;
}

.message-bubble {
  @apply max-w-[80%] rounded-lg px-4 py-2;
}

.user-message .message-bubble {
  @apply bg-blue-600 text-white;
}

.assistant-message .message-bubble {
  @apply bg-purple-50 text-gray-900 border border-purple-200;
}

.system-bubble {
  @apply px-3 py-1 bg-gray-100 text-gray-600 text-xs rounded-full;
}

.assistant-avatar {
  @apply w-8 h-8 rounded-full bg-purple-100 text-purple-600 flex items-center justify-center flex-shrink-0;
}

.typing-indicator {
  @apply flex gap-1 px-4 py-3 bg-purple-50 rounded-lg border border-purple-200;
}

.typing-indicator span {
  @apply w-2 h-2 bg-purple-400 rounded-full animate-bounce;
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
  @apply flex-1 px-3 py-2 border rounded-lg resize-none focus:ring-2 focus:ring-purple-500 focus:border-transparent;
  max-height: 120px;
}

.send-button {
  @apply px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors;
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
