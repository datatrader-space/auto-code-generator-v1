<template>
  <div class="space-y-8">
    <div>
      <h1 class="text-3xl font-bold text-gray-900">AI Providers</h1>
      <p class="mt-2 text-gray-600">
        Manage third-party AI APIs and local providers. Add models to make them available in chat.
      </p>
    </div>

    <div class="bg-white rounded-lg shadow">
      <div class="px-6 py-4 border-b flex items-center justify-between">
        <div>
          <h2 class="text-lg font-semibold text-gray-900">Providers</h2>
          <p class="text-sm text-gray-500">Configure Ollama, Anthropic, OpenAI, Gemini, or custom endpoints.</p>
        </div>
      </div>
      <div class="p-6 space-y-4">
        <div v-if="providers.length === 0" class="text-sm text-gray-500">
          No providers configured yet.
        </div>
        <div v-else class="space-y-3">
          <div
            v-for="provider in providers"
            :key="provider.id"
            class="flex flex-col gap-3 border rounded-lg p-4"
          >
            <div class="flex items-center justify-between">
              <div>
                <p class="font-medium text-gray-900">{{ provider.name }}</p>
                <p class="text-xs text-gray-500">
                  {{ provider.provider_type.toUpperCase() }}
                  <span v-if="provider.base_url">• {{ provider.base_url }}</span>
                </p>
              </div>
              <div class="flex items-center gap-3">
                <label class="flex items-center text-xs text-gray-500 gap-2">
                  <input
                    type="checkbox"
                    v-model="provider.is_active"
                    @change="toggleProvider(provider)"
                  />
                  Active
                </label>
                <button
                  v-if="provider.provider_type === 'ollama'"
                  @click="syncOllama(provider)"
                  class="text-xs px-3 py-1 rounded bg-purple-100 text-purple-700 hover:bg-purple-200"
                >
                  Sync Ollama Models
                </button>
                <button
                  @click="removeProvider(provider)"
                  class="text-xs px-3 py-1 rounded bg-red-100 text-red-700 hover:bg-red-200"
                >
                  Delete
                </button>
              </div>
            </div>
            <div class="text-xs text-gray-400">
              API Key: <span>{{ provider.api_key ? 'Configured' : 'Not set' }}</span>
            </div>
          </div>
        </div>

        <form @submit.prevent="createProvider" class="border-t pt-4 grid gap-4 md:grid-cols-2">
          <div>
            <label class="text-sm font-medium text-gray-700">Name</label>
            <input v-model="newProvider.name" class="input" placeholder="My Anthropic" required />
          </div>
          <div>
            <label class="text-sm font-medium text-gray-700">Provider Type</label>
            <select v-model="newProvider.provider_type" class="input">
              <option value="ollama">Ollama</option>
              <option value="anthropic">Anthropic</option>
              <option value="openai">OpenAI</option>
              <option value="gemini">Gemini</option>
              <option value="custom">Custom</option>
            </select>
          </div>
          <div>
            <label class="text-sm font-medium text-gray-700">Base URL</label>
            <input v-model="newProvider.base_url" class="input" placeholder="http://localhost:11434" />
          </div>
          <div>
            <label class="text-sm font-medium text-gray-700">API Key</label>
            <input v-model="newProvider.api_key" class="input" placeholder="sk-..." />
          </div>
          <div class="md:col-span-2 flex items-center justify-end gap-2">
            <button type="submit" class="btn-primary">Add Provider</button>
          </div>
        </form>
      </div>
    </div>

    <div class="bg-white rounded-lg shadow">
      <div class="px-6 py-4 border-b flex items-center justify-between">
        <div>
          <h2 class="text-lg font-semibold text-gray-900">Models</h2>
          <p class="text-sm text-gray-500">Assign models to providers for chat selection.</p>
        </div>
        <select v-model="modelFilter" class="input max-w-xs">
          <option value="">All Providers</option>
          <option v-for="provider in providers" :key="provider.id" :value="provider.id">
            {{ provider.name }}
          </option>
        </select>
      </div>
      <div class="p-6 space-y-4">
        <div v-if="models.length === 0" class="text-sm text-gray-500">
          No models configured yet.
        </div>
        <div v-else class="space-y-2">
          <div
            v-for="model in filteredModels"
            :key="model.id"
            class="flex items-center justify-between border rounded-lg p-3"
          >
            <div>
              <p class="font-medium text-gray-900">{{ model.name }}</p>
              <p class="text-xs text-gray-500">
                {{ model.provider_name }} • {{ model.model_id }}
              </p>
            </div>
            <div class="flex items-center gap-3">
              <label class="flex items-center text-xs text-gray-500 gap-2">
                <input
                  type="checkbox"
                  v-model="model.is_active"
                  @change="toggleModel(model)"
                />
                Active
              </label>
              <button
                @click="removeModel(model)"
                class="text-xs px-3 py-1 rounded bg-red-100 text-red-700 hover:bg-red-200"
              >
                Delete
              </button>
            </div>
          </div>
        </div>

        <form @submit.prevent="createModel" class="border-t pt-4 grid gap-4 md:grid-cols-2">
          <div>
            <label class="text-sm font-medium text-gray-700">Provider</label>
            <select v-model="newModel.provider" class="input" required>
              <option value="" disabled>Select provider</option>
              <option v-for="provider in providers" :key="provider.id" :value="provider.id">
                {{ provider.name }}
              </option>
            </select>
          </div>
          <div>
            <label class="text-sm font-medium text-gray-700">Model Name</label>
            <input v-model="newModel.name" class="input" placeholder="gpt-4o" required />
          </div>
          <div>
            <label class="text-sm font-medium text-gray-700">Model ID</label>
            <input v-model="newModel.model_id" class="input" placeholder="gpt-4o" required />
          </div>
          <div>
            <label class="text-sm font-medium text-gray-700">Context Window</label>
            <input v-model.number="newModel.context_window" type="number" class="input" placeholder="0" />
          </div>
          <div class="md:col-span-2 flex items-center justify-end gap-2">
            <button type="submit" class="btn-primary">Add Model</button>
          </div>
        </form>
      </div>
    </div>

    <div class="bg-white rounded-lg shadow">
      <div class="px-6 py-4 border-b flex items-center justify-between">
        <div>
          <h2 class="text-lg font-semibold text-gray-900">Recent LLM Requests</h2>
          <p class="text-sm text-gray-500">Last 15 requests grouped by provider/model.</p>
        </div>
        <div v-if="statsLoading" class="text-xs text-gray-400">Loading...</div>
      </div>
      <div class="p-6 space-y-4">
        <div v-if="groupedRequests.length === 0" class="text-sm text-gray-500">
          No request history yet.
        </div>
        <div v-else class="space-y-4">
          <div v-for="group in groupedRequests" :key="group.label" class="border rounded-lg">
            <div class="px-4 py-2 border-b bg-gray-50 text-sm font-medium text-gray-700">
              {{ group.label }}
            </div>
            <div class="divide-y text-sm">
              <div
                v-for="request in group.requests"
                :key="request.created_at"
                class="px-4 py-2 grid grid-cols-4 gap-2 items-center"
              >
                <span :class="request.status === 'error' ? 'text-red-600' : 'text-green-600'">
                  {{ request.status }}
                </span>
                <span class="text-gray-500">{{ formatLatency(request.latency_ms) }}</span>
                <span class="text-gray-500">{{ request.total_tokens ?? '—' }} tokens</span>
                <span class="text-gray-400">{{ formatDate(request.created_at) }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, inject, onMounted, ref, watch } from 'vue'
import api from '../services/api'

const notify = inject('notify', () => {})

const providers = ref([])
const models = ref([])
const modelFilter = ref('')
const stats = ref(null)
const statsLoading = ref(false)

const newProvider = ref({
  name: '',
  provider_type: 'ollama',
  base_url: '',
  api_key: '',
  is_active: true
})

const newModel = ref({
  provider: '',
  name: '',
  model_id: '',
  context_window: 0,
  is_active: true
})

const loadProviders = async () => {
  const response = await api.getLlmProviders()
  providers.value = response.data.results || response.data
}

const loadModels = async () => {
  const params = {}
  if (modelFilter.value) {
    params.provider = modelFilter.value
  }
  const response = await api.getLlmModels(params)
  models.value = response.data.results || response.data
}

const loadStats = async () => {
  try {
    statsLoading.value = true
    const response = await api.getLlmStats()
    stats.value = response.data
  } finally {
    statsLoading.value = false
  }
}

const createProvider = async () => {
  await api.createLlmProvider(newProvider.value)
  notify('Provider added', 'success')
  newProvider.value = {
    name: '',
    provider_type: 'ollama',
    base_url: '',
    api_key: '',
    is_active: true
  }
  await loadProviders()
}

const createModel = async () => {
  await api.createLlmModel(newModel.value)
  notify('Model added', 'success')
  newModel.value = {
    provider: '',
    name: '',
    model_id: '',
    context_window: 0,
    is_active: true
  }
  await loadModels()
}

const toggleProvider = async (provider) => {
  await api.updateLlmProvider(provider.id, {
    ...provider,
    is_active: provider.is_active
  })
  notify('Provider updated', 'success')
}

const toggleModel = async (model) => {
  await api.updateLlmModel(model.id, {
    ...model,
    is_active: model.is_active
  })
  notify('Model updated', 'success')
}

const removeProvider = async (provider) => {
  if (!confirm(`Delete provider "${provider.name}"?`)) return
  await api.deleteLlmProvider(provider.id)
  notify('Provider deleted', 'success')
  await loadProviders()
  await loadModels()
}

const removeModel = async (model) => {
  if (!confirm(`Delete model "${model.name}"?`)) return
  await api.deleteLlmModel(model.id)
  notify('Model deleted', 'success')
  await loadModels()
}

const syncOllama = async (provider) => {
  await api.syncOllamaModels(provider.id)
  notify('Ollama models synced', 'success')
  await loadModels()
}

const filteredModels = computed(() => {
  if (!modelFilter.value) return models.value
  return models.value.filter((model) => model.provider === parseInt(modelFilter.value, 10))
})

const groupedRequests = computed(() => {
  const recent = stats.value?.recent_requests || []
  const groups = {}
  recent.forEach((request) => {
    const label = `${request.provider || 'unknown'} / ${request.model || 'default'}`
    if (!groups[label]) {
      groups[label] = []
    }
    groups[label].push(request)
  })
  return Object.entries(groups).map(([label, requests]) => ({ label, requests }))
})

const formatLatency = (value) => {
  if (value === null || value === undefined) return '—'
  return `${Math.round(value)} ms`
}

const formatDate = (value) => {
  if (!value) return '—'
  return new Date(value).toLocaleString()
}

watch(modelFilter, loadModels)

onMounted(async () => {
  await loadProviders()
  await loadModels()
  await loadStats()
})
</script>

<style scoped>
.input {
  @apply w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500;
}

.btn-primary {
  @apply bg-blue-600 text-white px-4 py-2 rounded-lg text-sm hover:bg-blue-700;
}
</style>
