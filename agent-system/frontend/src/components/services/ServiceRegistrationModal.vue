<template>
  <div class="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
    <div class="bg-white rounded-lg shadow-2xl max-w-4xl w-full max-h-[90vh] overflow-hidden flex flex-col">
      <!-- Header -->
      <div class="bg-gradient-to-r from-blue-600 to-blue-700 text-white px-6 py-4">
        <div class="flex items-center justify-between">
          <div>
            <h2 class="text-xl font-bold">Register New Service</h2>
            <p class="text-sm text-white/80 mt-1">{{ stepDescriptions[currentStep] }}</p>
          </div>
          <button
            @click="$emit('close')"
            class="text-white/80 hover:text-white text-2xl leading-none"
          >
            ×
          </button>
        </div>

        <!-- Progress Steps -->
        <div class="flex items-center gap-2 mt-4">
          <div
            v-for="(step, index) in steps"
            :key="index"
            class="flex-1 h-2 rounded-full transition"
            :class="index <= currentStep ? 'bg-white' : 'bg-white/30'"
          ></div>
        </div>
      </div>

      <!-- Content -->
      <div class="flex-1 overflow-y-auto p-6">
        <!-- Step 1: Basic Info -->
        <div v-if="currentStep === 0">
          <div class="space-y-4">
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">Service Name *</label>
              <input
                v-model="formData.name"
                type="text"
                placeholder="e.g., Jira, Slack, GitHub"
                class="w-full px-3 py-2 border border-gray-300 rounded focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            </div>

            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">Category</label>
              <select
                v-model="formData.category"
                class="w-full px-3 py-2 border border-gray-300 rounded focus:ring-2 focus:ring-blue-500"
              >
                <option value="">Select category</option>
                <option value="project_management">Project Management</option>
                <option value="communication">Communication</option>
                <option value="file_storage">File Storage</option>
                <option value="code_repository">Code Repository</option>
                <option value="task_management">Task Management</option>
                <option value="crm">CRM</option>
                <option value="marketing">Marketing</option>
                <option value="analytics">Analytics</option>
                <option value="other">Other</option>
              </select>
            </div>

            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">Description *</label>
              <textarea
                v-model="formData.description"
                rows="3"
                placeholder="Describe what this service does"
                class="w-full px-3 py-2 border border-gray-300 rounded focus:ring-2 focus:ring-blue-500"
              ></textarea>
            </div>

            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">Icon (Emoji)</label>
              <input
                v-model="formData.icon"
                type="text"
                placeholder="🌐"
                maxlength="2"
                class="w-20 px-3 py-2 border border-gray-300 rounded text-center text-2xl focus:ring-2 focus:ring-blue-500"
              />
            </div>
          </div>
        </div>

        <!-- Step 2: API Configuration -->
        <div v-else-if="currentStep === 1">
          <div class="space-y-4">
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">Base URL *</label>
              <input
                v-model="formData.base_url"
                type="url"
                placeholder="https://api.example.com"
                class="w-full px-3 py-2 border border-gray-300 rounded focus:ring-2 focus:ring-blue-500"
              />
              <p class="text-xs text-gray-500 mt-1">The base URL for all API requests</p>
            </div>

            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">API Spec URL (OpenAPI/Swagger)</label>
              <input
                v-model="formData.api_spec_url"
                type="url"
                placeholder="https://api.example.com/openapi.json"
                class="w-full px-3 py-2 border border-gray-300 rounded focus:ring-2 focus:ring-blue-500"
              />
              <p class="text-xs text-gray-500 mt-1">URL to OpenAPI or Swagger specification</p>
            </div>

            <button
              v-if="formData.api_spec_url"
              @click="discoverActions"
              :disabled="discovering"
              class="px-4 py-2 bg-purple-600 text-white rounded hover:bg-purple-700 transition disabled:opacity-50"
            >
              {{ discovering ? 'Discovering...' : '🔍 Discover Actions' }}
            </button>

            <div v-if="discoveredData" class="bg-green-50 border border-green-200 rounded p-4">
              <div class="flex items-center gap-2 text-green-700 font-medium mb-2">
                <span>✅</span>
                <span>Discovered {{ discoveredData.total_actions }} actions!</span>
              </div>
              <div class="text-sm text-gray-600">
                Found {{ Object.keys(discoveredData.categories).length }} categories
              </div>
            </div>
          </div>
        </div>

        <!-- Step 3: Authentication -->
        <div v-else-if="currentStep === 2">
          <div class="space-y-4">
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">Authentication Type *</label>
              <select
                v-model="formData.auth_type"
                class="w-full px-3 py-2 border border-gray-300 rounded focus:ring-2 focus:ring-blue-500"
              >
                <option value="bearer">Bearer Token</option>
                <option value="api_key">API Key</option>
                <option value="oauth2">OAuth 2.0</option>
                <option value="basic">Basic Auth</option>
              </select>
            </div>

            <!-- Bearer Token -->
            <div v-if="formData.auth_type === 'bearer'">
              <label class="block text-sm font-medium text-gray-700 mb-1">Bearer Token</label>
              <input
                v-model="formData.auth_config.token"
                type="password"
                placeholder="Enter token"
                class="w-full px-3 py-2 border border-gray-300 rounded focus:ring-2 focus:ring-blue-500"
              />
            </div>

            <!-- API Key -->
            <div v-if="formData.auth_type === 'api_key'">
              <label class="block text-sm font-medium text-gray-700 mb-1">API Key</label>
              <input
                v-model="formData.auth_config.api_key"
                type="password"
                placeholder="Enter API key"
                class="w-full px-3 py-2 border border-gray-300 rounded focus:ring-2 focus:ring-blue-500"
              />
            </div>

            <!-- Basic Auth -->
            <div v-if="formData.auth_type === 'basic'" class="space-y-3">
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">Username</label>
                <input
                  v-model="formData.auth_config.username"
                  type="text"
                  class="w-full px-3 py-2 border border-gray-300 rounded focus:ring-2 focus:ring-blue-500"
                />
              </div>
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">Password</label>
                <input
                  v-model="formData.auth_config.password"
                  type="password"
                  class="w-full px-3 py-2 border border-gray-300 rounded focus:ring-2 focus:ring-blue-500"
                />
              </div>
            </div>
          </div>
        </div>

        <!-- Step 4: Select Actions -->
        <div v-else-if="currentStep === 3">
          <div v-if="!discoveredData" class="text-center py-8">
            <p class="text-gray-600">No actions discovered yet.</p>
            <p class="text-sm text-gray-500 mt-2">Go back and discover actions from API spec.</p>
          </div>

          <div v-else>
            <div class="mb-4">
              <h3 class="font-medium text-gray-900 mb-2">Select Action Categories</h3>
              <p class="text-sm text-gray-600">Choose which categories of actions to enable</p>
            </div>

            <div class="space-y-3">
              <div
                v-for="(categoryData, categoryName) in discoveredData.categories"
                :key="categoryName"
                class="border rounded-lg p-4 hover:bg-gray-50 transition cursor-pointer"
                :class="{ 'bg-blue-50 border-blue-300': selectedCategories.includes(categoryName) }"
                @click="toggleCategory(categoryName)"
              >
                <div class="flex items-center justify-between">
                  <div class="flex-1">
                    <div class="flex items-center gap-2">
                      <input
                        type="checkbox"
                        :checked="selectedCategories.includes(categoryName)"
                        class="rounded"
                        @click.stop
                      />
                      <h4 class="font-medium text-gray-900">{{ categoryData.name }}</h4>
                      <span class="px-2 py-0.5 text-xs bg-gray-100 text-gray-600 rounded-full">
                        {{ categoryData.count }} actions
                      </span>
                    </div>
                    <div class="text-sm text-gray-600 mt-1 ml-6">
                      <span v-if="categoryData.actions.length > 0">
                        {{ categoryData.actions.slice(0, 3).map(a => a.name).join(', ') }}
                        <span v-if="categoryData.actions.length > 3">...</span>
                      </span>
                    </div>
                  </div>
                  <div v-if="discoveredData.recommended_categories.includes(categoryName)" class="ml-2">
                    <span class="px-2 py-1 text-xs bg-green-100 text-green-700 rounded-full">
                      Recommended
                    </span>
                  </div>
                </div>
              </div>
            </div>

            <div class="mt-4 p-3 bg-blue-50 border border-blue-200 rounded">
              <div class="text-sm text-blue-700">
                <strong>{{ getTotalSelectedActions() }} actions</strong> will be created
              </div>
            </div>
          </div>
        </div>

        <!-- Step 5: Review -->
        <div v-else-if="currentStep === 4">
          <div class="space-y-6">
            <div>
              <h3 class="font-medium text-gray-900 mb-4">Review Service Configuration</h3>

              <div class="space-y-3">
                <div class="flex justify-between py-2 border-b">
                  <span class="text-gray-600">Name:</span>
                  <span class="font-medium">{{ formData.name }}</span>
                </div>
                <div class="flex justify-between py-2 border-b">
                  <span class="text-gray-600">Category:</span>
                  <span class="font-medium">{{ formData.category || 'N/A' }}</span>
                </div>
                <div class="flex justify-between py-2 border-b">
                  <span class="text-gray-600">Base URL:</span>
                  <span class="font-medium text-sm">{{ formData.base_url }}</span>
                </div>
                <div class="flex justify-between py-2 border-b">
                  <span class="text-gray-600">Auth Type:</span>
                  <span class="font-medium">{{ formData.auth_type }}</span>
                </div>
                <div class="flex justify-between py-2 border-b">
                  <span class="text-gray-600">Categories Selected:</span>
                  <span class="font-medium">{{ selectedCategories.length }}</span>
                </div>
                <div class="flex justify-between py-2">
                  <span class="text-gray-600">Total Actions:</span>
                  <span class="font-medium text-blue-600">{{ getTotalSelectedActions() }}</span>
                </div>
              </div>
            </div>

            <div class="bg-yellow-50 border border-yellow-200 rounded p-4">
              <div class="flex gap-2">
                <span class="text-yellow-600">⚠️</span>
                <div class="text-sm text-yellow-800">
                  <strong>Note:</strong> After registration, all selected actions will be created as tools
                  and immediately available in the Tool Registry.
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Footer -->
      <div class="border-t border-gray-200 px-6 py-4 bg-gray-50 flex justify-between">
        <button
          v-if="currentStep > 0"
          @click="currentStep--"
          class="px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100 rounded transition"
        >
          ← Back
        </button>
        <div v-else></div>

        <div class="flex gap-3">
          <button
            @click="$emit('close')"
            class="px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100 rounded transition"
          >
            Cancel
          </button>
          <button
            v-if="currentStep < steps.length - 1"
            @click="nextStep"
            :disabled="!canProceed"
            class="px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded transition disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Next →
          </button>
          <button
            v-else
            @click="registerService"
            :disabled="registering || !canProceed"
            class="px-4 py-2 text-sm font-medium text-white bg-green-600 hover:bg-green-700 rounded transition disabled:opacity-50"
          >
            {{ registering ? 'Registering...' : 'Register Service' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, computed } from 'vue'
import axios from 'axios'

export default {
  name: 'ServiceRegistrationModal',
  emits: ['close', 'registered'],
  setup(props, { emit }) {
    const currentStep = ref(0)
    const discovering = ref(false)
    const registering = ref(false)

    const steps = ['Basic Info', 'API Config', 'Authentication', 'Select Actions', 'Review']
    const stepDescriptions = [
      'Basic service information',
      'API endpoint and spec configuration',
      'Authentication credentials',
      'Choose which action categories to enable',
      'Review and confirm'
    ]

    const formData = ref({
      name: '',
      description: '',
      category: '',
      icon: '',
      base_url: '',
      api_spec_url: '',
      auth_type: 'bearer',
      auth_config: {}
    })

    const discoveredData = ref(null)
    const selectedCategories = ref([])

    const canProceed = computed(() => {
      if (currentStep.value === 0) {
        return formData.value.name && formData.value.description
      }
      if (currentStep.value === 1) {
        return formData.value.base_url
      }
      if (currentStep.value === 2) {
        return formData.value.auth_type
      }
      if (currentStep.value === 3) {
        return selectedCategories.value.length > 0
      }
      return true
    })

    const discoverActions = async () => {
      discovering.value = true
      try {
        const response = await axios.post('/services/discover/', {
          api_spec_url: formData.value.api_spec_url,
          service_type: formData.value.name.toLowerCase()
        })

        discoveredData.value = response.data

        // Auto-select recommended categories
        selectedCategories.value = response.data.recommended_categories || []

      } catch (error) {
        console.error('Failed to discover actions:', error)
        alert('Failed to discover actions: ' + (error.response?.data?.error || error.message))
      } finally {
        discovering.value = false
      }
    }

    const toggleCategory = (categoryName) => {
      const index = selectedCategories.value.indexOf(categoryName)
      if (index > -1) {
        selectedCategories.value.splice(index, 1)
      } else {
        selectedCategories.value.push(categoryName)
      }
    }

    const getTotalSelectedActions = () => {
      if (!discoveredData.value) return 0
      return selectedCategories.value.reduce((total, catName) => {
        return total + (discoveredData.value.categories[catName]?.count || 0)
      }, 0)
    }

    const nextStep = () => {
      if (currentStep.value < steps.length - 1) {
        currentStep.value++
      }
    }

    const registerService = async () => {
      registering.value = true
      try {
        // Step 1: Create service
        const serviceResponse = await axios.post('/services/create/', {
          name: formData.value.name,
          description: formData.value.description,
          category: formData.value.category,
          icon: formData.value.icon,
          base_url: formData.value.base_url,
          auth_type: formData.value.auth_type,
          auth_config: formData.value.auth_config,
          api_spec_url: formData.value.api_spec_url
        })

        const serviceId = serviceResponse.data.service_id

        // Step 2: Create actions for selected categories
        if (discoveredData.value && selectedCategories.value.length > 0) {
          const actionsToCreate = []

          selectedCategories.value.forEach(categoryName => {
            const category = discoveredData.value.categories[categoryName]
            if (category && category.actions) {
              actionsToCreate.push(...category.actions.map(action => ({
                name: action.name,
                action_group: categoryName,
                description: action.description,
                endpoint_path: action.endpoint_path,
                http_method: action.http_method,
                parameters: action.parameters,
                execution_pattern: action.execution_pattern || 'simple'
              })))
            }
          })

          if (actionsToCreate.length > 0) {
            await axios.post(`/services/${serviceId}/actions/create/`, {
              actions: actionsToCreate
            })
          }
        }

        emit('registered')

      } catch (error) {
        console.error('Failed to register service:', error)
        alert('Failed to register service: ' + (error.response?.data?.error || error.message))
      } finally {
        registering.value = false
      }
    }

    return {
      currentStep,
      discovering,
      registering,
      steps,
      stepDescriptions,
      formData,
      discoveredData,
      selectedCategories,
      canProceed,
      discoverActions,
      toggleCategory,
      getTotalSelectedActions,
      nextStep,
      registerService
    }
  }
}
</script>
