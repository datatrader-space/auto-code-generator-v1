<template>
  <div class="relationship-viewer">
    <!-- Header Controls -->
    <div class="viewer-header">
      <div class="flex items-center justify-between">
        <div>
          <h3 class="text-lg font-semibold text-gray-900">Relationships</h3>
          <p class="text-sm text-gray-500">Code dependencies and connections</p>
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
              placeholder="Search relationships..."
              class="search-input"
            />
          </div>

          <!-- View Mode Toggle -->
          <div class="flex bg-gray-100 rounded-lg p-1">
            <button
              @click="viewMode = 'list'"
              :class="['toggle-button', viewMode === 'list' ? 'active' : '']"
              title="List View"
            >
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            </button>
            <button
              @click="viewMode = 'network'"
              :class="['toggle-button', viewMode === 'network' ? 'active' : '']"
              title="Network View"
            >
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
            </button>
          </div>

          <!-- Type Filter -->
          <select v-model="relationshipTypeFilter" class="type-select">
            <option value="">All Types</option>
            <option value="imports">Imports</option>
            <option value="calls">Function Calls</option>
            <option value="inherits">Inheritance</option>
            <option value="uses">Uses</option>
            <option value="used_by">Used By</option>
          </select>
        </div>
      </div>

      <!-- Stats -->
      <div class="mt-3 flex items-center gap-4 text-sm">
        <div class="flex items-center gap-2">
          <span class="stat-badge bg-blue-100 text-blue-700">
            {{ totalRelationships }} total
          </span>
          <span v-if="relationshipStats.imports" class="stat-badge bg-green-100 text-green-700">
            {{ relationshipStats.imports }} imports
          </span>
          <span v-if="relationshipStats.calls" class="stat-badge bg-purple-100 text-purple-700">
            {{ relationshipStats.calls }} calls
          </span>
          <span v-if="relationshipStats.inherits" class="stat-badge bg-orange-100 text-orange-700">
            {{ relationshipStats.inherits }} inheritance
          </span>
        </div>
      </div>
    </div>

    <!-- Empty State -->
    <div v-if="!relationships || Object.keys(relationships).length === 0" class="empty-state">
      <svg class="w-16 h-16 mx-auto text-gray-300 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
      </svg>
      <p class="text-gray-500 font-medium">No relationships found</p>
      <p class="text-sm text-gray-400 mt-1">Run CRS analysis to discover code relationships</p>
    </div>

    <!-- List View -->
    <div v-else-if="viewMode === 'list'" class="list-view">
      <div
        v-for="(data, artifactName) in filteredRelationships"
        :key="artifactName"
        class="relationship-card"
      >
        <div class="card-header" @click="toggleExpand(artifactName)">
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-2">
              <svg
                :class="['w-4 h-4 transition-transform', isExpanded(artifactName) ? 'rotate-90' : '']"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
              </svg>
              <svg class="w-5 h-5 text-purple-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 21a4 4 0 01-4-4V5a2 2 0 012-2h4a2 2 0 012 2v12a4 4 0 01-4 4zm0 0h12a2 2 0 002-2v-4a2 2 0 00-2-2h-2.343M11 7.343l1.657-1.657a2 2 0 012.828 0l2.829 2.829a2 2 0 010 2.828l-8.486 8.485M7 17h.01" />
              </svg>
              <span class="font-medium text-gray-900">{{ artifactName }}</span>
            </div>

            <span class="text-xs text-gray-500">
              {{ getRelationshipCount(data) }} connections
            </span>
          </div>
        </div>

        <div v-if="isExpanded(artifactName)" class="card-body">
          <!-- Imports -->
          <div v-if="data.imports && data.imports.length > 0" class="relation-section">
            <h4 class="relation-title">
              <svg class="w-4 h-4 inline text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M9 19l3 3m0 0l3-3m-3 3V10" />
              </svg>
              Imports ({{ data.imports.length }})
            </h4>
            <ul class="relation-list">
              <li v-for="(item, index) in data.imports" :key="index" class="relation-item">
                <code class="relation-code">{{ item }}</code>
              </li>
            </ul>
          </div>

          <!-- Calls -->
          <div v-if="data.calls && data.calls.length > 0" class="relation-section">
            <h4 class="relation-title">
              <svg class="w-4 h-4 inline text-purple-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
              Calls ({{ data.calls.length }})
            </h4>
            <ul class="relation-list">
              <li v-for="(item, index) in data.calls" :key="index" class="relation-item">
                <code class="relation-code">{{ item }}</code>
              </li>
            </ul>
          </div>

          <!-- Used By -->
          <div v-if="data.used_by && data.used_by.length > 0" class="relation-section">
            <h4 class="relation-title">
              <svg class="w-4 h-4 inline text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
              </svg>
              Used By ({{ data.used_by.length }})
            </h4>
            <ul class="relation-list">
              <li v-for="(item, index) in data.used_by" :key="index" class="relation-item">
                <code class="relation-code">{{ item }}</code>
              </li>
            </ul>
          </div>

          <!-- Inherits -->
          <div v-if="data.inherits && data.inherits.length > 0" class="relation-section">
            <h4 class="relation-title">
              <svg class="w-4 h-4 inline text-orange-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
              </svg>
              Inherits ({{ data.inherits.length }})
            </h4>
            <ul class="relation-list">
              <li v-for="(item, index) in data.inherits" :key="index" class="relation-item">
                <code class="relation-code">{{ item }}</code>
              </li>
            </ul>
          </div>
        </div>
      </div>
    </div>

    <!-- Network View -->
    <div v-else class="network-view">
      <div class="network-container">
        <svg ref="networkSvg" class="network-svg"></svg>
        <div class="network-placeholder">
          <svg class="w-24 h-24 text-gray-300 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
          </svg>
          <p class="text-gray-500 font-medium">Network visualization coming soon</p>
          <p class="text-sm text-gray-400 mt-1">Interactive graph showing all relationships</p>
          <p class="text-xs text-gray-400 mt-2">Use list view to explore relationships</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'

const props = defineProps({
  relationships: {
    type: Object,
    default: () => ({})
  }
})

// State
const searchQuery = ref('')
const viewMode = ref('list') // 'list' or 'network'
const relationshipTypeFilter = ref('')
const expandedItems = ref(new Set())
const networkSvg = ref(null)

// Computed
const filteredRelationships = computed(() => {
  let filtered = { ...props.relationships }

  // Apply search
  if (searchQuery.value) {
    const query = searchQuery.value.toLowerCase()
    filtered = Object.fromEntries(
      Object.entries(filtered).filter(([name, data]) =>
        name.toLowerCase().includes(query) ||
        JSON.stringify(data).toLowerCase().includes(query)
      )
    )
  }

  // Apply type filter
  if (relationshipTypeFilter.value) {
    filtered = Object.fromEntries(
      Object.entries(filtered).filter(([_, data]) =>
        data[relationshipTypeFilter.value] && data[relationshipTypeFilter.value].length > 0
      )
    )
  }

  return filtered
})

const totalRelationships = computed(() => {
  return Object.keys(props.relationships || {}).length
})

const relationshipStats = computed(() => {
  const stats = {
    imports: 0,
    calls: 0,
    inherits: 0,
    used_by: 0
  }

  Object.values(props.relationships || {}).forEach(data => {
    if (data.imports) stats.imports += data.imports.length
    if (data.calls) stats.calls += data.calls.length
    if (data.inherits) stats.inherits += data.inherits.length
    if (data.used_by) stats.used_by += data.used_by.length
  })

  return stats
})

// Methods
const toggleExpand = (artifactName) => {
  if (expandedItems.value.has(artifactName)) {
    expandedItems.value.delete(artifactName)
  } else {
    expandedItems.value.add(artifactName)
  }
}

const isExpanded = (artifactName) => {
  return expandedItems.value.has(artifactName)
}

const getRelationshipCount = (data) => {
  let count = 0
  if (data.imports) count += data.imports.length
  if (data.calls) count += data.calls.length
  if (data.used_by) count += data.used_by.length
  if (data.inherits) count += data.inherits.length
  return count
}
</script>

<style scoped>
.relationship-viewer {
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

.type-select {
  @apply px-3 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent;
}

.stat-badge {
  @apply px-2 py-1 text-xs font-medium rounded-full;
}

.empty-state {
  @apply py-16 text-center bg-white rounded-lg border;
}

/* List View */
.list-view {
  @apply space-y-3;
}

.relationship-card {
  @apply bg-white rounded-lg border overflow-hidden;
}

.card-header {
  @apply px-4 py-3 bg-gray-50 border-b cursor-pointer hover:bg-gray-100 transition-colors;
}

.card-body {
  @apply p-4 space-y-4;
}

.relation-section {
  @apply border-l-4 pl-4;
}

.relation-section:nth-child(1) {
  @apply border-green-400;
}

.relation-section:nth-child(2) {
  @apply border-purple-400;
}

.relation-section:nth-child(3) {
  @apply border-blue-400;
}

.relation-section:nth-child(4) {
  @apply border-orange-400;
}

.relation-title {
  @apply font-semibold text-gray-900 mb-2 text-sm;
}

.relation-list {
  @apply space-y-1;
}

.relation-item {
  @apply text-sm;
}

.relation-code {
  @apply bg-gray-50 px-2 py-1 rounded text-xs font-mono text-gray-700 border;
}

/* Network View */
.network-view {
  @apply bg-white rounded-lg border;
}

.network-container {
  @apply relative;
  min-height: 500px;
}

.network-svg {
  @apply w-full h-full;
}

.network-placeholder {
  @apply absolute inset-0 flex flex-col items-center justify-center;
}
</style>
