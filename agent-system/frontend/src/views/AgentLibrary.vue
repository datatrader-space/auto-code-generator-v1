<template>
  <div class="agent-library-container p-6 bg-gray-50 min-h-screen">
    <div class="max-w-7xl mx-auto">
      <!-- Header -->
      <div class="flex justify-between items-center mb-8">
        <div>
          <h1 class="text-3xl font-bold text-gray-900">🤖 Agent Library</h1>
          <p class="text-gray-600 mt-1">Design, test, and deploy specialized AI agents</p>
        </div>
        <button
          @click="createAgent"
          class="px-5 py-2.5 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition font-medium flex items-center gap-2 shadow-sm"
        >
          <span class="text-xl">+</span>
          Create New Agent
        </button>
      </div>

      <!-- Loading State -->
      <div v-if="loading" class="text-center py-16">
        <div class="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600"></div>
        <p class="mt-4 text-gray-600">Loading agent profiles...</p>
      </div>

      <!-- Empty State -->
      <div v-else-if="agents.length === 0" class="text-center py-20 bg-white rounded-xl shadow-sm border border-gray-100">
        <div class="text-6xl mb-4">🧬</div>
        <h3 class="text-xl font-bold text-gray-900">No Agents Found</h3>
        <p class="text-gray-500 mt-2 mb-6">Create your first specialized agent to get started.</p>
        <button
          @click="createAgent"
          class="px-4 py-2 border border-indigo-600 text-indigo-600 rounded-lg hover:bg-indigo-50 transition font-medium"
        >
          Design an Agent
        </button>
      </div>

      <!-- Agent Grid -->
      <div v-else class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        <div 
          v-for="agent in agents" 
          :key="agent.id"
          class="bg-white rounded-xl shadow-sm border border-gray-200 hover:shadow-md transition-shadow duration-300 flex flex-col overflow-hidden"
        >
          <!-- Card Header / Icon -->
          <div class="p-6 pb-4 flex items-start justify-between bg-gradient-to-r from-gray-50 to-white border-b border-gray-100">
             <div class="w-12 h-12 rounded-lg bg-indigo-100 text-indigo-600 flex items-center justify-center text-2xl">
               🤖
             </div>
             <div class="flex gap-2">
                <span class="text-xs font-mono bg-gray-100 text-gray-600 px-2 py-1 rounded">
                    {{ agent.tools.length }} Tools
                </span>
             </div>
          </div>
          
          <!-- Content -->
          <div class="p-6 pt-4 flex-1">
            <h3 class="text-lg font-bold text-gray-900 mb-2 truncate">{{ agent.name }}</h3>
            <p class="text-gray-500 text-sm line-clamp-3 mb-4">
              {{ agent.description || "No description provided." }}
            </p>
            
            <div class="flex flex-wrap gap-2 mb-4">
                <span v-if="agent.knowledge_scope === 'system'" class="px-2 py-0.5 rounded text-xs bg-green-100 text-green-700 font-medium">System Context</span>
                <span v-if="agent.knowledge_scope === 'repository'" class="px-2 py-0.5 rounded text-xs bg-blue-100 text-blue-700 font-medium">Repo Context</span>
                <span v-if="agent.knowledge_scope === 'none'" class="px-2 py-0.5 rounded text-xs bg-gray-100 text-gray-600 font-medium">Isolated</span>
            </div>
          </div>

          <!-- Footer / Actions -->
          <div class="p-4 bg-gray-50 border-t border-gray-100 flex gap-3">
            <button
              @click="editAgent(agent.id)"
              class="flex-1 px-3 py-2 bg-white border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 transition text-sm font-medium"
            >
              Edit / Test
            </button>
            <button
               @click="launchSession(agent)"
               class="flex-1 px-3 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition text-sm font-medium"
            >
               Deploy
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import api from '../services/api';

const router = useRouter();
const loading = ref(true);
const agents = ref([]);

const fetchAgents = async () => {
    try {
        loading.value = true;
        const response = await api.get('/agents/');
        agents.value = response.data.results || response.data;
    } catch (e) {
        console.error("Failed to fetch agents", e);
    } finally {
        loading.value = false;
    }
};

const createAgent = () => {
    router.push('/agents/new'); // Opens Playground in 'new' mode
};

const editAgent = (id) => {
    router.push(`/agents/${id}`); // Opens Playground in 'edit' mode
};

const launchSession = (agent) => {
    // TODO: Open a modal to select System/Repo before launching
    alert("Launch feature coming soon! Use 'Edit / Test' to run in Playground.");
};

onMounted(() => {
    fetchAgents();
});
</script>
