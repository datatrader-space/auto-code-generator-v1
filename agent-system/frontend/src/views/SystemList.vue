<template>
  <div>
    <!-- Header -->
    <div class="mb-8">
      <h1 class="text-3xl font-bold text-gray-900">Your Systems</h1>
      <p class="mt-2 text-gray-600">Manage your multi-repo agent systems</p>
    </div>
    
    <!-- Create System Button -->
    <div class="mb-6">
      <div class="flex gap-4">
        <router-link
          to="/agents"
          class="inline-flex items-center px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition"
        >
          <span class="mr-2">🤖</span>
          Agent Library
        </router-link>
        <button
          @click="showCreateModal = true"
          class="inline-flex items-center px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition"
        >
          <span class="mr-2">+</span>
          Create New System
        </button>
      </div>
    </div>

    <!-- LLM Stats -->
    <div class="mb-8 bg-white rounded-lg shadow p-4">
      <div class="flex items-center justify-between">
        <div>
          <h2 class="text-lg font-semibold text-gray-900">LLM Activity</h2>
          <p class="text-sm text-gray-500">Last 24h overview</p>
        </div>
        <div v-if="statsLoading" class="text-xs text-gray-400">Loading...</div>
      </div>
      <div v-if="stats" class="grid grid-cols-2 md:grid-cols-4 gap-4 mt-4">
        <div>
          <p class="text-xl font-semibold text-gray-900">{{ stats.total_requests }}</p>
          <p class="text-xs text-gray-500">Total Requests</p>
        </div>
        <div>
          <p class="text-xl font-semibold text-gray-900">{{ formatPercent(stats.error_rate) }}</p>
          <p class="text-xs text-gray-500">Error Rate</p>
        </div>
        <div>
          <p class="text-xl font-semibold text-gray-900">{{ formatLatency(stats.avg_latency_ms) }}</p>
          <p class="text-xs text-gray-500">Avg Latency</p>
        </div>
        <div>
          <p class="text-sm font-semibold text-gray-900 truncate">
            {{ topProviderModel }}
          </p>
          <p class="text-xs text-gray-500">Top Provider/Model</p>
        </div>
      </div>
      <div v-else-if="!statsLoading" class="text-sm text-gray-500 mt-4">
        No LLM activity yet.
      </div>
    </div>
    
    <!-- Loading -->
    <div v-if="loading" class="text-center py-12">
      <div class="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      <p class="mt-4 text-gray-600">Loading systems...</p>
    </div>
    
    <!-- Systems Grid -->
    <div v-else-if="systems.length > 0" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
      <div
        v-for="system in systems"
        :key="system.id"
        class="bg-white rounded-lg shadow hover:shadow-lg transition cursor-pointer"
        @click="goToSystem(system.id)"
      >
        <div class="p-6">
          <!-- Status Badge -->
          <div class="flex items-start justify-between mb-4">
            <div>
              <h3 class="text-lg font-semibold text-gray-900">{{ system.name }}</h3>
              <p class="text-sm text-gray-500 mt-1">{{ system.description || 'No description' }}</p>
            </div>
            <span
              class="px-2 py-1 text-xs font-medium rounded-full"
              :class="{
                'bg-green-100 text-green-800': system.status === 'ready',
                'bg-yellow-100 text-yellow-800': system.status === 'initializing',
                'bg-blue-100 text-blue-800': system.status === 'analyzing',
                'bg-red-100 text-red-800': system.status === 'error'
              }"
            >
              {{ system.status }}
            </span>
          </div>
          
          <!-- Stats -->
          <div class="grid grid-cols-2 gap-4 mt-4">
            <div>
              <p class="text-2xl font-bold text-blue-600">{{ system.repositories_count }}</p>
              <p class="text-xs text-gray-500">Repositories</p>
            </div>
            <div>
              <p class="text-2xl font-bold text-purple-600">{{ system.knowledge_count }}</p>
              <p class="text-xs text-gray-500">Knowledge Items</p>
            </div>
          </div>
          
          <!-- Created date -->
          <div class="mt-4 pt-4 border-t">
            <p class="text-xs text-gray-400">
              Created {{ formatDate(system.created_at) }}
            </p>
          </div>
        </div>
      </div>
    </div>
    
    <!-- Empty State -->
    <div v-else class="text-center py-12 bg-white rounded-lg shadow">
      <svg class="mx-auto h-12 w-12 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4" />
      </svg>
      <h3 class="mt-2 text-sm font-medium text-gray-900">No systems</h3>
      <p class="mt-1 text-sm text-gray-500">Get started by creating a new system.</p>
      <div class="mt-6">
        <button
          @click="showCreateModal = true"
          class="inline-flex items-center px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
        >
          <span class="mr-2">+</span>
          Create System
        </button>
      </div>
    </div>
    
    <!-- Create System Modal -->
    <div
      v-if="showCreateModal"
      class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50"
      @click.self="showCreateModal = false"
    >
      <div class="bg-white rounded-lg max-w-md w-full p-6">
        <h2 class="text-xl font-bold mb-4">Create New System</h2>
        
        <form @submit.prevent="createSystem">
          <div class="mb-4">
            <label class="block text-sm font-medium text-gray-700 mb-2">
              System Name *
            </label>
            <input
              v-model="newSystem.name"
              type="text"
              required
              class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              placeholder="e.g., E-commerce Platform"
            />
          </div>
          
          <div class="mb-6">
            <label class="block text-sm font-medium text-gray-700 mb-2">
              Description
            </label>
            <textarea
              v-model="newSystem.description"
              rows="3"
              class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              placeholder="Describe your system..."
            ></textarea>
          </div>
          
          <div class="flex justify-end space-x-3">
            <button
              type="button"
              @click="showCreateModal = false"
              class="px-4 py-2 text-gray-700 hover:bg-gray-100 rounded-lg transition"
            >
              Cancel
            </button>
            <button
              type="submit"
              :disabled="creating"
              class="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition disabled:opacity-50"
            >
              {{ creating ? 'Creating...' : 'Create System' }}
            </button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, inject, computed } from 'vue'
import { useRouter } from 'vue-router'
import api from '../services/api'

const router = useRouter()
const notify = inject('notify')

const systems = ref([])
const loading = ref(true)

const showCreateModal = ref(false)
const creating = ref(false)

const stats = ref(null)
const statsLoading = ref(false)

const newSystem = ref({
  name: '',
  description: ''
})

// Load systems
const loadSystems = async () => {
  try {
    loading.value = true
    const response = await api.getSystems()
    systems.value = response.data?.results || response.data || []
  } catch (error) {
    notify?.('Failed to load systems', 'error')
    console.error(error)
  } finally {
    loading.value = false
  }
}

// Load LLM stats (single source of truth)
const loadStats = async () => {
  try {
    statsLoading.value = true
    const response = await api.getLlmStats()
    stats.value = response.data
  } catch (error) {
    console.error('Failed to load LLM stats:', error)
    stats.value = null
  } finally {
    statsLoading.value = false
  }
}

// Create system
const createSystem = async () => {
  try {
    creating.value = true
    const response = await api.createSystem(newSystem.value)

    notify?.('System created successfully!', 'success')
    showCreateModal.value = false
    newSystem.value = { name: '', description: '' }

    router.push(`/systems/${response.data.id}`)
  } catch (error) {
    notify?.('Failed to create system', 'error')
    console.error(error)
  } finally {
    creating.value = false
  }
}

// Navigate to system
const goToSystem = (id) => {
  router.push(`/systems/${id}`)
}

// Formatting helpers
const formatDate = (dateString) => {
  if (!dateString) return '—'
  const date = new Date(dateString)
  return date.toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric'
  })
}

const formatPercent = (value) => {
  if (value === null || value === undefined) return '—'
  return `${(value * 100).toFixed(1)}%`
}

const formatLatency = (value) => {
  if (value === null || value === undefined) return '—'
  return `${Math.round(value)} ms`
}

const topProviderModel = computed(() => {
  const top = stats.value?.top_provider_model
  if (!top) return '—'
  return [top.provider, top.model].filter(Boolean).join(' / ')
})

// Load on mount
onMounted(() => {
  loadSystems()
  loadStats()
})
</script>
