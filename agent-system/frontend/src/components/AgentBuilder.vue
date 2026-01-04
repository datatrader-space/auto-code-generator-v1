<template>
  <div class="agent-builder flex flex-col h-full bg-white border-r border-gray-200 w-96 md:w-[450px] shrink-0">
    <div class="p-4 border-b border-gray-200 flex justify-between items-center bg-gray-50">
      <h2 class="font-bold text-gray-800">Agent Configuration</h2>
      <div class="flex gap-2">
        <button 
            @click="$emit('save')" 
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

      <!-- Soul (Prompt) -->
      <div>
        <label class="block text-sm font-medium text-gray-700 mb-1">
            System Prompt
            <span class="text-xs font-normal text-gray-500 ml-1">(Use {{tools}} for automatic injection)</span>
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

      <hr />

      <!-- Knowledge -->
      <div>
        <label class="block text-sm font-medium text-gray-700 mb-2">Knowledge Context</label>
        <div class="grid grid-cols-3 gap-2">
            <button 
                v-for="scope in scopes" 
                :key="scope.value"
                @click="internalAgent.knowledge_scope = scope.value"
                :class="[
                    'px-2 py-2 text-xs font-medium rounded border text-center transition-colors',
                    internalAgent.knowledge_scope === scope.value
                        ? 'bg-indigo-50 border-indigo-500 text-indigo-700 shadow-sm'
                        : 'bg-white border-gray-200 text-gray-600 hover:bg-gray-50'
                ]"
            >
                {{ scope.label }}
            </button>
        </div>
        <p class="text-xs text-gray-500 mt-2">
            {{ getScopeDescription(internalAgent.knowledge_scope) }}
        </p>
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
const internalAgent = ref({ ...props.agent });
const availableTools = ref([]);
const loadingTools = ref(false);
const isUpdatingFromProp = ref(false);

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
        // Fetch ToolDefinitions from our new API
        const response = await api.get('/tools/definitions/');
        availableTools.value = response.data.results || response.data;
    } catch (e) {
        console.error("Failed to fetch tools", e);
    } finally {
        loadingTools.value = false;
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

// Sync prop changes to internal
watch(() => props.agent, (newVal) => {
    isUpdatingFromProp.value = true;
    internalAgent.value = { ...newVal };
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

onMounted(() => {
    fetchTools();
});
</script>
