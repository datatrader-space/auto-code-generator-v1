<template>
  <div id="app" class="min-h-screen bg-gray-50">
    <!-- Navigation (hide on login page) -->
    <nav v-if="$route.path !== '/login'" class="bg-white shadow-sm border-b">
      <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div class="flex justify-between h-16">
          <div class="flex">
            <!-- Logo -->
            <div class="flex-shrink-0 flex items-center">
              <router-link to="/" class="text-2xl font-bold text-blue-600">
                🤖 Auto Code Generator
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
          <div class="flex items-center space-x-4">
            <!-- LLM Status -->
            <div v-if="llmHealth" class="flex items-center space-x-2">
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

            <!-- GitHub Status -->
            <div v-if="currentUser" class="flex items-center">
              <div
                class="w-2 h-2 rounded-full mr-2"
                :class="currentUser.github_username ? 'bg-green-500' : 'bg-gray-300'"
              ></div>
              <span class="text-xs text-gray-600">
                {{ currentUser.github_username ? `GitHub: ${currentUser.github_username}` : 'GitHub Not Connected' }}
              </span>
            </div>

            <!-- User Menu -->
            <div v-if="currentUser" class="relative">
              <button
                @click="showUserMenu = !showUserMenu"
                class="flex items-center space-x-2 text-sm text-gray-700 hover:text-gray-900"
              >
                <span>👤 {{ currentUser.username }}</span>
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"></path>
                </svg>
              </button>

              <!-- Dropdown Menu -->
              <div
                v-if="showUserMenu"
                class="absolute right-0 mt-2 w-48 bg-white rounded-lg shadow-lg py-1 z-50"
              >
                <a
                  v-if="!currentUser.github_username"
                  @click="connectGitHub"
                  class="block px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 cursor-pointer"
                >
                  Connect GitHub
                </a>
                <a
                  @click="handleLogout"
                  class="block px-4 py-2 text-sm text-red-600 hover:bg-gray-100 cursor-pointer"
                >
                  Logout
                </a>
              </div>
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
import { ref, onMounted, provide } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import api from './services/api'

const router = useRouter()
const route = useRoute()
const llmHealth = ref(null)
const currentUser = ref(null)
const showUserMenu = ref(false)
const notifications = ref([])

// Load current user
const loadCurrentUser = async () => {
  try {
    const response = await api.getCurrentUser()
    currentUser.value = response.data.user
  } catch (error) {
    console.error('Failed to load user:', error)
    currentUser.value = null
  }
}

// Load user data on mount
onMounted(async () => {
  // Check for GitHub OAuth callback
  const urlParams = new URLSearchParams(window.location.search)

  if (urlParams.get('github_connected')) {
    const username = urlParams.get('username')
    addNotification(`GitHub connected successfully as ${username}!`, 'success')

    // Clean up URL
    window.history.replaceState({}, '', window.location.pathname)

    // Reload user data to update GitHub status
    await loadCurrentUser()
  } else if (urlParams.get('github_error')) {
    const error = urlParams.get('github_error')
    const errorMessages = {
      'no_code': 'GitHub authorization was cancelled',
      'no_token': 'Failed to get GitHub access token',
      'exchange_failed': 'Failed to connect to GitHub'
    }
    addNotification(errorMessages[error] || 'GitHub connection failed', 'error')

    // Clean up URL
    window.history.replaceState({}, '', window.location.pathname)
  }

  // Load current user if authenticated
  if (route.path !== '/login') {
    await loadCurrentUser()
  }

  // Check LLM health
  try {
    const response = await api.get('/llm/health/')
    llmHealth.value = response.data
  } catch (error) {
    console.error('Failed to check LLM health:', error)
  }
})

// Logout
const handleLogout = async () => {
  try {
    await api.logout()
    currentUser.value = null
    localStorage.removeItem('user')
    showUserMenu.value = false
    router.push('/login')
    addNotification('Logged out successfully', 'success')
  } catch (error) {
    console.error('Logout failed:', error)
    addNotification('Logout failed', 'error')
  }
}

// Connect GitHub
const connectGitHub = () => {
  showUserMenu.value = false
  // Open GitHub OAuth in popup or redirect
  window.location.href = 'http://localhost:8000/api/auth/github/login'
}

// Close user menu when clicking outside
if (typeof window !== 'undefined') {
  window.addEventListener('click', (e) => {
    if (!e.target.closest('.relative')) {
      showUserMenu.value = false
    }
  })
}

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