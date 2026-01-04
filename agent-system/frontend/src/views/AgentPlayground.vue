<template>
  <div class="agent-playground h-screen flex flex-col bg-gray-100 overflow-hidden">
    
    <!-- Top Bar: Context & Actions -->
    <div class="h-14 bg-white border-b border-gray-200 flex items-center justify-between px-4 shrink-0 shadow-sm z-10">
        <div class="flex items-center gap-4">
            <button @click="$router.push('/agents')" class="text-gray-500 hover:text-gray-700">
                ← Back
            </button>
            <div class="h-6 w-px bg-gray-200"></div>
            <h1 class="text-lg font-bold text-gray-800">
                {{ agent.id ? 'Edit Agent' : 'New Agent' }}
            </h1>
        </div>

        <!-- Run Controls -->
        <div class="flex items-center gap-3">
             <select v-model="selectedContext.system" class="text-sm border-gray-300 rounded-md shadow-sm">
                <option :value="null">Select System...</option>
                <option v-for="s in systems" :key="s.id" :value="s.id">{{ s.name }}</option>
             </select>
             
             <select v-model="selectedContext.repo" class="text-sm border-gray-300 rounded-md shadow-sm">
                 <option :value="null">Select Repository...</option>
                 <option v-for="r in repositories" :key="r.id" :value="r.id">{{ r.name }}</option>
             </select>

             <button 
                @click="runAgent"
                class="px-4 py-1.5 bg-green-600 text-white rounded hover:bg-green-700 transition flex items-center gap-2 text-sm font-bold"
             >
                ▶ Run
             </button>
        </div>
    </div>

    <!-- Main Workspace -->
    <div class="flex-1 flex overflow-hidden">
        
        <!-- Left: Builder -->
        <AgentBuilder 
            v-if="agent"
            v-model:agent="agent"
            :isSaving="saving"
            @save="saveAgent"
        />

        <!-- Right: Preview / Chat -->
        <div class="flex-1 flex flex-col bg-white relative">
            <div class="p-2 border-b border-gray-100 bg-gray-50 text-xs text-gray-400 text-center font-mono">
                PREVIEW SESSION
            </div>
            
            <div class="flex-1 flex items-center justify-center text-gray-400 h-full" v-if="!activeSessionId">
                <div class="text-center">
                    <div class="text-4xl mb-2">💬</div>
                    <p>Click "Run" to start testing this agent.</p>
                </div>
            </div>

            <!-- We will mount the actual Chat Component here later -->
            <div v-if="activeSessionId" class="flex-1 overflow-hidden p-4">
                 <div class="bg-blue-50 p-4 rounded text-blue-800">
                    Session Started: {{ activeSessionId }}
                    <br>
                    (Chat Interface Integration Needed)
                 </div>
            </div>
        </div>

    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import api from '../services/api';
import AgentBuilder from '../components/AgentBuilder.vue';

const route = useRoute();
const router = useRouter();

const agent = ref({
    name: 'New Agent',
    description: '',
    system_prompt_template: 'You are a helpful AI assistant enabled with tools.',
    knowledge_scope: 'system',
    tool_ids: [],
    temperature: 0.7
});

const saving = ref(false);
const systems = ref([]);
const repositories = ref([]);
const selectedContext = ref({ system: null, repo: null });
const activeSessionId = ref(null);

const fetchContextData = async () => {
    try {
        const [sysRes, repoRes] = await Promise.all([
            api.get('/systems/'),
             // In real app, repos depend on system, simplifying for now
             // Using a generic call or mocking empty
             Promise.resolve({ data: { results: [] } }) 
        ]);
        systems.value = sysRes.data.results || sysRes.data;
    } catch (e) {
        console.error("Context load failed", e);
    }
};

const fetchAgent = async (id) => {
    try {
        const res = await api.get(`/agents/${id}/`);
        // Ensure tool_ids maps to tools objects if API returns expanded objects
        // The serializer expects tool_ids for write, but read might separate them
        const data = res.data;
        if (!data.tool_ids && data.tools) {
            data.tool_ids = data.tools.map(t => t.id);
        }
        agent.value = data;
    } catch (e) {
        console.error("Agent load failed", e);
    }
};

const saveAgent = async () => {
    try {
        saving.value = true;
        let res;
        if (agent.value.id) {
            res = await api.patch(`/agents/${agent.value.id}/`, agent.value);
        } else {
            res = await api.post('/agents/', agent.value);
            // Redirect to edit mode to prevent duplicate creates
            router.replace(`/agents/${res.data.id}`);
        }
        agent.value = res.data;
        // Fix up tool ids again if needed
        if (!agent.value.tool_ids && agent.value.tools) {
            agent.value.tool_ids = agent.value.tools.map(t => t.id);
        }
    } catch (e) {
        alert("Failed to save agent: " + (e.response?.data?.error || e.message));
    } finally {
        saving.value = false;
    }
};

const runAgent = async () => {
    if (agent.value.knowledge_scope === 'system' && !selectedContext.value.system) {
        alert("Please select a System Context for this agent.");
        return;
    }

    try {
        // Save first (auto-save behavior)
        if (!agent.value.id) await saveAgent();
        
        // Start Chat
        const res = await api.post(`/agents/${agent.value.id}/chat/`, {
            system_id: selectedContext.value.system,
            repository_id: selectedContext.value.repo
        });
        
        activeSessionId.value = res.data.profile_id; // Using profile_id as mock session for now per backend stub
        
    } catch (e) {
        alert("Run failed: " + e.message);
    }
};

onMounted(() => {
    fetchContextData();
    if (route.params.id && route.params.id !== 'new') {
        fetchAgent(route.params.id);
    }
});
</script>
