<template>
  <div
    class="service-card bg-white rounded-lg shadow hover:shadow-lg transition p-6 cursor-pointer relative"
    :class="{ 'opacity-60': !service.enabled }"
    @click="$emit('click', service)"
  >
    <!-- Status Badge -->
    <div class="absolute top-4 right-4">
      <span
        v-if="service.enabled"
        class="px-2 py-1 text-xs font-medium bg-green-100 text-green-700 rounded-full"
      >
        Active
      </span>
      <span
        v-else
        class="px-2 py-1 text-xs font-medium bg-gray-100 text-gray-600 rounded-full"
      >
        Disabled
      </span>
    </div>

    <!-- Icon & Name -->
    <div class="flex items-start gap-3 mb-3">
      <div class="text-3xl flex-shrink-0">
        {{ service.icon || getServiceIcon(service.category) }}
      </div>
      <div class="flex-1 min-w-0">
        <h3 class="text-lg font-bold text-gray-900 truncate">{{ service.name }}</h3>
        <p class="text-sm text-gray-500">{{ service.category || 'General' }}</p>
      </div>
    </div>

    <!-- Description -->
    <p class="text-sm text-gray-600 mb-4 line-clamp-2">
      {{ service.description }}
    </p>

    <!-- Stats -->
    <div class="grid grid-cols-2 gap-3 mb-4">
      <div class="bg-gray-50 rounded p-2">
        <div class="text-xs text-gray-500">Total Actions</div>
        <div class="text-lg font-bold text-gray-900">{{ service.total_actions }}</div>
      </div>
      <div class="bg-blue-50 rounded p-2">
        <div class="text-xs text-gray-500">Enabled</div>
        <div class="text-lg font-bold text-blue-600">{{ service.enabled_actions }}</div>
      </div>
    </div>

    <!-- Base URL -->
    <div class="mb-4 pb-4 border-b">
      <div class="text-xs text-gray-500 mb-1">Base URL</div>
      <div class="text-xs font-mono text-gray-700 truncate">{{ service.base_url }}</div>
    </div>

    <!-- Auth Type -->
    <div class="flex items-center gap-2 text-xs text-gray-600 mb-4">
      <span>🔐</span>
      <span>{{ formatAuthType(service.auth_type) }}</span>
    </div>

    <!-- Last Used -->
    <div v-if="service.last_used_at" class="text-xs text-gray-500 mb-4">
      Last used: {{ formatDate(service.last_used_at) }}
    </div>

    <!-- Actions -->
    <div class="flex gap-2" @click.stop>
      <button
        @click="$emit('toggle-enabled', service.id, !service.enabled)"
        class="flex-1 px-3 py-2 text-sm rounded transition"
        :class="service.enabled
          ? 'bg-gray-100 text-gray-700 hover:bg-gray-200'
          : 'bg-green-100 text-green-700 hover:bg-green-200'"
      >
        {{ service.enabled ? 'Disable' : 'Enable' }}
      </button>
      <button
        @click="$emit('delete', service.id)"
        class="px-3 py-2 text-sm bg-red-100 text-red-700 rounded hover:bg-red-200 transition"
      >
        Delete
      </button>
    </div>
  </div>
</template>

<script>
export default {
  name: 'ServiceCard',
  props: {
    service: {
      type: Object,
      required: true
    }
  },
  emits: ['click', 'delete', 'toggle-enabled'],
  setup() {
    const getServiceIcon = (category) => {
      const icons = {
        'project_management': '📋',
        'communication': '💬',
        'file_storage': '📁',
        'code_repository': '💻',
        'task_management': '✅',
        'crm': '👥',
        'marketing': '📈',
        'analytics': '📊'
      }
      return icons[category] || '🌐'
    }

    const formatAuthType = (authType) => {
      const types = {
        'bearer': 'Bearer Token',
        'api_key': 'API Key',
        'oauth2': 'OAuth 2.0',
        'basic': 'Basic Auth'
      }
      return types[authType] || authType
    }

    const formatDate = (dateString) => {
      const date = new Date(dateString)
      const now = new Date()
      const diff = now - date

      if (diff < 60000) return 'Just now'
      if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`
      if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`
      if (diff < 604800000) return `${Math.floor(diff / 86400000)}d ago`

      return date.toLocaleDateString()
    }

    return {
      getServiceIcon,
      formatAuthType,
      formatDate
    }
  }
}
</script>

<style scoped>
.line-clamp-2 {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>
