<template>
  <div class="tool-card bg-white rounded-lg shadow-sm border border-gray-200 p-4 hover:shadow-md transition-shadow">
    <!-- Header -->
    <div class="flex items-start justify-between mb-3">
      <div class="flex-1">
        <h3 class="text-lg font-semibold text-gray-900">{{ tool.name }}</h3>
        <p class="text-sm text-gray-600 mt-1 line-clamp-2">{{ tool.description }}</p>
      </div>
      <div class="ml-2">
        <span
          :class="[
            'px-3 py-1 text-xs rounded-full font-medium',
            tool.enabled
              ? 'bg-green-100 text-green-700'
              : 'bg-gray-100 text-gray-600'
          ]"
        >
          {{ tool.enabled ? 'Enabled' : 'Disabled' }}
        </span>
      </div>
    </div>

    <!-- Metadata -->
    <div class="space-y-2 mb-4">
      <div class="flex items-center text-sm text-gray-600">
        <span class="font-medium mr-2">Version:</span>
        <span>{{ tool.version }}</span>
      </div>

      <div class="flex items-center text-sm text-gray-600">
        <span class="font-medium mr-2">Parameters:</span>
        <span>{{ tool.parameters.length }}</span>
      </div>

      <div v-if="tool.permissions && tool.permissions.length > 0" class="flex items-center text-sm text-gray-600">
        <span class="font-medium mr-2">Permissions:</span>
        <div class="flex gap-1 flex-wrap">
          <span
            v-for="perm in tool.permissions"
            :key="perm"
            class="px-2 py-0.5 bg-orange-100 text-orange-700 rounded text-xs"
          >
            {{ perm }}
          </span>
        </div>
      </div>

      <div v-if="tool.tags && tool.tags.length > 0" class="flex items-center text-sm text-gray-600">
        <span class="font-medium mr-2">Tags:</span>
        <div class="flex gap-1 flex-wrap">
          <span
            v-for="tag in tool.tags"
            :key="tag"
            class="px-2 py-0.5 bg-blue-100 text-blue-700 rounded text-xs"
          >
            {{ tag }}
          </span>
        </div>
      </div>
    </div>

    <!-- Actions -->
    <div class="flex gap-2 pt-3 border-t border-gray-200">
      <button
        @click="$emit('execute', tool)"
        :disabled="!tool.enabled"
        class="flex-1 px-3 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 transition disabled:bg-gray-300 disabled:cursor-not-allowed text-sm font-medium"
      >
        ▶️ Execute
      </button>
      <button
        @click="$emit('view-details', tool)"
        class="px-3 py-2 border border-gray-300 text-gray-700 rounded hover:bg-gray-50 transition text-sm font-medium"
      >
        📖 Details
      </button>
    </div>
  </div>
</template>

<script>
export default {
  name: 'ToolCard',
  props: {
    tool: {
      type: Object,
      required: true
    }
  },
  emits: ['execute', 'view-details']
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
