<template>
  <div class="modal-overlay fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50" @click.self="$emit('close')">
    <div class="modal-content bg-white rounded-lg shadow-xl w-full max-w-2xl max-h-[90vh] overflow-y-auto">
      <!-- Header -->
      <div class="sticky top-0 bg-white border-b border-gray-200 px-6 py-4">
        <div class="flex items-center justify-between">
          <h2 class="text-2xl font-bold text-gray-900">Execute: {{ tool.name }}</h2>
          <button @click="$emit('close')" class="text-gray-400 hover:text-gray-600 text-2xl">×</button>
        </div>
        <p class="text-sm text-gray-600 mt-1">{{ tool.description }}</p>
      </div>

      <!-- Form -->
      <div class="px-6 py-4 space-y-4">
        <!-- Repository Selection -->
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-2">
            Repository <span class="text-red-500">*</span>
          </label>
          <select
            v-model="selectedRepositoryId"
            class="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            required
          >
            <option value="">Select repository...</option>
            <option v-for="repo in repositories" :key="repo.id" :value="repo.id">
              {{ repo.name }} ({{ repo.system_name || 'System' }})
            </option>
          </select>
        </div>

        <!-- Tool Parameters -->
        <div class="border border-gray-200 rounded-lg p-4 bg-gray-50">
          <h3 class="text-sm font-medium text-gray-900 mb-3">Parameters</h3>

          <div v-if="tool.parameters.length === 0" class="text-sm text-gray-500 italic">
            No parameters required
          </div>

          <div v-else class="space-y-3">
            <div v-for="param in tool.parameters" :key="param.name">
              <label class="block text-sm font-medium text-gray-700 mb-1">
                {{ param.name }}
                <span v-if="param.required" class="text-red-500">*</span>
                <span v-if="!param.required" class="text-gray-400 text-xs">(optional)</span>
              </label>

              <p v-if="param.description" class="text-xs text-gray-500 mb-1">
                {{ param.description }}
              </p>

              <!-- Text/String Input -->
              <input
                v-if="param.type === 'string' || param.type === 'path'"
                v-model="parameterValues[param.name]"
                :type="param.type === 'path' ? 'text' : 'text'"
                :placeholder="param.default || `Enter ${param.name}...`"
                :required="param.required"
                class="w-full px-3 py-2 border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
              />

              <!-- Number Input -->
              <input
                v-else-if="param.type === 'int'"
                v-model.number="parameterValues[param.name]"
                type="number"
                :placeholder="param.default || '0'"
                :required="param.required"
                class="w-full px-3 py-2 border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
              />

              <!-- Boolean Input -->
              <div v-else-if="param.type === 'bool'" class="flex items-center">
                <input
                  v-model="parameterValues[param.name]"
                  type="checkbox"
                  :id="`param-${param.name}`"
                  class="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded"
                />
                <label :for="`param-${param.name}`" class="ml-2 text-sm text-gray-700">
                  Enable {{ param.name }}
                </label>
              </div>

              <!-- Choice Input -->
              <select
                v-else-if="param.type === 'choice' && param.choices"
                v-model="parameterValues[param.name]"
                :required="param.required"
                class="w-full px-3 py-2 border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
              >
                <option value="">Select {{ param.name }}...</option>
                <option v-for="choice in param.choices" :key="choice" :value="choice">
                  {{ choice }}
                </option>
              </select>

              <!-- List Input (comma-separated) -->
              <input
                v-else-if="param.type === 'list'"
                v-model="parameterValues[param.name]"
                type="text"
                :placeholder="`Enter ${param.name} (comma-separated)...`"
                :required="param.required"
                class="w-full px-3 py-2 border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
              />

              <!-- Textarea for long strings -->
              <textarea
                v-else-if="param.name === 'content' || param.name === 'code' || param.name === 'message'"
                v-model="parameterValues[param.name]"
                :placeholder="param.default || `Enter ${param.name}...`"
                :required="param.required"
                rows="4"
                class="w-full px-3 py-2 border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm font-mono"
              />

              <!-- Default: text input -->
              <input
                v-else
                v-model="parameterValues[param.name]"
                type="text"
                :placeholder="param.default || `Enter ${param.name}...`"
                :required="param.required"
                class="w-full px-3 py-2 border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
              />
            </div>
          </div>
        </div>

        <!-- Session ID (Optional) -->
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-2">
            Session ID (optional)
          </label>
          <input
            v-model="sessionId"
            type="text"
            placeholder="Auto-generated if not provided"
            class="w-full px-3 py-2 border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
          />
        </div>

        <!-- Example -->
        <div v-if="tool.examples && tool.examples.length > 0" class="bg-blue-50 border border-blue-200 rounded-lg p-3">
          <div class="text-xs font-medium text-blue-900 mb-2">💡 Example:</div>
          <pre class="text-xs text-blue-800 overflow-x-auto">{{ tool.examples[0] }}</pre>
        </div>
      </div>

      <!-- Footer -->
      <div class="sticky bottom-0 bg-gray-50 border-t border-gray-200 px-6 py-4 flex justify-end gap-3">
        <button
          @click="$emit('close')"
          class="px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-100 transition"
        >
          Cancel
        </button>
        <button
          @click="executeToolNow"
          :disabled="!canExecute"
          class="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition disabled:bg-gray-300 disabled:cursor-not-allowed"
        >
          ▶️ Execute Tool
        </button>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, computed, watch } from 'vue'

export default {
  name: 'ToolExecuteModal',
  props: {
    tool: {
      type: Object,
      required: true
    },
    repositories: {
      type: Array,
      default: () => []
    }
  },
  emits: ['close', 'execute'],
  setup(props, { emit }) {
    const selectedRepositoryId = ref('')
    const sessionId = ref('')
    const parameterValues = ref({})

    // Initialize default values
    watch(() => props.tool, (tool) => {
      if (tool) {
        tool.parameters.forEach(param => {
          if (param.default !== null && param.default !== undefined) {
            parameterValues.value[param.name] = param.default
          }
        })
      }
    }, { immediate: true })

    const canExecute = computed(() => {
      if (!selectedRepositoryId.value) return false

      // Check required parameters
      for (const param of props.tool.parameters) {
        if (param.required && !parameterValues.value[param.name]) {
          return false
        }
      }

      return true
    })

    const executeToolNow = () => {
      // Process list parameters (convert comma-separated string to array)
      const processedParams = { ...parameterValues.value }
      for (const param of props.tool.parameters) {
        if (param.type === 'list' && typeof processedParams[param.name] === 'string') {
          processedParams[param.name] = processedParams[param.name]
            .split(',')
            .map(s => s.trim())
            .filter(s => s.length > 0)
        }
      }

      emit('execute', {
        tool: props.tool,
        repository_id: selectedRepositoryId.value,
        session_id: sessionId.value || undefined,
        parameters: processedParams
      })
    }

    return {
      selectedRepositoryId,
      sessionId,
      parameterValues,
      canExecute,
      executeToolNow
    }
  }
}
</script>
