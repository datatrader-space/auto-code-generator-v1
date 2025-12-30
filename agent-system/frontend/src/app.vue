<template>
  <div id="app" class="min-h-screen bg-gray-50">
    <!-- Navigation -->
    <nav class="bg-white shadow-sm border-b">
      <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div class="flex justify-between h-16">
          <div class="flex">
            <!-- Logo -->
            <div class="flex-shrink-0 flex items-center">
              <router-link to="/" class="text-2xl font-bold text-blue-600">
                🤖 CRS Agent
              </router-link>
            </div>
            
            <!-- Navigation Links -->
            <div class="hidden sm:ml-6 sm:flex sm:space-x-8">
              <router-link
                to="/"
                class="inline-flex items-center px-1 pt-1 text-sm font-medium text-gray-900 border-b-2"
                :class="$route.path === '/' ? 'border-blue-500' : 'border-transparent hover:border-gray-300'"
              >
                Systems
              </router-link>
              
              <a
                href="http://localhost:8000/admin"
                target="_blank"
                class="inline-flex items-center px-1 pt-1 text-sm font-medium text-gray-500 hover:text-gray-700"
              >
                Admin Panel
              </a>
            </div>
          </div>
          
          <!-- Right side -->
          <div class="flex items-center">
            <!-- LLM Status -->
            <div v-if="llmHealth" class="mr-4 flex items-center space-x-2">
              <div class="flex items-center">
                <div 
                  class="w-2 h-2 rounded-full mr-2"
                  :class="llmHealth.local?.available ? 'bg-green-500' : 'bg-gray-300'"
                ></div>
                <span class="text-xs text-gray-600">Local LLM</span>
              </div>
              
              <div class="flex items-center">
                <div 
                  class="w-2 h-2 rounded-full mr-2"
                  :class="llmHealth.cloud?.available ? 'bg-green-500' : 'bg-gray-300'"
                ></div>
                <span class="text-xs text-gray-600">Cloud LLM</span>
              </div>
            </div>
            
            <!-- User -->
            <div class="text-sm text-gray-700">
              👤 {{ username }}
            </div>
          </div>
        </div>
      </div>
    </nav>
    
    <!-- Main Content -->
    <main class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <router-view />
    </main>
    
    <!-- Toast Notifications (if any) -->
    <div class="fixed bottom-4 right-4 space-y-2">
      <div
        v-for="notification in notifications"
        :key="notification.id"
        class="bg-white shadow-lg rounded-lg p-4 max-w-sm"
        :class="{
          'border-l-4 border-green-500': notification.type === 'success',
          'border-l-4 border-red-500': notification.type === 'error',
          'border-l-4 border-blue-500': notification.type === 'info'
        }"
      >
        <div class="flex items-start">
          <div class="flex-1">
            <p class="text-sm font-medium text-gray-900">
              {{ notification.message }}
            </p>
          </div>
          <button
            @click="removeNotification(notification.id)"
            class="ml-4 text-gray-400 hover:text-gray-600"
          >
            ✕
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import api from './services/api'

const router = useRouter()
const llmHealth = ref(null)
const username = ref('admin')
const notifications = ref([])

// Check LLM health on mount
onMounted(async () => {
  try {
    const response = await api.get('/llm/health/')
    llmHealth.value = response.data
  } catch (error) {
    console.error('Failed to check LLM health:', error)
  }
})

// Notification system
let notificationId = 0

const addNotification = (message, type = 'info') => {
  const id = notificationId++
  notifications.value.push({ id, message, type })
  
  // Auto-remove after 5 seconds
  setTimeout(() => {
    removeNotification(id)
  }, 5000)
}

const removeNotification = (id) => {
  const index = notifications.value.findIndex(n => n.id === id)
  if (index > -1) {
    notifications.value.splice(index, 1)
  }
}

// Expose to child components via provide/inject
import { provide } from 'vue'
provide('notify', addNotification)
</script>

<style>
/* Global styles */
body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Oxygen',
    'Ubuntu', 'Cantarell', 'Fira Sans', 'Droid Sans', 'Helvetica Neue',
    sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

* {
  box-sizing: border-box;
}
</style>