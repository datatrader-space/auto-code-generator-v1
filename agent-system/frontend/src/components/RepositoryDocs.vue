<template>
  <div class="h-full flex flex-col bg-white rounded-lg border">
    <!-- Header/Tabs -->
    <div class="border-b px-4 py-3 flex items-center justify-between bg-gray-50">
      <div class="flex space-x-4">
        <button
          @click="activeTab = 'requirements'"
          class="px-3 py-1 text-sm font-medium rounded-md transition-colors"
          :class="activeTab === 'requirements' ? 'bg-white text-blue-700 shadow-sm' : 'text-gray-600 hover:text-gray-900'"
        >
          Requirements / Spec
        </button>
        <button
          @click="activeTab = 'generated'"
          class="px-3 py-1 text-sm font-medium rounded-md transition-colors"
          :class="activeTab === 'generated' ? 'bg-white text-blue-700 shadow-sm' : 'text-gray-600 hover:text-gray-900'"
        >
          Generated Docs
        </button>
      </div>
      
      <!-- Actions -->
      <div v-if="activeTab === 'requirements' && filename">
        <span class="text-xs text-gray-400">File: {{ filename }}</span>
      </div>
    </div>

    <!-- Content -->
    <div class="flex-1 overflow-y-auto p-8 relative">
       <!-- Loading State -->
       <div v-if="loading" class="absolute inset-0 flex items-center justify-center bg-white z-10">
         <div class="flex flex-col items-center">
            <svg class="animate-spin h-8 w-8 text-blue-600 mb-2" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
            <p class="text-gray-500 text-sm">Loading documentation...</p>
         </div>
       </div>

       <!-- Requirements Tab -->
       <div v-if="activeTab === 'requirements'" class="prose max-w-none dark:prose-invert">
          <div v-if="error" class="bg-red-50 text-red-700 p-4 rounded-lg">
             {{ error }}
          </div>
          <div v-else-if="requirementsContent" v-html="renderedRequirements"></div>
          <div v-else class="text-center text-gray-500 py-12">
            No requirements file found.
          </div>
       </div>

       <!-- Generated Docs Tab -->
       <div v-if="activeTab === 'generated'" class="prose max-w-none">
          <h3>Generated Documentation</h3>
          <p class="text-gray-600">
            This section will display AI-generated usage guides, API references, and architecture summaries extracted from the Knowledge Graph.
          </p>
          <div class="bg-yellow-50 text-yellow-800 p-4 rounded-lg mt-4 w-fit">
            🚧 Feature Coming Soon
          </div>
       </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, computed } from 'vue'
import { marked } from 'marked'
import api from '../services/api'

const props = defineProps({
  repository: {
    type: Object,
    required: true
  }
})

const activeTab = ref('requirements')
const loading = ref(false)
const error = ref(null)
const requirementsContent = ref('')
const filename = ref('')

// Configure marked (syntax highlighting removed - can add back later if needed)
marked.setOptions({
  breaks: true,
  gfm: true
})

const renderedRequirements = computed(() => {
    if (!requirementsContent.value) return ''
    return marked(requirementsContent.value)
})

const fetchRequirements = async () => {
  if (!props.repository || !props.repository.id) return

  loading.value = true
  error.value = null
  requirementsContent.value = ''
  filename.value = ''

  try {
     // Ensure props.repository.system is available. If it's just an ID in some contexts, we might need to fetch it.
     // Assuming props.repository has system ID or we can get it from route.
     // Currently api.getRepositoryRequirements takes (systemId, repoId).
     // props.repository from SystemDetail likely has system_id or we can pass systemId as prop.
     
     // Checking SystemDetail usage: "v-for='repo in repositories'" -> repo usually has system_id or system object if serialized deeply.
     // Let's assume repo.system or repo.system_id is present.
     const systemId = props.repository.system || props.repository.system_id
     
     const response = await api.getRepositoryRequirements(systemId, props.repository.id)
     requirementsContent.value = response.data.content || ''
     filename.value = response.data.filename || ''
     
     if (response.data.error) {
        error.value = response.data.error
     }

  } catch (err) {
     console.error("Failed to load requirements", err)
     error.value = "Failed to load requirements. Repository might not be cloned or no file exists."
     requirementsContent.value = err.response?.data?.content || '' // Fallback if backend returns helpful markdown message on 404
  } finally {
     loading.value = false
  }
}

onMounted(() => {
  fetchRequirements()
})

watch(() => props.repository.id, () => {
   fetchRequirements()
})
</script>

<style scoped>
/* Scoped overrides if needed, mainly relying on tailwind typography */
</style>
