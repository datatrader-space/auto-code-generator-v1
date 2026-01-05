<template>
  <div class="services-container p-6 bg-gray-50 min-h-screen">
    <div class="max-w-7xl mx-auto">
      <!-- Header -->
      <div class="flex justify-between items-center mb-6">
        <div>
          <h1 class="text-3xl font-bold text-gray-900">🌐 Services</h1>
          <p class="text-gray-600 mt-1">Register external services and auto-discover their tools</p>
        </div>
        <button
          @click="showRegistrationModal = true"
          class="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition font-medium flex items-center gap-2"
        >
          <span class="text-xl">+</span>
          Register Service
        </button>
      </div>

      <!-- Stats Cards -->
      <div class="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
        <div class="bg-white p-4 rounded-lg shadow">
          <div class="text-sm text-gray-600">Total Services</div>
          <div class="text-2xl font-bold text-gray-900">{{ services.length }}</div>
        </div>
        <div class="bg-white p-4 rounded-lg shadow">
          <div class="text-sm text-gray-600">Active Services</div>
          <div class="text-2xl font-bold text-green-600">{{ activeCount }}</div>
        </div>
        <div class="bg-white p-4 rounded-lg shadow">
          <div class="text-sm text-gray-600">Total Actions</div>
          <div class="text-2xl font-bold text-purple-600">{{ totalActions }}</div>
        </div>
        <div class="bg-white p-4 rounded-lg shadow">
          <div class="text-sm text-gray-600">Enabled Actions</div>
          <div class="text-2xl font-bold text-blue-600">{{ enabledActions }}</div>
        </div>
      </div>

      <!-- Loading State -->
      <div v-if="loading" class="text-center py-12">
        <div class="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
        <p class="mt-4 text-gray-600">Loading services...</p>
      </div>

      <!-- Empty State -->
      <div v-else-if="services.length === 0" class="bg-white rounded-lg shadow-lg p-12 text-center">
        <div class="text-6xl mb-4">🌐</div>
        <h2 class="text-2xl font-bold text-gray-900 mb-2">No Services Yet</h2>
        <p class="text-gray-600 mb-6 max-w-md mx-auto">
          Register your first service to auto-discover tools and actions.
          Connect to Jira, Slack, GitHub, or any service with an OpenAPI spec.
        </p>
        <button
          @click="showRegistrationModal = true"
          class="px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition font-medium"
        >
          Register Your First Service
        </button>
      </div>

      <!-- Services Grid -->
      <div v-else class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        <ServiceCard
          v-for="service in services"
          :key="service.id"
          :service="service"
          @click="viewService(service)"
          @delete="handleDeleteService"
          @toggle-enabled="handleToggleEnabled"
        />
      </div>

      <!-- Service Registration Modal -->
      <ServiceRegistrationModal
        v-if="showRegistrationModal"
        @close="showRegistrationModal = false"
        @registered="handleServiceRegistered"
      />

      <!-- Service Detail Modal -->
      <ServiceDetailModal
        v-if="selectedService"
        :service="selectedService"
        @close="selectedService = null"
        @updated="loadServices"
      />
    </div>
  </div>
</template>

<script>
import { ref, computed, onMounted } from 'vue'
import api from '../services/api'
import ServiceCard from '../components/services/ServiceCard.vue'
import ServiceRegistrationModal from '../components/services/ServiceRegistrationModal.vue'
import ServiceDetailModal from '../components/services/ServiceDetailModal.vue'

export default {
  name: 'Services',
  components: {
    ServiceCard,
    ServiceRegistrationModal,
    ServiceDetailModal
  },
  setup() {
    const services = ref([])
    const loading = ref(false)
    const showRegistrationModal = ref(false)
    const selectedService = ref(null)

    // Computed stats
    const activeCount = computed(() => services.value.filter(s => s.enabled).length)
    const totalActions = computed(() => services.value.reduce((sum, s) => sum + s.total_actions, 0))
    const enabledActions = computed(() => services.value.reduce((sum, s) => sum + s.enabled_actions, 0))

    // Methods
    const loadServices = async () => {
      loading.value = true
      try {
        const response = await api.getServices()
        services.value = response.data.services || []
      } catch (error) {
        console.error('Failed to load services:', error)
        alert('Failed to load services: ' + (error.response?.data?.error || error.message))
      } finally {
        loading.value = false
      }
    }

    const viewService = async (service) => {
      try {
        const response = await api.getService(service.id)
        selectedService.value = response.data
      } catch (error) {
        console.error('Failed to load service details:', error)
        alert('Failed to load service details')
      }
    }

    const handleServiceRegistered = async () => {
      showRegistrationModal.value = false
      await loadServices()
      alert('Service registered successfully!')
    }

    const handleDeleteService = async (serviceId) => {
      if (!confirm('Are you sure you want to delete this service? All associated actions will be removed.')) {
        return
      }

      try {
        await api.deleteService(serviceId)
        await loadServices()
        alert('Service deleted successfully')
      } catch (error) {
        console.error('Failed to delete service:', error)
        alert('Failed to delete service: ' + (error.response?.data?.error || error.message))
      }
    }

    const handleToggleEnabled = async (serviceId, enabled) => {
      try {
        await api.updateService(serviceId, { enabled })
        await loadServices()
      } catch (error) {
        console.error('Failed to update service:', error)
        alert('Failed to update service')
      }
    }

    onMounted(() => {
      loadServices()
    })

    return {
      services,
      loading,
      showRegistrationModal,
      selectedService,
      activeCount,
      totalActions,
      enabledActions,
      viewService,
      handleServiceRegistered,
      handleDeleteService,
      handleToggleEnabled
    }
  }
}
</script>

<style scoped>
.services-container {
  animation: fadeIn 0.3s ease-in;
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
</style>
