<template>
  <div class="blueprint-viewer">
    <!-- Header Controls -->
    <div class="viewer-header">
      <div class="flex items-center justify-between">
        <div>
          <h3 class="text-lg font-semibold text-gray-900">Blueprints</h3>
          <p class="text-sm text-gray-500">System architecture and structure definitions</p>
        </div>

        <div class="flex items-center gap-3">
          <!-- Search -->
          <div class="relative">
            <svg class="w-4 h-4 absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            <input
              v-model="searchQuery"
              type="text"
              placeholder="Search blueprints..."
              class="search-input"
            />
          </div>

          <!-- View Toggle -->
          <div class="flex bg-gray-100 rounded-lg p-1">
            <button
              @click="viewMode = 'tree'"
              :class="['toggle-button', viewMode === 'tree' ? 'active' : '']"
              title="Tree View"
            >
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
              </svg>
            </button>
            <button
              @click="viewMode = 'json'"
              :class="['toggle-button', viewMode === 'json' ? 'active' : '']"
              title="JSON View"
            >
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Empty State -->
    <div v-if="!blueprints || Object.keys(blueprints).length === 0" class="empty-state">
      <svg class="w-16 h-16 mx-auto text-gray-300 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
      </svg>
      <p class="text-gray-500 font-medium">No blueprints available</p>
      <p class="text-sm text-gray-400 mt-1">Run CRS analysis to generate blueprints</p>
    </div>

    <!-- Tree View -->
    <div v-else-if="viewMode === 'tree'" class="tree-view">
      <div
        v-for="(content, filename) in filteredBlueprints"
        :key="filename"
        class="blueprint-card"
      >
        <div class="card-header" @click="toggleExpand(filename)">
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-2">
              <svg
                :class="['w-4 h-4 transition-transform', isExpanded(filename) ? 'rotate-90' : '']"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
              </svg>
              <svg class="w-5 h-5 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              <span class="font-medium text-gray-900">{{ filename }}</span>
            </div>

            <div class="flex items-center gap-2">
              <span class="text-xs text-gray-500">
                {{ getBlueprintStats(content) }}
              </span>
              <button
                @click.stop="copyBlueprint(filename, content)"
                class="copy-icon"
                title="Copy to clipboard"
              >
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                </svg>
              </button>
            </div>
          </div>
        </div>

        <div v-if="isExpanded(filename)" class="card-body">
          <div class="blueprint-structure">
            <TreeNode :data="content" :level="0" />
          </div>
        </div>
      </div>
    </div>

    <!-- JSON View -->
    <div v-else class="json-view">
      <div
        v-for="(content, filename) in filteredBlueprints"
        :key="filename"
        class="json-card"
      >
        <div class="json-header">
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-2">
              <svg class="w-5 h-5 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              <span class="font-medium text-gray-900">{{ filename }}</span>
            </div>
            <button
              @click="copyBlueprint(filename, content)"
              class="copy-button"
            >
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
              </svg>
              Copy
            </button>
          </div>
        </div>
        <pre class="json-content"><code>{{ JSON.stringify(content, null, 2) }}</code></pre>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  blueprints: {
    type: Object,
    default: () => ({})
  }
})

// State
const searchQuery = ref('')
const viewMode = ref('tree') // 'tree' or 'json'
const expandedItems = ref(new Set())

// Computed
const filteredBlueprints = computed(() => {
  if (!searchQuery.value) return props.blueprints

  const query = searchQuery.value.toLowerCase()
  const filtered = {}

  Object.entries(props.blueprints).forEach(([filename, content]) => {
    if (
      filename.toLowerCase().includes(query) ||
      JSON.stringify(content).toLowerCase().includes(query)
    ) {
      filtered[filename] = content
    }
  })

  return filtered
})

// Methods
const toggleExpand = (filename) => {
  if (expandedItems.value.has(filename)) {
    expandedItems.value.delete(filename)
  } else {
    expandedItems.value.add(filename)
  }
}

const isExpanded = (filename) => {
  return expandedItems.value.has(filename)
}

const getBlueprintStats = (content) => {
  if (Array.isArray(content)) {
    return `${content.length} items`
  }
  if (typeof content === 'object' && content !== null) {
    const keys = Object.keys(content)
    return `${keys.length} keys`
  }
  return 'Blueprint data'
}

const copyBlueprint = (filename, content) => {
  const text = JSON.stringify(content, null, 2)
  navigator.clipboard.writeText(text)
}
</script>

<script>
// TreeNode component for hierarchical display
export default {
  components: {
    TreeNode: {
      name: 'TreeNode',
      props: {
        data: [Object, Array, String, Number, Boolean],
        level: Number
      },
      data() {
        return {
          expanded: false
        }
      },
      computed: {
        isExpandable() {
          return typeof this.data === 'object' && this.data !== null
        },
        keys() {
          if (Array.isArray(this.data)) {
            return this.data.map((_, i) => i)
          }
          return Object.keys(this.data || {})
        }
      },
      template: `
        <div class="tree-node">
          <div
            v-if="isExpandable"
            @click="expanded = !expanded"
            :class="['node-header', 'level-' + level]"
          >
            <svg
              :class="['w-3 h-3 transition-transform inline mr-1', expanded ? 'rotate-90' : '']"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
            </svg>
            <span class="node-key">
              {{ Array.isArray(data) ? 'Array' : 'Object' }}
            </span>
            <span class="node-count">({{ keys.length }})</span>
          </div>

          <div v-else :class="['node-value', 'level-' + level]">
            <span class="value-content">{{ data }}</span>
          </div>

          <div v-if="expanded" class="node-children">
            <div v-for="key in keys" :key="key" class="child-item">
              <span class="child-key">{{ key }}:</span>
              <TreeNode :data="data[key]" :level="level + 1" />
            </div>
          </div>
        </div>
      `
    }
  }
}
</script>

<style scoped>
.blueprint-viewer {
  @apply space-y-4;
}

.viewer-header {
  @apply bg-white rounded-lg border p-4;
}

.search-input {
  @apply pl-10 pr-4 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent;
  width: 250px;
}

.toggle-button {
  @apply px-3 py-1.5 rounded text-gray-600 transition-colors;
}

.toggle-button.active {
  @apply bg-white text-blue-600 shadow-sm;
}

.empty-state {
  @apply py-16 text-center bg-white rounded-lg border;
}

/* Tree View */
.tree-view {
  @apply space-y-3;
}

.blueprint-card {
  @apply bg-white rounded-lg border overflow-hidden;
}

.card-header {
  @apply px-4 py-3 bg-gray-50 border-b cursor-pointer hover:bg-gray-100 transition-colors;
}

.card-body {
  @apply p-4;
}

.copy-icon {
  @apply text-gray-400 hover:text-gray-600 transition-colors;
}

.blueprint-structure {
  @apply bg-gray-50 rounded-lg p-4 font-mono text-sm;
}

/* Tree Node Styles */
:deep(.tree-node) {
  @apply my-1;
}

:deep(.node-header) {
  @apply cursor-pointer hover:bg-gray-100 px-2 py-1 rounded;
}

:deep(.node-key) {
  @apply font-semibold text-blue-600;
}

:deep(.node-count) {
  @apply text-gray-500 text-xs ml-1;
}

:deep(.node-value) {
  @apply px-2 py-1;
}

:deep(.value-content) {
  @apply text-gray-700;
}

:deep(.node-children) {
  @apply ml-4 border-l-2 border-gray-200 pl-2;
}

:deep(.child-item) {
  @apply my-1;
}

:deep(.child-key) {
  @apply text-purple-600 font-medium mr-2;
}

:deep(.level-0) {
  @apply text-sm;
}

:deep(.level-1) {
  @apply text-sm;
}

:deep(.level-2) {
  @apply text-xs;
}

/* JSON View */
.json-view {
  @apply space-y-3;
}

.json-card {
  @apply bg-white rounded-lg border overflow-hidden;
}

.json-header {
  @apply px-4 py-3 bg-gray-50 border-b;
}

.copy-button {
  @apply flex items-center gap-1 px-3 py-1 text-sm text-gray-600 hover:text-gray-900 border rounded-lg hover:bg-gray-100 transition-colors;
}

.json-content {
  @apply bg-gray-900 text-gray-100 p-4 overflow-x-auto font-mono text-xs;
  max-height: 600px;
  overflow-y: auto;
}

.json-content code {
  @apply block;
}
</style>
