import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import './style.css'

// Import views
import SystemList from './views/SystemList.vue'
import SystemDetail from './views/SystemDetail.vue'

// Create router
const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'home',
      component: SystemList
    },
    {
      path: '/systems/:id',
      name: 'system-detail',
      component: SystemDetail
    }
  ]
})

// Create app
const app = createApp(App)
app.use(router)
app.mount('#app')