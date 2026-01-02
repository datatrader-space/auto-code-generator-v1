<template>
  <div v-if="show" class="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
    <div class="bg-white rounded-lg shadow-2xl max-w-3xl w-full max-h-[90vh] overflow-hidden flex flex-col">
      <!-- Header -->
      <div class="bg-gradient-to-r from-blue-600 to-blue-700 text-white px-6 py-4 flex items-center justify-between">
        <div>
          <h2 class="text-xl font-bold">Register New Tool</h2>
          <p class="text-sm text-white/80 mt-1">Add a remote service or create a YAML-based tool</p>
        </div>
        <button
          @click="$emit('close')"
          class="text-white/80 hover:text-white text-2xl leading-none"
        >
          ×
        </button>
      </div>

      <!-- Tab Selector -->
      <div class="border-b border-gray-200 bg-gray-50">
        <div class="flex">
          <button
            @click="activeTab = 'remote'"
            class="flex-1 px-6 py-3 text-sm font-medium transition"
            :class="activeTab === 'remote' ? 'bg-white text-blue-600 border-b-2 border-blue-600' : 'text-gray-600 hover:text-gray-800'"
          >
            🌐 Remote Tool
          </button>
          <button
            @click="activeTab = 'yaml'"
            class="flex-1 px-6 py-3 text-sm font-medium transition"
            :class="activeTab === 'yaml' ? 'bg-white text-blue-600 border-b-2 border-blue-600' : 'text-gray-600 hover:text-gray-800'"
          >
            📝 YAML Tool
          </button>
          <button
            @click="activeTab = 'help'"
            class="flex-1 px-6 py-3 text-sm font-medium transition"
            :class="activeTab === 'help' ? 'bg-white text-blue-600 border-b-2 border-blue-600' : 'text-gray-600 hover:text-gray-800'"
          >
            ❓ Help
          </button>
        </div>
      </div>

      <!-- Content -->
      <div class="flex-1 overflow-y-auto p-6">
        <!-- Remote Tool Form -->
        <div v-if="activeTab === 'remote'">
          <div class="space-y-4">
            <!-- Basic Info -->
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">Tool Name *</label>
              <input
                v-model="remoteForm.name"
                type="text"
                placeholder="e.g., JIRA_CREATE_ISSUE"
                class="w-full px-3 py-2 border border-gray-300 rounded focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
              <p class="text-xs text-gray-500 mt-1">Uppercase with underscores</p>
            </div>

            <div class="grid grid-cols-2 gap-4">
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">Category *</label>
                <input
                  v-model="remoteForm.category"
                  type="text"
                  placeholder="e.g., jira"
                  class="w-full px-3 py-2 border border-gray-300 rounded focus:ring-2 focus:ring-blue-500"
                />
              </div>
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">Version</label>
                <input
                  v-model="remoteForm.version"
                  type="text"
                  placeholder="1.0.0"
                  class="w-full px-3 py-2 border border-gray-300 rounded focus:ring-2 focus:ring-blue-500"
                />
              </div>
            </div>

            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">Description *</label>
              <textarea
                v-model="remoteForm.description"
                rows="2"
                placeholder="Describe what this tool does"
                class="w-full px-3 py-2 border border-gray-300 rounded focus:ring-2 focus:ring-blue-500"
              ></textarea>
            </div>

            <!-- Endpoint Configuration -->
            <div class="border-t pt-4">
              <h3 class="font-medium text-gray-900 mb-3">Endpoint Configuration</h3>

              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">Endpoint URL *</label>
                <input
                  v-model="remoteForm.endpoint_url"
                  type="url"
                  placeholder="https://api.example.com/tools/action"
                  class="w-full px-3 py-2 border border-gray-300 rounded focus:ring-2 focus:ring-blue-500"
                />
              </div>

              <div class="grid grid-cols-2 gap-4 mt-4">
                <div>
                  <label class="block text-sm font-medium text-gray-700 mb-1">HTTP Method</label>
                  <select
                    v-model="remoteForm.method"
                    class="w-full px-3 py-2 border border-gray-300 rounded focus:ring-2 focus:ring-blue-500"
                  >
                    <option value="POST">POST</option>
                    <option value="GET">GET</option>
                    <option value="PUT">PUT</option>
                    <option value="DELETE">DELETE</option>
                  </select>
                </div>
                <div>
                  <label class="block text-sm font-medium text-gray-700 mb-1">Timeout (seconds)</label>
                  <input
                    v-model.number="remoteForm.timeout"
                    type="number"
                    min="5"
                    max="300"
                    class="w-full px-3 py-2 border border-gray-300 rounded focus:ring-2 focus:ring-blue-500"
                  />
                </div>
              </div>
            </div>

            <!-- Authentication -->
            <div class="border-t pt-4">
              <h3 class="font-medium text-gray-900 mb-3">Authentication (Optional)</h3>

              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">Auth Type</label>
                <select
                  v-model="remoteForm.auth_type"
                  class="w-full px-3 py-2 border border-gray-300 rounded focus:ring-2 focus:ring-blue-500"
                >
                  <option :value="null">None</option>
                  <option value="bearer">Bearer Token</option>
                  <option value="api_key">API Key</option>
                  <option value="basic">Basic Auth</option>
                </select>
              </div>

              <div v-if="remoteForm.auth_type === 'bearer'" class="mt-3">
                <label class="block text-sm font-medium text-gray-700 mb-1">Bearer Token</label>
                <input
                  v-model="remoteForm.auth_token"
                  type="password"
                  placeholder="Enter token"
                  class="w-full px-3 py-2 border border-gray-300 rounded focus:ring-2 focus:ring-blue-500"
                />
              </div>

              <div v-if="remoteForm.auth_type === 'api_key'" class="mt-3 space-y-3">
                <div>
                  <label class="block text-sm font-medium text-gray-700 mb-1">API Key Header Name</label>
                  <input
                    v-model="remoteForm.auth_key_name"
                    type="text"
                    placeholder="X-API-Key"
                    class="w-full px-3 py-2 border border-gray-300 rounded focus:ring-2 focus:ring-blue-500"
                  />
                </div>
                <div>
                  <label class="block text-sm font-medium text-gray-700 mb-1">API Key Value</label>
                  <input
                    v-model="remoteForm.auth_api_key"
                    type="password"
                    placeholder="Enter API key"
                    class="w-full px-3 py-2 border border-gray-300 rounded focus:ring-2 focus:ring-blue-500"
                  />
                </div>
              </div>

              <div v-if="remoteForm.auth_type === 'basic'" class="mt-3 space-y-3">
                <div>
                  <label class="block text-sm font-medium text-gray-700 mb-1">Username</label>
                  <input
                    v-model="remoteForm.auth_username"
                    type="text"
                    class="w-full px-3 py-2 border border-gray-300 rounded focus:ring-2 focus:ring-blue-500"
                  />
                </div>
                <div>
                  <label class="block text-sm font-medium text-gray-700 mb-1">Password</label>
                  <input
                    v-model="remoteForm.auth_password"
                    type="password"
                    class="w-full px-3 py-2 border border-gray-300 rounded focus:ring-2 focus:ring-blue-500"
                  />
                </div>
              </div>
            </div>

            <!-- Parameters -->
            <div class="border-t pt-4">
              <div class="flex items-center justify-between mb-3">
                <h3 class="font-medium text-gray-900">Parameters</h3>
                <button
                  @click="addParameter"
                  class="text-sm text-blue-600 hover:text-blue-700 font-medium"
                >
                  + Add Parameter
                </button>
              </div>

              <div v-if="remoteForm.parameters.length === 0" class="text-sm text-gray-500 italic">
                No parameters defined yet
              </div>

              <div v-for="(param, idx) in remoteForm.parameters" :key="idx" class="bg-gray-50 border border-gray-200 rounded p-3 mb-2">
                <div class="grid grid-cols-2 gap-2">
                  <input
                    v-model="param.name"
                    placeholder="Parameter name"
                    class="px-2 py-1 text-sm border border-gray-300 rounded"
                  />
                  <select v-model="param.type" class="px-2 py-1 text-sm border border-gray-300 rounded">
                    <option value="string">String</option>
                    <option value="int">Integer</option>
                    <option value="bool">Boolean</option>
                    <option value="choice">Choice</option>
                    <option value="list">List</option>
                  </select>
                </div>
                <input
                  v-model="param.description"
                  placeholder="Description"
                  class="w-full mt-2 px-2 py-1 text-sm border border-gray-300 rounded"
                />
                <div class="flex items-center justify-between mt-2">
                  <label class="flex items-center text-sm">
                    <input v-model="param.required" type="checkbox" class="mr-1" />
                    Required
                  </label>
                  <button
                    @click="removeParameter(idx)"
                    class="text-xs text-red-600 hover:text-red-700"
                  >
                    Remove
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- YAML Tool Form -->
        <div v-if="activeTab === 'yaml'">
          <div class="space-y-4">
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">Tool Name *</label>
              <input
                v-model="yamlForm.name"
                type="text"
                placeholder="e.g., CUSTOM_COMMAND"
                class="w-full px-3 py-2 border border-gray-300 rounded focus:ring-2 focus:ring-blue-500"
              />
            </div>

            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">YAML Definition *</label>
              <textarea
                v-model="yamlForm.yaml_definition"
                rows="15"
                placeholder="tool:
  name: CUSTOM_COMMAND
  category: custom
  description: My custom tool
  parameters:
    - name: arg1
      type: string
      required: true
  execution:
    type: shell_command
    template: 'echo {{ arg1 }}'"
                class="w-full px-3 py-2 border border-gray-300 rounded font-mono text-sm focus:ring-2 focus:ring-blue-500"
              ></textarea>
              <p class="text-xs text-gray-500 mt-1">See the Help tab for YAML syntax examples</p>
            </div>
          </div>
        </div>

        <!-- Help Content -->
        <div v-if="activeTab === 'help'" class="prose prose-sm max-w-none">
          <h3>Remote Tools</h3>
          <p>Remote tools allow external services to integrate with the agent system. Your service should expose an HTTP endpoint that:</p>
          <ul>
            <li>Accepts POST requests with JSON: <code>{"parameters": {...}, "context": {...}}</code></li>
            <li>Returns JSON: <code>{"success": true/false, "output": "...", "error": "..."}</code></li>
          </ul>

          <h3>YAML Tools</h3>
          <p>YAML tools are defined declaratively and support various execution types:</p>

          <h4>Shell Command Example:</h4>
          <pre class="bg-gray-100 p-3 rounded text-xs overflow-x-auto">tool:
  name: MY_COMMAND
  category: custom
  description: Run a custom shell command
  parameters:
    - name: path
      type: string
      required: true
      description: Target path
  execution:
    type: shell_command
    template: 'ls -la {{ path }}'
    timeout: 30</pre>

          <h4>Smart Command Example:</h4>
          <pre class="bg-gray-100 p-3 rounded text-xs overflow-x-auto">tool:
  name: RUN_TESTS
  execution:
    type: smart_command
    detect_from_files:
      - pattern: "pytest.ini"
        command: pytest {{ path }}
      - pattern: "package.json"
        command: npm test</pre>

          <h4>Parameter Types:</h4>
          <ul class="text-sm">
            <li><code>string</code> - Text input</li>
            <li><code>int</code> - Integer number</li>
            <li><code>bool</code> - True/false</li>
            <li><code>choice</code> - Select from options</li>
            <li><code>list</code> - Array of values</li>
            <li><code>path</code> - File/directory path</li>
          </ul>
        </div>
      </div>

      <!-- Footer -->
      <div class="border-t border-gray-200 px-6 py-4 bg-gray-50 flex justify-end gap-3">
        <button
          @click="$emit('close')"
          class="px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100 rounded transition"
        >
          Cancel
        </button>
        <button
          v-if="activeTab !== 'help'"
          @click="submitTool"
          :disabled="!isFormValid"
          class="px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded transition disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {{ submitting ? 'Registering...' : 'Register Tool' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, computed } from 'vue'
import axios from 'axios'

export default {
  name: 'RegisterToolModal',
  props: {
    show: Boolean
  },
  emits: ['close', 'registered'],
  setup(props, { emit }) {
    const activeTab = ref('remote')
    const submitting = ref(false)

    const remoteForm = ref({
      name: '',
      category: '',
      description: '',
      version: '1.0.0',
      endpoint_url: '',
      method: 'POST',
      timeout: 30,
      auth_type: null,
      auth_token: '',
      auth_key_name: 'X-API-Key',
      auth_api_key: '',
      auth_username: '',
      auth_password: '',
      parameters: []
    })

    const yamlForm = ref({
      name: '',
      yaml_definition: ''
    })

    const addParameter = () => {
      remoteForm.value.parameters.push({
        name: '',
        type: 'string',
        required: true,
        description: ''
      })
    }

    const removeParameter = (index) => {
      remoteForm.value.parameters.splice(index, 1)
    }

    const isFormValid = computed(() => {
      if (activeTab.value === 'remote') {
        return remoteForm.value.name &&
               remoteForm.value.category &&
               remoteForm.value.description &&
               remoteForm.value.endpoint_url
      } else if (activeTab.value === 'yaml') {
        return yamlForm.value.name && yamlForm.value.yaml_definition
      }
      return false
    })

    const submitTool = async () => {
      submitting.value = true

      try {
        if (activeTab.value === 'remote') {
          // Build auth_config
          let authConfig = null
          if (remoteForm.value.auth_type === 'bearer') {
            authConfig = { token: remoteForm.value.auth_token }
          } else if (remoteForm.value.auth_type === 'api_key') {
            authConfig = {
              key_name: remoteForm.value.auth_key_name,
              api_key: remoteForm.value.auth_api_key
            }
          } else if (remoteForm.value.auth_type === 'basic') {
            authConfig = {
              username: remoteForm.value.auth_username,
              password: remoteForm.value.auth_password
            }
          }

          const payload = {
            name: remoteForm.value.name,
            category: remoteForm.value.category,
            description: remoteForm.value.description,
            version: remoteForm.value.version,
            endpoint_url: remoteForm.value.endpoint_url,
            method: remoteForm.value.method,
            timeout: remoteForm.value.timeout,
            auth_type: remoteForm.value.auth_type,
            auth_config: authConfig,
            parameters: remoteForm.value.parameters
          }

          await axios.post('/tools/register/remote/', payload)
        } else if (activeTab.value === 'yaml') {
          await axios.post('/tools/create/yaml/', {
            name: yamlForm.value.name,
            yaml_definition: yamlForm.value.yaml_definition
          })
        }

        emit('registered')
        emit('close')
      } catch (error) {
        alert(`Failed to register tool: ${error.response?.data?.error || error.message}`)
      } finally {
        submitting.value = false
      }
    }

    return {
      activeTab,
      submitting,
      remoteForm,
      yamlForm,
      addParameter,
      removeParameter,
      isFormValid,
      submitTool
    }
  }
}
</script>

<style scoped>
.prose code {
  background: #f3f4f6;
  padding: 2px 4px;
  border-radius: 3px;
  font-size: 0.875em;
}

.prose pre {
  background: #f3f4f6;
  padding: 1rem;
  border-radius: 0.375rem;
  overflow-x: auto;
}
</style>
