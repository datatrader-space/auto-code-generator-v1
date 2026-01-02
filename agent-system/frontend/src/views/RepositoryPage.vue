<template>
  <div class="repository-page h-full bg-gray-50 flex flex-col overflow-hidden font-sans text-gray-900">
    <!-- Clean Minimal Header -->
    <header class="h-14 bg-white border-b border-gray-200 flex items-center justify-between px-6 flex-shrink-0 z-10 w-full shadow-sm">
      <div class="flex items-center gap-4">
        <button 
          @click="goBack" 
          class="p-2 -ml-2 text-gray-400 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
          title="Back to System"
        >
          <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 19l-7-7m0 0l7-7m-7 7h18" />
          </svg>
        </button>
        <div class="flex flex-col">
          <h1 class="text-lg font-bold text-gray-900 leading-tight">
            {{ repository?.name || 'Loading...' }}
          </h1>
          <span v-if="repository" class="text-xs text-gray-500 font-mono tracking-tight opacity-75">
            {{ repository.url }}
          </span>
        </div>
      </div>
      
      <!-- Right Header Controls -->
      <div class="flex items-center gap-3">
         <!-- Context Panel Toggle -->
         <button 
           @click="toggleContextPanel"
           class="flex items-center gap-2 px-3 py-1.5 rounded-md text-sm font-medium transition-all duration-200"
           :class="isContextPanelOpen 
             ? 'bg-blue-50 text-blue-700 shadow-sm ring-1 ring-blue-100' 
             : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900 border border-gray-200'"
         >
           <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
             <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16m-7 6h7" />
           </svg>
           {{ isContextPanelOpen ? 'Hide Context' : 'Show Context' }}
         </button>

         <span class="px-2 py-1 bg-green-50 text-green-700 text-xs font-semibold rounded-md border border-green-100 uppercase tracking-wider">
           Agent Active
         </span>
      </div>
    </header>

    <!-- Main Workspace Area (Modal Layout) -->
    <div class="flex-1 flex overflow-hidden relative">
      
      <!-- BACKGROUND: Agent Work Area (Chat) -->
      <div class="flex-1 flex flex-col min-w-0 bg-white relative z-0">
        <!-- Chat Interface (Full Screen, No Padding) -->
        <div class="flex-1 bg-white relative">
           <div v-if="repository" class="absolute inset-0">
             <RepositoryChat
              :repository="repository"
              :system-id="systemId"
              :hide-header="true"
            />
           </div>
        </div>
      </div>

      <!-- OVERLAY: Context Modal -->
      <transition name="modal-fade">
        <div v-if="isContextPanelOpen" class="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6">
          
          <!-- Backdrop -->
          <div class="absolute inset-0 bg-black/40 backdrop-blur-[2px] transition-opacity" @click="toggleContextPanel"></div>

          <!-- Modal Card -->
          <div class="relative bg-white rounded-xl shadow-2xl w-[95%] max-w-[1400px] h-[90vh] flex flex-col overflow-hidden border border-gray-100 ring-1 ring-black/5">
            
            <!-- Modal Header / Tabs -->
            <div class="flex items-center justify-between px-4 py-3 bg-gray-50/50 border-b border-gray-200">
               <!-- Left: Tabs -->
               <div class="flex items-center gap-1">
                <button
                  v-for="tab in contextTabs"
                  :key="tab.id"
                  @click="activeContextTab = tab.id"
                  class="px-3 py-2 text-sm font-medium rounded-md whitespace-nowrap transition-all duration-200 flex items-center gap-2"
                  :class="activeContextTab === tab.id 
                    ? 'bg-white text-blue-700 shadow-sm ring-1 ring-gray-200' 
                    : 'text-gray-600 hover:bg-gray-100/80 hover:text-gray-900'"
                >
                  <span>{{ tab.icon }}</span>
                  {{ tab.label }}
                </button>
               </div>

               <!-- Right: Close Button -->
               <button 
                @click="toggleContextPanel"
                class="ml-4 p-2 rounded-full text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors"
               >
                 <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" /></svg>
               </button>
            </div>

            <!-- Modal Content -->
            <div class="flex-1 overflow-hidden relative bg-white">
              
              <div v-if="loading" class="absolute inset-0 flex flex-col items-center justify-center text-gray-500 gap-3">
                <div class="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin"></div>
                <span class="text-sm font-medium">Loading Context...</span>
              </div>

              <div v-else-if="error" class="absolute inset-0 flex flex-col items-center justify-center p-8 text-center">
                <p class="text-red-500 font-medium mb-2">{{ error }}</p>
                <button @click="loadRepository" class="text-blue-600 hover:underline text-sm">Retry Load</button>
              </div>

              <!-- Tab Views -->
              <template v-else-if="repository">
                
                <div v-if="activeContextTab === 'code'" class="h-full flex flex-col">
                  <CodeBrowser
                    :repository-id="repository.id"
                    :system-id="systemId"
                    :artifacts="crsPayloads.artifacts || []"
                  />
                </div>

                <div v-if="activeContextTab === 'knowledge'" class="h-full overflow-y-auto custom-scrollbar p-6">
                   <RepositoryKnowledge
                    :repository-id="repository.id"
                     :system-id="systemId"
                  />
                </div>

                <div v-if="activeContextTab === 'docs'" class="h-full overflow-y-auto custom-scrollbar p-6">
                  <RepositoryDocs
                    :repository="repository"
                  />
                </div>

                <div v-if="activeContextTab === 'trace'" class="h-full overflow-y-auto custom-scrollbar">
                  <SessionTrace
                    :repository="repository"
                    :system-id="systemId"
                  />
                </div>

              </template>
            </div>

          </div>
        </div>
      </transition>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '../services/api'
import RepositoryKnowledge from '../components/RepositoryKnowledge.vue'
import RepositoryDocs from '../components/RepositoryDocs.vue'
import RepositoryChat from '../components/RepositoryChat.vue'
import CodeBrowser from '../components/CodeBrowser.vue'
import SessionTrace from '../components/SessionTrace.vue'
import TaskDashboard from '../components/TaskDashboard.vue'

const route = useRoute()
const router = useRouter()

const systemId = computed(() => parseInt(route.params.systemId))
const repositoryId = computed(() => parseInt(route.params.repoId))

const repository = ref(null)
const crsPayloads = ref({ artifacts: [], relationships: [], blueprints: {} })
const loading = ref(true)
const error = ref(null)

const isContextPanelOpen = ref(false)

// Right Panel State
const activeContextTab = ref('code')

const contextTabs = [
  { id: 'code', label: 'Code', icon: '💻' },
  { id: 'knowledge', label: 'Knowledge', icon: '🧠' },
  { id: 'docs', label: 'Docs', icon: '📄' },
  { id: 'trace', label: 'Trace', icon: '🔍' }
]

const goBack = () => {
  router.push(`/systems/${systemId.value}`)
}

const toggleContextPanel = () => {
  isContextPanelOpen.value = !isContextPanelOpen.value
}

const loadRepository = async () => {
  loading.value = true
  error.value = null
  
  try {
    // Load repository data
    const repoResponse = await api.getRepository(systemId.value, repositoryId.value)
    repository.value = repoResponse.data
    
    // Load CRS payloads if available
    try {
      const payloadsResponse = await api.getCRSPayloads(systemId.value, repositoryId.value)
      crsPayloads.value = payloadsResponse.data
    } catch (err) {
      console.warn('CRS payloads not available:', err)
      // Not a critical error, continue without payloads
    }
  } catch (err) {
    console.error('Failed to load repository:', err)
    error.value = err.response?.data?.error || 'Failed to load repository'
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadRepository()
})
</script>

<style scoped>
/* Custom Scrollbar for sleek look */
.custom-scrollbar::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}

.custom-scrollbar::-webkit-scrollbar-track {
  background: transparent;
}

.custom-scrollbar::-webkit-scrollbar-thumb {
  background-color: #e2e8f0;
  border-radius: 3px;
}

.custom-scrollbar::-webkit-scrollbar-thumb:hover {
  background-color: #cbd5e1;
}

.no-scrollbar::-webkit-scrollbar {
  display: none;
}

.no-scrollbar {
  -ms-overflow-style: none;
  scrollbar-width: none;
}

/* Transitions */
.modal-fade-enter-active,
.modal-fade-leave-active {
  transition: opacity 0.2s ease;
}

.modal-fade-enter-from,
.modal-fade-leave-to {
  opacity: 0;
}
</style>
