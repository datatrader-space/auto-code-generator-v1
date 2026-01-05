<template>
  <div class="agent-builder flex flex-col h-full bg-white border-r border-gray-200 w-96 md:w-[450px] shrink-0">
    <div class="p-4 border-b border-gray-200 flex justify-between items-center bg-gray-50">
      <h2 class="font-bold text-gray-800">Agent Configuration</h2>
      <div class="flex gap-2">
        <button 
            @click="save" 
            :disabled="isSaving"
            class="px-3 py-1.5 bg-indigo-600 text-white text-sm rounded hover:bg-indigo-700 disabled:opacity-50"
        >
            {{ isSaving ? 'Saving...' : 'Save Agent' }}
        </button>
      </div>
    </div>

    <div class="flex-1 overflow-y-auto p-4 space-y-6">
      
      <!-- Identity -->
      <div class="space-y-4">
        <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Name</label>
            <input 
                v-model="internalAgent.name"
                class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                placeholder="e.g. Django Migration Expert"
            />
        </div>
        <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Description</label>
            <textarea 
                v-model="internalAgent.description"
                rows="2"
                class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:outline-none resize-none"
                placeholder="What does this agent do?"
            ></textarea>
        </div>
      </div>

      <hr />

      <!-- Soul (Prompt) & Model -->
      <div class="space-y-4">
        <div>
             <label class="block text-sm font-medium text-gray-700 mb-1">Default Model</label>
             <select 
                ref="modelSelect"
                :value="internalAgent.default_model || ''"
                class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:outline-none bg-white"
             >
                <option :value="null">Select a model...</option>
                <option v-for="m in llmModels" :key="m.id" :value="m.id">
                    {{ m.name }} ({{ m.provider_name }})
                </option>
             </select>
        </div>
        <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">
                System Prompt
                <span v-pre class="text-xs font-normal text-gray-500 ml-1">(Use {{tools}} for automatic injection)</span>
            </label>
        <div class="relative">
            <textarea 
                v-model="internalAgent.system_prompt_template"
                rows="8"
                class="w-full px-3 py-2 font-mono text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:outline-none bg-gray-50"
                placeholder="You are a helpful assistant..."
            ></textarea>
        </div>
      </div>
      </div>

      <hr />

      <!-- Knowledge -->


      <hr />

      <!-- Agent Knowledge Base -->
      <div>
        <label class="block text-sm font-medium text-gray-700 mb-2">Knowledge Base & Files</label>
        <div class="space-y-3">
             <!-- Upload -->
            <div class="flex gap-2">
                <input 
                    type="file" 
                    ref="fileInput"
                    class="hidden" 
                    @change="handleFileUpload"
                />
                <button 
                    @click="$refs.fileInput.click()"
                    class="flex-1 px-3 py-2 border border-gray-300 border-dashed rounded-lg text-sm text-gray-500 hover:bg-gray-50 hover:text-indigo-600 transition flex items-center justify-center gap-2"
                    :disabled="uploading"
                >
                    <span v-if="uploading">Uploading...</span>
                    <span v-else>+ Upload Knowledge File</span>
                </button>
            </div>

            <!-- File List -->
            <div class="space-y-2">
                <!-- If no files -->
                <div v-if="(!internalAgent.knowledge_files || internalAgent.knowledge_files.length === 0)" class="text-xs text-gray-400 text-center italic py-2">
                    No files uploaded. Agent relies on prompt only.
                </div>

                <div 
                    v-for="file in internalAgent.knowledge_files" 
                    :key="file.id"
                    class="group relative bg-white border border-gray-200 rounded-lg p-3 hover:border-indigo-300 transition"
                >
                    <!-- Header -->
                    <div class="flex justify-between items-start mb-1">
                        <div class="font-medium text-sm text-gray-800 truncate pr-4">{{ file.name }}</div>
                        <button 
                             class="text-gray-400 hover:text-red-500 opacity-0 group-hover:opacity-100 transition"
                             title="Remove (Database only)"
                        >
                            ×
                        </button>
                    </div>

                    <!-- Analysis Preview -->
                    <div v-if="file.analysis" class="text-xs text-gray-600 bg-gray-50 p-2 rounded mt-1 line-clamp-3">
                        <span class="font-bold text-indigo-600">AI Analysis:</span> {{ file.analysis }}
                    </div>
                    <div v-else class="text-xs text-gray-400 italic mt-1">
                        Analysis pending...
                    </div>
                </div>
            </div>
        </div>
      </div>

      <hr />

      <!-- Tools -->
      <div>
        <div class="flex justify-between items-center mb-2">
             <label class="block text-sm font-medium text-gray-700">Capabilities (Tools)</label>
             <span class="text-xs text-gray-500">{{ selectedToolsCount }} selected</span>
        </div>
        
        <div class="border border-gray-200 rounded-lg divide-y divide-gray-100 max-h-60 overflow-y-auto">
            <div v-if="loadingTools" class="p-4 text-center text-sm text-gray-500">Loading tools...</div>
            <div 
                v-else
                v-for="tool in availableTools" 
                :key="tool.id"
                class="flex items-start p-3 hover:bg-gray-50 cursor-pointer"
                @click="toggleTool(tool.id)"
            >
                <div class="flex items-center h-5">
                    <input 
                        type="checkbox" 
                        :checked="internalAgent.tool_ids.includes(tool.id)"
                        class="h-4 w-4 text-indigo-600 border-gray-300 rounded focus:ring-indigo-500"
                    />
                </div>
                <div class="ml-3 text-sm">
                    <label class="font-medium text-gray-700 cursor-pointer">{{ tool.name }}</label>
                    <p class="text-gray-500 text-xs">{{ tool.description }}</p>
                </div>
            </div>
        </div>
      </div>

    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue';
import api from '../services/api';

const props = defineProps({
    agent: {
        type: Object,
        required: true
    },
    isSaving: {
        type: Boolean,
        default: false
    }
});

const emit = defineEmits(['update:agent', 'save']);

// Local copy for editing
const internalAgent = ref({ 
    default_model: null,  // Ensure this property exists for Vue reactivity
    ...props.agent 
});
const availableTools = ref([]);
const llmModels = ref([]);
const loadingTools = ref(false);
const isUpdatingFromProp = ref(false);
const uploading = ref(false);
const fileInput = ref(null);
const modelSelect = ref(null);

const scopes = [
    { value: 'system', label: 'Full System' },
    { value: 'repository', label: 'Repository' },
    { value: 'none', label: 'None' }
];

const getScopeDescription = (scope) => {
    const map = {
        'system': 'Agent can access documentation and code across the entire system.',
        'repository': 'Agent is restricted to the specific repository it is launched in.',
        'none': 'No RAG access. Pure logic and external tools only.'
    };
    return map[scope] || '';
};

const selectedToolsCount = computed(() => {
    return internalAgent.value.tool_ids ? internalAgent.value.tool_ids.length : 0;
});

const fetchTools = async () => {
    try {
        loadingTools.value = true;
        // Fetch ALL pages of ToolDefinitions from our API
        let allTools = [];
        let nextUrl = '/tools/definitions/';

        while (nextUrl) {
            const response = await api.get(nextUrl);
            const data = response.data;

            // Add results from this page
            if (data.results) {
                allTools = allTools.concat(data.results);
            } else {
                // Fallback for non-paginated response
                allTools = data;
                break;
            }

            // Get next page URL (extract path from full URL)
            if (data.next) {
                const url = new URL(data.next);
                nextUrl = url.pathname + url.search;
            } else {
                nextUrl = null;
            }
        }

        availableTools.value = allTools;
        console.log(`Loaded ${allTools.length} tools total`);
    } catch (e) {
        console.error("Failed to fetch tools", e);
    } finally {
        loadingTools.value = false;
    }
};

const fetchModels = async () => {
    try {
        console.log('Fetching LLM models...');
        const res = await api.getLlmModels();
        llmModels.value = res.data.results || res.data;
        console.log('Loaded models:', llmModels.value.length, 'models');
        console.log('Models:', llmModels.value.map(m => ({ id: m.id, name: m.name })));
    } catch (e) {
        console.error("Failed to fetch models", e);
    }
};

const toggleTool = (toolId) => {
    if (!internalAgent.value.tool_ids) {
        internalAgent.value.tool_ids = [];
    }
    
    const index = internalAgent.value.tool_ids.indexOf(toolId);
    if (index === -1) {
        internalAgent.value.tool_ids.push(toolId);
    } else {
        internalAgent.value.tool_ids.splice(index, 1);
    }
};

const save = () => {
    // Read the model selection directly from the form
    const selectedModel = modelSelect.value?.value;
    const modelId = selectedModel && selectedModel !== '' ? parseInt(selectedModel) : null;
    
    // Create the payload with the current form values
    const agentData = {
        ...internalAgent.value,
        default_model: modelId
    };
    
    console.log('Saving agent with default_model:', modelId);
    emit('save', agentData);
};

const handleFileUpload = async (event) => {
    const file = event.target.files[0];
    if (!file) return;

    if (!internalAgent.value.id) {
        alert("Please save the agent first to upload files.");
        return;
    }

    try {
        uploading.value = true;
        const res = await api.uploadAgentFile(internalAgent.value.id, file);
        
        // Add to list
        if (!internalAgent.value.knowledge_files) {
            internalAgent.value.knowledge_files = [];
        }
        internalAgent.value.knowledge_files.unshift(res.data);
        
        // Clear input
        if (fileInput.value) fileInput.value.value = '';
    } catch (e) {
        alert("Upload failed: " + (e.response?.data?.error || e.message));
    } finally {
        uploading.value = false;
    }
};

// Sync prop changes to internal
watch(() => props.agent, (newVal) => {
    isUpdatingFromProp.value = true;
    internalAgent.value = { 
        default_model: null,  // Ensure reactivity
        ...newVal 
    };
    // Ensure array exists
    if (!internalAgent.value.tool_ids) internalAgent.value.tool_ids = [];
    
    // Release lock after update propagates
    setTimeout(() => { isUpdatingFromProp.value = false; }, 0);
}, { deep: true });

// Sync internal changes to parent
watch(internalAgent, (newVal) => {
    if (isUpdatingFromProp.value) return;
    emit('update:agent', newVal);
}, { deep: true });

// Debug: Watch default_model specifically
watch(() => internalAgent.value.default_model, (newVal, oldVal) => {
    console.log('🔍 default_model changed from', oldVal, 'to', newVal);
}, { immediate: true });

onMounted(() => {
    fetchTools();
    fetchModels();
});
</script>
