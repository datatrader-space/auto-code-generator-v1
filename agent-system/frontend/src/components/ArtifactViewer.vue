<template>
  <div class="artifact-viewer">
    <!-- Search and Filters -->
    <div class="search-bar">
      <div class="flex items-center gap-3">
        <div class="relative flex-1">
          <svg class="w-5 h-5 absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          <input
            v-model="searchQuery"
            type="text"
            placeholder="Search artifacts by name, type, or content..."
            class="search-input"
          />
          <button
            v-if="searchQuery"
            @click="searchQuery = ''"
            class="absolute right-3 top-1/2 transform -translate-y-1/2 text-gray-400 hover:text-gray-600"
          >
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <!-- View Mode Toggle -->
        <div class="flex bg-gray-100 rounded-lg p-1">
          <button
            @click="viewMode = 'cards'"
            :class="['view-toggle', viewMode === 'cards' ? 'active' : '']"
            title="Card View"
          >
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
            </svg>
          </button>
          <button
            @click="viewMode = 'list'"
            :class="['view-toggle', viewMode === 'list' ? 'active' : '']"
            title="List View"
          >
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>
        </div>

        <!-- Display Mode Toggle -->
        <select v-model="displayMode" class="display-select">
          <option value="source">Source Code</option>
          <option value="json">JSON Structure</option>
          <option value="both">Both</option>
        </select>
      </div>

      <!-- Results Count -->
      <div class="mt-3 flex items-center justify-between">
        <p class="text-sm text-gray-600">
          {{ filteredArtifacts.length }} of {{ artifacts.length }} artifacts
        </p>
        <div class="flex gap-2">
          <button
            v-for="type in artifactTypes"
            :key="type"
            @click="toggleTypeFilter(type)"
            :class="['filter-tag', typeFilters.includes(type) ? 'active' : '']"
          >
            {{ type }}
          </button>
        </div>
      </div>
    </div>

    <!-- Artifacts Display -->
    <div v-if="filteredArtifacts.length === 0" class="empty-state">
      <svg class="w-16 h-16 mx-auto text-gray-300 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
      </svg>
      <p class="text-gray-500 font-medium">No artifacts found</p>
      <p class="text-sm text-gray-400 mt-1">Try adjusting your search or filters</p>
    </div>

    <!-- Card View -->
    <div v-else-if="viewMode === 'cards'" class="artifacts-grid">
      <div
        v-for="artifact in paginatedArtifacts"
        :key="artifact.name"
        class="artifact-card"
        @click="selectArtifact(artifact)"
      >
        <div class="card-header">
          <div class="flex items-start justify-between">
            <div class="flex-1 min-w-0">
              <h4 class="card-title">{{ artifact.name }}</h4>
              <p class="card-type">{{ artifact.type || 'artifact' }}</p>
            </div>
            <span class="artifact-badge">
              {{ getFileExtension(artifact.name) }}
            </span>
          </div>
        </div>

        <div class="card-body">
          <div v-if="artifact.docstring" class="text-xs text-gray-600 line-clamp-2 mb-2">
            {{ artifact.docstring }}
          </div>

          <div class="flex flex-wrap gap-2 mt-2">
            <span v-if="artifact.methods?.length" class="meta-tag">
              {{ artifact.methods.length }} methods
            </span>
            <span v-if="artifact.properties?.length" class="meta-tag">
              {{ artifact.properties.length }} properties
            </span>
            <span v-if="artifact.imports?.length" class="meta-tag">
              {{ artifact.imports.length }} imports
            </span>
          </div>
        </div>

        <div class="card-footer">
          <button class="view-button">
            View Details →
          </button>
        </div>
      </div>
    </div>

    <!-- List View -->
    <div v-else class="artifacts-list">
      <div
        v-for="artifact in paginatedArtifacts"
        :key="artifact.name"
        class="list-item"
        @click="selectArtifact(artifact)"
      >
        <div class="flex items-center justify-between">
          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2">
              <span class="artifact-badge-sm">{{ getFileExtension(artifact.name) }}</span>
              <h4 class="list-title">{{ artifact.name }}</h4>
              <span class="text-xs text-gray-400">{{ artifact.type }}</span>
            </div>
            <p v-if="artifact.docstring" class="text-xs text-gray-500 mt-1 line-clamp-1">
              {{ artifact.docstring }}
            </p>
          </div>
          <svg class="w-5 h-5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
          </svg>
        </div>
      </div>
    </div>

    <!-- Pagination -->
    <div v-if="totalPages > 1" class="pagination">
      <button
        @click="currentPage--"
        :disabled="currentPage === 1"
        class="pagination-button"
      >
        Previous
      </button>
      <span class="pagination-info">
        Page {{ currentPage }} of {{ totalPages }}
      </span>
      <button
        @click="currentPage++"
        :disabled="currentPage === totalPages"
        class="pagination-button"
      >
        Next
      </button>
    </div>

    <!-- Artifact Detail Modal -->
    <div
      v-if="selectedArtifact"
      class="modal-overlay"
      @click.self="selectedArtifact = null"
    >
      <div class="modal-content">
        <div class="modal-header">
          <div>
            <h3 class="modal-title">{{ selectedArtifact.name }}</h3>
            <p class="text-sm text-gray-500">{{ selectedArtifact.type || 'Artifact' }}</p>
          </div>
          <button
            @click="selectedArtifact = null"
            class="close-button"
          >
            <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div class="modal-body">
          <!-- Source Code View -->
          <div v-if="displayMode === 'source' || displayMode === 'both'" class="code-section">
            <div class="section-header">
              <h4 class="section-title">Source Code</h4>
              <button
                @click="copyCode(selectedArtifact)"
                class="copy-button"
              >
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                </svg>
                Copy
              </button>
            </div>
            <pre class="code-block"><code>{{ formatSourceCode(selectedArtifact) }}</code></pre>
          </div>

          <!-- JSON View -->
          <div v-if="displayMode === 'json' || displayMode === 'both'" class="json-section">
            <div class="section-header">
              <h4 class="section-title">JSON Structure</h4>
              <button
                @click="copyJSON(selectedArtifact)"
                class="copy-button"
              >
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                </svg>
                Copy
              </button>
            </div>
            <pre class="json-block"><code>{{ JSON.stringify(selectedArtifact, null, 2) }}</code></pre>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'

const props = defineProps({
  artifacts: {
    type: Array,
    default: () => []
  }
})

// State
const searchQuery = ref('')
const viewMode = ref('cards') // 'cards' or 'list'
const displayMode = ref('source') // 'source', 'json', or 'both'
const typeFilters = ref([])
const selectedArtifact = ref(null)
const currentPage = ref(1)
const itemsPerPage = 12

// Computed
const artifactTypes = computed(() => {
  const types = new Set(props.artifacts.map(a => a.type).filter(Boolean))
  return Array.from(types)
})

const filteredArtifacts = computed(() => {
  let filtered = props.artifacts

  // Apply search
  if (searchQuery.value) {
    const query = searchQuery.value.toLowerCase()
    filtered = filtered.filter(artifact => {
      return (
        artifact.name?.toLowerCase().includes(query) ||
        artifact.type?.toLowerCase().includes(query) ||
        artifact.docstring?.toLowerCase().includes(query)
      )
    })
  }

  // Apply type filters
  if (typeFilters.value.length > 0) {
    filtered = filtered.filter(artifact =>
      typeFilters.value.includes(artifact.type)
    )
  }

  return filtered
})

const totalPages = computed(() =>
  Math.ceil(filteredArtifacts.value.length / itemsPerPage)
)

const paginatedArtifacts = computed(() => {
  const start = (currentPage.value - 1) * itemsPerPage
  const end = start + itemsPerPage
  return filteredArtifacts.value.slice(start, end)
})

// Methods
const toggleTypeFilter = (type) => {
  const index = typeFilters.value.indexOf(type)
  if (index > -1) {
    typeFilters.value.splice(index, 1)
  } else {
    typeFilters.value.push(type)
  }
  currentPage.value = 1 // Reset to first page
}

const selectArtifact = (artifact) => {
  selectedArtifact.value = artifact
}

const getFileExtension = (name) => {
  if (!name) return ''
  const ext = name.split('.').pop()
  return ext.toUpperCase()
}

const formatSourceCode = (artifact) => {
  // Format artifact as source code
  if (artifact.source_code) {
    return artifact.source_code
  }

  // Reconstruct from structure
  let code = ''
  if (artifact.docstring) {
    code += `"""${artifact.docstring}"""\n\n`
  }

  if (artifact.imports?.length) {
    code += artifact.imports.join('\n') + '\n\n'
  }

  if (artifact.type === 'class') {
    code += `class ${artifact.name}:\n`
    if (artifact.methods?.length) {
      artifact.methods.forEach(method => {
        code += `    def ${method.name}(${method.parameters?.join(', ') || ''}):\n`
        code += `        """${method.docstring || 'Method implementation'}"""\n`
        code += `        pass\n\n`
      })
    }
  } else if (artifact.type === 'function') {
    code += `def ${artifact.name}(${artifact.parameters?.join(', ') || ''}):\n`
    code += `    """${artifact.docstring || 'Function implementation'}"""\n`
    code += `    pass\n`
  }

  return code || JSON.stringify(artifact, null, 2)
}

const copyCode = (artifact) => {
  const code = formatSourceCode(artifact)
  navigator.clipboard.writeText(code)
}

const copyJSON = (artifact) => {
  navigator.clipboard.writeText(JSON.stringify(artifact, null, 2))
}

// Reset page when search changes
watch(searchQuery, () => {
  currentPage.value = 1
})
</script>

<style scoped>
.artifact-viewer {
  @apply space-y-4;
}

.search-bar {
  @apply bg-white rounded-lg border p-4;
}

.search-input {
  @apply w-full pl-10 pr-10 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent;
}

.view-toggle {
  @apply px-3 py-1.5 rounded text-gray-600 transition-colors;
}

.view-toggle.active {
  @apply bg-white text-blue-600 shadow-sm;
}

.display-select {
  @apply px-3 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent;
}

.filter-tag {
  @apply px-2 py-1 text-xs border rounded-full text-gray-600 hover:bg-gray-50 transition-colors;
}

.filter-tag.active {
  @apply bg-blue-100 text-blue-700 border-blue-300;
}

.empty-state {
  @apply py-12 text-center;
}

/* Card View */
.artifacts-grid {
  @apply grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4;
}

.artifact-card {
  @apply bg-white border rounded-lg overflow-hidden hover:shadow-md transition-shadow cursor-pointer;
}

.card-header {
  @apply p-4 bg-gray-50 border-b;
}

.card-title {
  @apply font-medium text-gray-900 truncate;
}

.card-type {
  @apply text-xs text-gray-500 mt-0.5;
}

.artifact-badge {
  @apply px-2 py-1 bg-blue-100 text-blue-700 text-xs font-mono rounded;
}

.artifact-badge-sm {
  @apply px-1.5 py-0.5 bg-gray-100 text-gray-600 text-xs font-mono rounded;
}

.card-body {
  @apply p-4;
}

.meta-tag {
  @apply px-2 py-1 bg-gray-100 text-gray-600 text-xs rounded;
}

.card-footer {
  @apply px-4 py-3 bg-gray-50 border-t;
}

.view-button {
  @apply text-sm text-blue-600 hover:text-blue-700 font-medium;
}

/* List View */
.artifacts-list {
  @apply space-y-2;
}

.list-item {
  @apply bg-white border rounded-lg p-4 hover:shadow-sm transition-shadow cursor-pointer;
}

.list-title {
  @apply font-medium text-gray-900 truncate;
}

/* Pagination */
.pagination {
  @apply flex items-center justify-center gap-4 py-4;
}

.pagination-button {
  @apply px-4 py-2 border rounded-lg hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed;
}

.pagination-info {
  @apply text-sm text-gray-600;
}

/* Modal */
.modal-overlay {
  @apply fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50;
}

.modal-content {
  @apply bg-white rounded-lg max-w-4xl w-full max-h-[90vh] overflow-hidden flex flex-col;
}

.modal-header {
  @apply flex items-start justify-between p-6 border-b;
}

.modal-title {
  @apply text-xl font-bold text-gray-900;
}

.close-button {
  @apply text-gray-400 hover:text-gray-600 transition-colors;
}

.modal-body {
  @apply p-6 overflow-y-auto space-y-6;
}

.code-section,
.json-section {
  @apply space-y-3;
}

.section-header {
  @apply flex items-center justify-between;
}

.section-title {
  @apply font-semibold text-gray-900;
}

.copy-button {
  @apply flex items-center gap-1 px-3 py-1 text-sm text-gray-600 hover:text-gray-900 border rounded-lg hover:bg-gray-50 transition-colors;
}

.code-block {
  @apply bg-gray-900 text-gray-100 p-4 rounded-lg overflow-x-auto font-mono text-sm;
  max-height: 500px;
}

.json-block {
  @apply bg-gray-50 text-gray-800 p-4 rounded-lg overflow-x-auto font-mono text-sm border;
  max-height: 500px;
}

.line-clamp-1 {
  display: -webkit-box;
  -webkit-line-clamp: 1;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.line-clamp-2 {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>
