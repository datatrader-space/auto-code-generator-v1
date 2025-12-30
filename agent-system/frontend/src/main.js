import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import './style.css'
import api from './services/api'

// Import views
import SystemList from './views/SystemList.vue'
import SystemDetail from './views/SystemDetail.vue'
import Login from './views/Login.vue'

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