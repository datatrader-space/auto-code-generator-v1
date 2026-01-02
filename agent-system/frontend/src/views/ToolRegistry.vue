<template>
  <div class="tool-registry-container p-6 bg-gray-50 min-h-screen">
    <div class="max-w-7xl mx-auto">
      <!-- Header -->
      <div class="flex justify-between items-center mb-6">
        <div>
          <h1 class="text-3xl font-bold text-gray-900">🔧 Tool Registry</h1>
          <p class="text-gray-600 mt-1">Manage and execute agent tools</p>
        </div>
        <button
          @click="showRegisterModal = true"
          class="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition font-medium flex items-center gap-2"
        >
          <span class="text-xl">+</span>
          Register Tool
        </button>
      </div>

      <!-- Stats Cards -->
      <div class="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
        <div class="bg-white p-4 rounded-lg shadow">
          <div class="text-sm text-gray-600">Total Tools</div>
          <div class="text-2xl font-bold text-gray-900">{{ totalTools }}</div>
        </div>
        <div class="bg-white p-4 rounded-lg shadow">
          <div class="text-sm text-gray-600">Enabled</div>
          <div class="text-2xl font-bold text-green-600">{{ enabledCount }}</div>
        </div>
        <div class="bg-white p-4 rounded-lg shadow">
          <div class="text-sm text-gray-600">Categories</div>
          <div class="text-2xl font-bold text-purple-600">{{ categoriesCount }}</div>
        </div>
        <div class="bg-white p-4 rounded-lg shadow">
          <div class="text-sm text-gray-600">Recent Executions</div>
          <div class="text-2xl font-bold text-blue-600">{{ recentExecutions }}</div>
        </div>
      </div>

      <!-- Filters -->
      <div class="bg-white p-4 rounded-lg shadow mb-6">
        <div class="flex gap-4 items-center">
          <input
            v-model="searchQuery"
            type="text"
            placeholder="Search tools..."
            class="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <select
            v-model="selectedCategory"
            class="px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="">All Categories</option>
            <option v-for="cat in categories" :key="cat" :value="cat">
              {{ cat.toUpperCase() }}
            </option>
          </select>
        </div>
      </div>

      <!-- Loading State -->
      <div v-if="loading" class="text-center py-12">
        <div class="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
        <p class="mt-4 text-gray-600">Loading tools...</p>
      </div>

      <!-- Tools List by Category -->
      <div v-else class="space-y-6">
        <div v-for="(tools, category) in filteredToolsByCategory" :key="category">
          <h2 class="text-xl font-bold text-gray-800 mb-3 flex items-center">
            {{ getCategoryIcon(category) }} {{ category.toUpperCase() }}
            <span class="ml-2 text-sm font-normal text-gray-500">({{ tools.length }})</span>
          </h2>

          <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            <ToolCard
              v-for="tool in tools"
              :key="tool.name"
              :tool="tool"
              @execute="openExecuteModal"
              @view-details="viewToolDetails"
            />
          </div>
        </div>

        <!-- No Results -->
        <div v-if="Object.keys(filteredToolsByCategory).length === 0" class="text-center py-12">
          <p class="text-gray-500">No tools found matching your criteria</p>
        </div>
      </div>

      <!-- Execute Tool Modal -->
      <ToolExecuteModal
        v-if="showExecuteModal"
        :tool="selectedTool"
        :repositories="repositories"
        @close="showExecuteModal = false"
        @execute="executeToolWithParams"
      />

      <!-- Register Tool Modal -->
      <RegisterToolModal
        :show="showRegisterModal"
        @close="showRegisterModal = false"
        @registered="handleToolRegistered"
      />

      <!-- Execution Results Panel -->
      <ExecutionResultsPanel
        v-if="executionResults.length > 0"
        :results="executionResults"
        @clear="executionResults = []"
      />
    </div>
  </div>
</template>

<script>
import { ref, computed, onMounted } from 'vue'
import axios from 'axios'
import ToolCard from '../components/tools/ToolCard.vue'
import ToolExecuteModal from '../components/tools/ToolExecuteModal.vue'
import ExecutionResultsPanel from '../components/tools/ExecutionResultsPanel.vue'
import RegisterToolModal from '../components/tools/RegisterToolModal.vue'

export default {
  name: 'ToolRegistry',
  components: {
    ToolCard,
    ToolExecuteModal,
    ExecutionResultsPanel,
    RegisterToolModal
  },
  setup() {
    const tools = ref([])
    const toolsByCategory = ref({})
    const categories = ref([])
    const repositories = ref([])
    const loading = ref(false)

    const searchQuery = ref('')
    const selectedCategory = ref('')

    const showExecuteModal = ref(false)
    const showRegisterModal = ref(false)
    const selectedTool = ref(null)

    const executionResults = ref([])

    // Stats
    const totalTools = computed(() => tools.value.length)
    const enabledCount = computed(() => tools.value.filter(t => t.enabled).length)
    const categoriesCount = computed(() => categories.value.length)
    const recentExecutions = computed(() => executionResults.value.length)

    // Filtered tools
    const filteredTools = computed(() => {
      let filtered = tools.value

      // Search filter
      if (searchQuery.value) {
        const query = searchQuery.value.toLowerCase()
        filtered = filtered.filter(t =>
          t.name.toLowerCase().includes(query) ||
          t.description.toLowerCase().includes(query)
        )
      }

      // Category filter
      if (selectedCategory.value) {
        filtered = filtered.filter(t => t.category === selectedCategory.value)
      }

      return filtered
    })

    const filteredToolsByCategory = computed(() => {
      const grouped = {}
      filteredTools.value.forEach(tool => {
        if (!grouped[tool.category]) {
          grouped[tool.category] = []
        }
        grouped[tool.category].push(tool)
      })
      return grouped
    })

    // Methods
    const loadTools = async () => {
      loading.value = true
      try {
        const response = await axios.get('/api/tools/')
        tools.value = response.data.tools
        toolsByCategory.value = response.data.by_category
        categories.value = response.data.categories
      } catch (error) {
        console.error('Failed to load tools:', error)
      } finally {
        loading.value = false
      }
    }

    const loadRepositories = async () => {
      try {
        const response = await axios.get('/systems/')
        // Extract repositories from all systems
        const allRepos = []
        response.data.forEach(system => {
          if (system.repositories) {
            system.repositories.forEach(repo => {
              allRepos.push({
                ...repo,
                system_name: system.name
              })
            })
          }
        })
        repositories.value = allRepos
      } catch (error) {
        console.error('Failed to load repositories:', error)
      }
    }

    const openExecuteModal = (tool) => {
      selectedTool.value = tool
      showExecuteModal.value = true
    }

    const viewToolDetails = (tool) => {
      // Show detailed modal (can be implemented later)
      console.log('View details for:', tool)
    }

    const executeToolWithParams = async (execution) => {
      try {
        const response = await axios.post('/api/tools/execute/', {
          tool_name: execution.tool.name,
          parameters: execution.parameters,
          repository_id: execution.repository_id,
          session_id: execution.session_id
        })

        executionResults.value.unshift({
          id: Date.now(),
          tool_name: execution.tool.name,
          timestamp: new Date().toISOString(),
          ...response.data
        })

        showExecuteModal.value = false
      } catch (error) {
        console.error('Tool execution failed:', error)
        executionResults.value.unshift({
          id: Date.now(),
          tool_name: execution.tool.name,
          timestamp: new Date().toISOString(),
          success: false,
          error: error.response?.data?.error || error.message
        })
      }
    }

    const getCategoryIcon = (category) => {
      const icons = {
        'crs': '🔍',
        'shell': '💻',
        'filesystem': '📁',
        'git': '🌿',
        'testing': '✅',
        'network': '🌐',
        'database': '🗄️',
        'custom': '⚙️',
        'jira': '📋',
        'remote': '🌐'
      }
      return icons[category] || '🔧'
    }

    const handleToolRegistered = async () => {
      // Reload tools after registration
      await loadTools()
      showRegisterModal.value = false
      // Show success message
      alert('Tool registered successfully!')
    }

    onMounted(() => {
      loadTools()
      loadRepositories()
    })

    return {
      tools,
      toolsByCategory,
      categories,
      repositories,
      loading,
      searchQuery,
      selectedCategory,
      showExecuteModal,
      showRegisterModal,
      selectedTool,
      executionResults,
      totalTools,
      enabledCount,
      categoriesCount,
      recentExecutions,
      filteredToolsByCategory,
      openExecuteModal,
      viewToolDetails,
      executeToolWithParams,
      getCategoryIcon,
      handleToolRegistered
    }
  }
}
</script>

<style scoped>
.tool-registry-container {
  animation: fadeIn 0.3s ease-in;
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
</style>
