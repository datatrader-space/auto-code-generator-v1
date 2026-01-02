<template>
  <div class="h-full flex flex-col bg-white rounded-lg border">
    <div class="px-6 py-4 border-b flex justify-between items-center bg-gray-50">
      <h3 class="font-semibold text-gray-900">Task History</h3>
      <button 
        @click="$emit('start-new-task')"
        class="text-sm bg-blue-600 text-white px-3 py-1.5 rounded-md hover:bg-blue-700 transition-colors"
      >
        + New Task via Chat
      </button>
    </div>

    <div class="flex-1 overflow-y-auto p-4">
      <div v-if="loading" class="text-center py-8 text-gray-500">
        Loading tasks...
      </div>
      
      <div v-else-if="tasks.length === 0" class="text-center py-12 bg-gray-50 rounded-lg border-2 border-dashed">
        <p class="text-gray-500 mb-2">No tasks found for this system</p>
        <p class="text-xs text-gray-400">Start a conversation with the Agent to create tasks.</p>
      </div>

      <div v-else class="space-y-4">
        <div v-for="task in tasks" :key="task.id" class="border rounded-lg p-4 hover:shadow-sm transition-shadow">
           <div class="flex justify-between items-start mb-2">
             <div>
               <h4 class="font-medium text-gray-900">{{ task.title || 'Untitled Task' }}</h4>
               <p class="text-xs text-gray-500">ID: {{ task.task_id || task.id }}</p>
             </div>
             <span 
                class="px-2 py-1 text-xs rounded-full capitalize"
                :class="{
                  'bg-green-100 text-green-800': task.status === 'completed',
                  'bg-blue-100 text-blue-800': task.status === 'executing',
                  'bg-yellow-100 text-yellow-800': task.status === 'pending' || task.status === 'planning',
                  'bg-gray-100 text-gray-800': task.status === 'cancelled',
                  'bg-red-100 text-red-800': task.status === 'failed'
                }"
             >
               {{ task.status }}
             </span>
           </div>
           
           <p class="text-sm text-gray-600 mb-3 line-clamp-2">{{ task.description }}</p>
           
           <div class="text-xs text-gray-400 flex justify-between border-t pt-2 scrollbar-none">
             <span>Created: {{ formatDate(task.created_at) }}</span>
             <span v-if="task.updated_at">Updated: {{ formatDate(task.updated_at) }}</span>
           </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import api from '../services/api'

const props = defineProps({
  systemId: {
    type: Number,
    required: true
  }
})

const loading = ref(false)
const tasks = ref([])

const fetchTasks = async () => {
  if (!props.systemId) return
  
  loading.value = true
  try {
    const response = await api.getTasks(props.systemId)
    // Handle pagination results
    tasks.value = response.data.results || response.data
  } catch (error) {
    console.error("Failed to fetch tasks", error)
  } finally {
    loading.value = false
  }
}

const formatDate = (dateString) => {
  if (!dateString) return ''
  return new Date(dateString).toLocaleDateString() + ' ' + new Date(dateString).toLocaleTimeString()
}

onMounted(() => {
  fetchTasks()
})

watch(() => props.systemId, () => {
  fetchTasks()
})
</script>
