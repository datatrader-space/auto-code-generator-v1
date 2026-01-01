<template>
  <div class="h-full flex flex-col bg-white rounded-lg border">
    <div class="px-6 py-4 border-b bg-gray-50">
      <h3 class="font-semibold text-gray-900">Conversation History</h3>
    </div>
    <div class="flex-1 overflow-y-auto p-4">
      <div v-if="loading" class="text-center py-4 text-gray-500">Loading...</div>
      <div v-else-if="conversations.length === 0" class="text-center py-8 text-gray-500">
        No history found.
      </div>
      <div v-else class="space-y-2">
        <div 
          v-for="conv in conversations" 
          :key="conv.id"
          @click="$emit('select-conversation', conv.id)"
          class="p-4 border rounded hover:bg-gray-50 cursor-pointer flex justify-between items-center group transition-colors"
        >
          <div>
            <div class="font-medium text-gray-900 text-sm mb-1">{{ conv.title || 'Untitled Conversation' }}</div>
            <div class="text-xs text-gray-500">{{ formatDate(conv.updated_at) }} • {{ conv.message_count }} messages</div>
          </div>
          <div class="text-blue-600 opacity-0 group-hover:opacity-100 text-sm font-medium">
            Open →
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
  repositoryId: {
    type: Number,
    required: true
  }
})

const loading = ref(false)
const conversations = ref([])

const fetchHistory = async () => {
   if (!props.repositoryId) return
   loading.value = true
   try {
     const response = await api.get(`/conversations/?repository=${props.repositoryId}`)
     conversations.value = response.data.results || response.data
   } catch (e) {
     console.error(e)
   } finally {
     loading.value = false
   }
}

const formatDate = (date) => new Date(date).toLocaleDateString()

onMounted(fetchHistory)
watch(() => props.repositoryId, fetchHistory)
</script>
