<template>
  <div class="session-trace">
    <!-- Loading -->
    <div v-if="loading" class="text-center py-8">
      <div class="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
      <p class="mt-2 text-sm text-gray-600">Loading sessions...</p>
    </div>

    <!-- Sessions List -->
    <div v-else-if="sessions.length > 0" class="space-y-4">
      <div
        v-for="session in sessions"
        :key="session.id"
        class="border rounded-lg overflow-hidden"
      >
        <!-- Session Header -->
        <div
          class="px-4 py-3 bg-gray-50 flex items-center justify-between cursor-pointer hover:bg-gray-100"
          @click="toggleSession(session.id)"
        >
          <div class="flex-1">
            <div class="flex items-center gap-2">
              <span
                class="px-2 py-1 text-xs font-medium rounded-full"
                :class="{
                  'bg-green-100 text-green-800': session.status === 'success',
                  'bg-yellow-100 text-yellow-800': session.status === 'running',
                  'bg-red-100 text-red-800': session.status === 'failed',
                  'bg-gray-100 text-gray-800': session.status === 'cancelled'
                }"
              >
                {{ session.status }}
              </span>
              <span
                class="px-2 py-1 text-xs font-medium rounded bg-blue-100 text-blue-800"
              >
                {{ session.session_type }}
              </span>
              <span class="text-sm text-gray-600">
                {{ formatDate(session.created_at) }}
              </span>
              <span v-if="session.duration_ms" class="text-xs text-gray-500">
                {{ session.duration_ms }}ms
              </span>
            </div>
            <p class="text-sm text-gray-900 mt-1">
              {{ session.user_request }}
            </p>
          </div>
          <svg
            class="w-5 h-5 text-gray-400 transition-transform"
            :class="{ 'rotate-180': expandedSessions.has(session.id) }"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
          </svg>
        </div>

        <!-- Session Details -->
        <div
          v-if="expandedSessions.has(session.id)"
          class="px-4 py-3 bg-white border-t"
        >
          <div class="space-y-3 text-sm">
            <!-- Basic Info -->
            <div class="grid grid-cols-2 gap-2">
              <div>
                <span class="font-medium text-gray-700">Session ID:</span>
                <span class="text-gray-600 ml-2 font-mono text-xs">{{ session.session_id }}</span>
              </div>
              <div>
                <span class="font-medium text-gray-700">Intent:</span>
                <span class="text-gray-600 ml-2">{{ session.intent_classified_as || 'N/A' }}</span>
              </div>
            </div>

            <!-- LLM Model -->
            <div v-if="session.llm_model_name">
              <span class="font-medium text-gray-700">Model:</span>
              <span class="text-gray-600 ml-2">{{ session.llm_model_name }}</span>
            </div>

            <!-- Error Message -->
            <div v-if="session.error_message" class="mt-2">
              <span class="font-medium text-red-700">Error:</span>
              <pre class="mt-1 text-xs bg-red-50 p-2 rounded text-red-900 overflow-x-auto">{{ session.error_message }}</pre>
            </div>

            <!-- Final Answer -->
            <div v-if="session.final_answer" class="mt-2">
              <span class="font-medium text-gray-700">Answer:</span>
              <div class="mt-1 text-sm text-gray-900 bg-gray-50 p-3 rounded">
                {{ session.final_answer }}
              </div>
            </div>

            <!-- Knowledge Context -->
            <div v-if="session.knowledge_context && Object.keys(session.knowledge_context).length > 0" class="mt-2">
              <details class="cursor-pointer">
                <summary class="font-medium text-gray-700 hover:text-gray-900">
                  📚 Knowledge Context
                </summary>
                <pre class="mt-2 text-xs bg-gray-50 p-2 rounded overflow-x-auto">{{ JSON.stringify(session.knowledge_context, null, 2) }}</pre>
              </details>
            </div>

            <!-- Tools Used -->
            <div v-if="session.tools_used && session.tools_used.length > 0" class="mt-2">
              <span class="font-medium text-gray-700">🔧 Tools Used:</span>
              <div class="flex flex-wrap gap-1 mt-1">
                <span
                  v-for="(tool, idx) in session.tools_used"
                  :key="idx"
                  class="px-2 py-1 text-xs bg-purple-100 text-purple-800 rounded"
                >
                  {{ tool }}
                </span>
              </div>
            </div>

            <!-- Conversation Link -->
            <div v-if="session.conversation_title" class="mt-2">
              <span class="font-medium text-gray-700">Conversation:</span>
              <span class="text-gray-600 ml-2">{{ session.conversation_title }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Empty State -->
    <div v-else class="text-center py-12">
      <svg class="mx-auto h-12 w-12 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
      </svg>
      <p class="mt-2 text-sm text-gray-600">No agent sessions yet</p>
      <p class="text-xs text-gray-500 mt-1">Sessions will appear here when you interact with the repository chat</p>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import api from '../services/api'

const props = defineProps({
  repositoryId: {
    type: Number,
    required: true
  }
})

const sessions = ref([])
const loading = ref(false)
const expandedSessions = ref(new Set())

const loadSessions = async () => {
  try {
    loading.value = true
    const response = await api.get(`/sessions/?repository=${props.repositoryId}`)
    sessions.value = response.data.results || response.data
  } catch (error) {
    console.error('Failed to load sessions:', error)
  } finally {
    loading.value = false
  }
}

const toggleSession = (sessionId) => {
  if (expandedSessions.value.has(sessionId)) {
    expandedSessions.value.delete(sessionId)
  } else {
    expandedSessions.value.add(sessionId)
  }
}

const formatDate = (dateString) => {
  const date = new Date(dateString)
  const now = new Date()
  const diffMs = now - date
  const diffMins = Math.floor(diffMs / 60000)

  if (diffMins < 1) return 'Just now'
  if (diffMins < 60) return `${diffMins}m ago`

  const diffHours = Math.floor(diffMins / 60)
  if (diffHours < 24) return `${diffHours}h ago`

  const diffDays = Math.floor(diffHours / 24)
  if (diffDays < 7) return `${diffDays}d ago`

  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  })
}

// Load on mount and when repository changes
onMounted(() => {
  loadSessions()
})

watch(() => props.repositoryId, () => {
  loadSessions()
})
</script>

<style scoped>
.session-trace {
  @apply p-4;
  max-height: 600px;
  overflow-y: auto;
}
</style>
