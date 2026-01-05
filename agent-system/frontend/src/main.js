import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import './style.css'
import api from './services/api'

// Import views
import SystemList from './views/SystemList.vue'
import SystemDetail from './views/SystemDetail.vue'
import RepositoryPage from './views/RepositoryPage.vue'
import Login from './views/Login.vue'
import LLMSettings from './views/LLMSettings.vue'
import Benchmarks from './views/Benchmarks.vue'
import ToolRegistry from './views/ToolRegistry.vue'
import Services from './views/Services.vue'
import AgentLibrary from './views/AgentLibrary.vue'
import AgentPlayground from './views/AgentPlayground.vue'

// Create router
const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: Login,
      meta: { requiresGuest: true }
    },
    {
      path: '/',
      name: 'home',
      component: SystemList,
      meta: { requiresAuth: true }
    },
    {
      path: '/systems/:id',
      name: 'system-detail',
      component: SystemDetail,
      meta: { requiresAuth: true }
    },
    {
      path: '/systems/:systemId/repositories/:repoId',
      name: 'repository-detail',
      component: RepositoryPage,
      meta: { requiresAuth: true }
    },
    {
      path: '/ai-settings',
      name: 'ai-settings',
      component: LLMSettings,
      meta: { requiresAuth: true }
    },
    {
      path: '/benchmarks',
      name: 'benchmarks',
      component: Benchmarks,
      meta: { requiresAuth: true }
    },
    {
      path: '/tools',
      name: 'tools',
      component: ToolRegistry,
      meta: { requiresAuth: true }
    },
    {
      path: '/services',
      name: 'services',
      component: Services,
      meta: { requiresAuth: true }
    },
    {
      path: '/agents',
      name: 'agent-library',
      component: AgentLibrary,
      meta: { requiresAuth: true }
    },
    {
      path: '/agents/:id',
      name: 'agent-playground',
      component: AgentPlayground,
      meta: { requiresAuth: true }
    }
  ]
})

// Route guards
router.beforeEach(async (to, from, next) => {
  // Check authentication status
  try {
    const response = await api.checkAuth()
    const isAuthenticated = response.data.authenticated

    if (to.meta.requiresAuth && !isAuthenticated) {
      // Redirect to login if route requires auth
      next('/login')
    } else if (to.meta.requiresGuest && isAuthenticated) {
      // Redirect to home if already logged in
      next('/')
    } else {
      next()
    }
  } catch (error) {
    // If auth check fails, redirect to login for protected routes
    if (to.meta.requiresAuth) {
      next('/login')
    } else {
      next()
    }
  }
})

// Create app
const app = createApp(App)

// Add global notification helper
app.provide('notify', (message, type = 'info') => {
  // Simple console notification for now
  // Can be replaced with a toast library later
  console.log(`[${type.toUpperCase()}] ${message}`)

  // You can add a toast library here like vue-toastification
  // For now, using alert for important messages
  if (type === 'error') {
    alert(message)
  }
})

app.use(router)
app.mount('#app')
