<template>
  <div class="modal-overlay" @click.self="$emit('close')">
    <div class="modal-content service-detail-modal">
      <!-- Header -->
      <div class="modal-header">
        <div class="flex items-center gap-3">
          <div class="text-4xl">{{ service.icon || '🌐' }}</div>
          <div>
            <h2>{{ service.name }}</h2>
            <p class="text-gray-500">{{ service.slug }}</p>
          </div>
        </div>
        <button class="close-button" @click="$emit('close')">✕</button>
      </div>

      <!-- Loading State -->
      <div v-if="loading" class="loading-container">
        <div class="spinner"></div>
        <p>Loading service details...</p>
      </div>

      <!-- Error State -->
      <div v-else-if="error" class="error-container">
        <p class="text-red-600">{{ error }}</p>
        <button @click="loadServiceDetails" class="btn-secondary">Retry</button>
      </div>

      <!-- Content -->
      <div v-else class="modal-body">
        <!-- Service Info Section -->
        <div class="section">
          <h3>📋 Service Information</h3>
          <div class="info-grid">
            <div class="info-item">
              <label>Description</label>
              <p>{{ serviceDetail.description || 'No description' }}</p>
            </div>
            <div class="info-item">
              <label>Category</label>
              <p>{{ formatCategory(serviceDetail.category) }}</p>
            </div>
            <div class="info-item">
              <label>Base URL</label>
              <p class="font-mono text-sm">{{ serviceDetail.base_url }}</p>
            </div>
            <div class="info-item">
              <label>Authentication</label>
              <p>🔐 {{ formatAuthType(serviceDetail.auth_type) }}</p>
            </div>
            <div class="info-item">
              <label>API Specification</label>
              <a v-if="serviceDetail.api_spec_url" :href="serviceDetail.api_spec_url" target="_blank" class="text-blue-600 hover:underline">
                View API Spec →
              </a>
              <p v-else class="text-gray-400">Not provided</p>
            </div>
            <div class="info-item">
              <label>API Documentation</label>
              <a v-if="serviceDetail.api_docs_url" :href="serviceDetail.api_docs_url" target="_blank" class="text-blue-600 hover:underline">
                View Docs →
              </a>
              <p v-else class="text-gray-400">Not provided</p>
            </div>
            <div class="info-item">
              <label>Created At</label>
              <p>{{ formatDate(serviceDetail.created_at) }}</p>
            </div>
            <div class="info-item">
              <label>Status</label>
              <div class="flex items-center gap-2">
                <span :class="serviceDetail.enabled ? 'status-badge-active' : 'status-badge-inactive'">
                  {{ serviceDetail.enabled ? '✓ Active' : '○ Inactive' }}
                </span>
                <button @click="toggleServiceEnabled" class="btn-sm">
                  {{ serviceDetail.enabled ? 'Disable' : 'Enable' }}
                </button>
              </div>
            </div>
          </div>
        </div>

        <!-- Statistics Section -->
        <div class="section">
          <h3>📊 Statistics</h3>
          <div class="stats-grid">
            <div class="stat-card">
              <div class="stat-value">{{ serviceDetail.total_actions }}</div>
              <div class="stat-label">Total Actions</div>
            </div>
            <div class="stat-card">
              <div class="stat-value">{{ serviceDetail.enabled_actions }}</div>
              <div class="stat-label">Enabled Actions</div>
            </div>
            <div class="stat-card">
              <div class="stat-value">{{ getTotalExecutions() }}</div>
              <div class="stat-label">Total Executions</div>
            </div>
            <div class="stat-card">
              <div class="stat-value">{{ getSuccessRate() }}%</div>
              <div class="stat-label">Success Rate</div>
            </div>
          </div>
        </div>

        <!-- Actions Section -->
        <div class="section">
          <div class="flex items-center justify-between mb-4">
            <h3>🔧 Actions</h3>
            <div class="flex gap-2">
              <input
                v-model="searchQuery"
                type="text"
                placeholder="Search actions..."
                class="search-input"
              />
              <select v-model="filterGroup" class="filter-select">
                <option value="">All Groups</option>
                <option v-for="group in Object.keys(serviceDetail.actions_by_group || {})" :key="group" :value="group">
                  {{ formatActionGroup(group) }}
                </option>
              </select>
            </div>
          </div>

          <!-- Actions by Group -->
          <div v-if="Object.keys(filteredActions).length === 0" class="empty-state">
            <p>No actions found{{ searchQuery ? ' matching your search' : '' }}</p>
          </div>
          <div v-else class="actions-list">
            <div v-for="(actions, group) in filteredActions" :key="group" class="action-group">
              <div class="action-group-header" @click="toggleGroup(group)">
                <span class="action-group-title">
                  {{ expandedGroups.includes(group) ? '▼' : '▶' }}
                  {{ formatActionGroup(group) }}
                  <span class="action-count">({{ actions.length }})</span>
                </span>
                <div class="action-group-stats">
                  <span class="text-green-600">{{ getGroupEnabledCount(actions) }} enabled</span>
                </div>
              </div>

              <div v-show="expandedGroups.includes(group)" class="action-items">
                <div v-for="action in actions" :key="action.id" class="action-item">
                  <div class="action-header">
                    <div class="flex items-center gap-2">
                      <input
                        type="checkbox"
                        :checked="action.enabled"
                        @change="toggleActionEnabled(action.id, !action.enabled)"
                      />
                      <span class="action-name">{{ action.name }}</span>
                      <span class="http-method-badge" :class="`method-${action.http_method.toLowerCase()}`">
                        {{ action.http_method }}
                      </span>
                    </div>
                    <button
                      class="expand-button"
                      @click="toggleActionExpanded(action.id)"
                    >
                      {{ expandedActions.includes(action.id) ? '−' : '+' }}
                    </button>
                  </div>

                  <p class="action-description">{{ action.description }}</p>

                  <div class="action-meta">
                    <span class="font-mono text-xs">{{ action.endpoint_path }}</span>
                    <span class="text-gray-500">|</span>
                    <span class="text-xs">Tool: {{ action.tool_name }}</span>
                    <span class="text-gray-500">|</span>
                    <span class="text-xs">Pattern: {{ action.execution_pattern }}</span>
                  </div>

                  <!-- Expanded Action Details -->
                  <div v-show="expandedActions.includes(action.id)" class="action-details">
                    <!-- Parameters -->
                    <div v-if="action.parameters && action.parameters.length > 0" class="detail-section">
                      <h5>Parameters</h5>
                      <div class="parameters-list">
                        <div v-for="param in action.parameters" :key="param.name" class="parameter-item">
                          <span class="parameter-name">
                            {{ param.name }}
                            <span v-if="param.required" class="text-red-500">*</span>
                          </span>
                          <span class="parameter-type">{{ param.type }}</span>
                          <p class="parameter-description">{{ param.description }}</p>
                          <p v-if="param.default !== undefined" class="parameter-default">
                            Default: <code>{{ param.default }}</code>
                          </p>
                        </div>
                      </div>
                    </div>

                    <!-- Execution Stats -->
                    <div class="detail-section">
                      <h5>Execution Statistics</h5>
                      <div class="execution-stats">
                        <div class="stat-item">
                          <span class="stat-label">Total Executions:</span>
                          <span class="stat-value">{{ action.execution_count }}</span>
                        </div>
                        <div class="stat-item">
                          <span class="stat-label">Successful:</span>
                          <span class="stat-value text-green-600">{{ action.success_count }}</span>
                        </div>
                        <div class="stat-item">
                          <span class="stat-label">Failed:</span>
                          <span class="stat-value text-red-600">{{ action.failure_count }}</span>
                        </div>
                        <div class="stat-item">
                          <span class="stat-label">Avg Time:</span>
                          <span class="stat-value">{{ formatExecutionTime(action.average_execution_time) }}</span>
                        </div>
                        <div class="stat-item">
                          <span class="stat-label">Success Rate:</span>
                          <span class="stat-value">{{ getActionSuccessRate(action) }}%</span>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Knowledge Base Section -->
        <div v-if="serviceDetail.knowledge_entries && serviceDetail.knowledge_entries.length > 0" class="section">
          <h3>📚 Knowledge Base</h3>
          <div class="knowledge-list">
            <div v-for="entry in serviceDetail.knowledge_entries" :key="entry.id" class="knowledge-item">
              <div class="knowledge-header">
                <span class="knowledge-type">{{ formatKnowledgeType(entry.entry_type) }}</span>
                <h4>{{ entry.title }}</h4>
              </div>
              <p class="knowledge-content">{{ entry.content }}</p>
              <div v-if="entry.source_url" class="knowledge-footer">
                <a :href="entry.source_url" target="_blank" class="text-blue-600 hover:underline">
                  View Source →
                </a>
              </div>
              <div v-if="entry.tags && entry.tags.length > 0" class="knowledge-tags">
                <span v-for="tag in entry.tags" :key="tag" class="tag">{{ tag }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Footer Actions -->
      <div class="modal-footer">
        <button @click="handleDeleteService" class="btn-danger">Delete Service</button>
        <div class="flex gap-2">
          <button @click="$emit('close')" class="btn-secondary">Close</button>
          <button @click="handleEditService" class="btn-primary">Edit Configuration</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import api from '../../services/api'

const props = defineProps({
  service: {
    type: Object,
    required: true
  }
})

const emit = defineEmits(['close', 'updated'])

// State
const loading = ref(true)
const error = ref(null)
const serviceDetail = ref({})
const searchQuery = ref('')
const filterGroup = ref('')
const expandedGroups = ref([])
const expandedActions = ref([])

// Load service details
const loadServiceDetails = async () => {
  loading.value = true
  error.value = null

  try {
    const response = await api.getService(props.service.id)
    serviceDetail.value = response.data

    // Expand first group by default
    if (serviceDetail.value.actions_by_group) {
      const firstGroup = Object.keys(serviceDetail.value.actions_by_group)[0]
      if (firstGroup) {
        expandedGroups.value.push(firstGroup)
      }
    }
  } catch (err) {
    console.error('Failed to load service details:', err)
    error.value = err.response?.data?.error || 'Failed to load service details'
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadServiceDetails()
})

// Computed
const filteredActions = computed(() => {
  if (!serviceDetail.value.actions_by_group) return {}

  let actions = { ...serviceDetail.value.actions_by_group }

  // Filter by group
  if (filterGroup.value) {
    actions = { [filterGroup.value]: actions[filterGroup.value] }
  }

  // Filter by search query
  if (searchQuery.value) {
    const query = searchQuery.value.toLowerCase()
    const filtered = {}

    for (const [group, groupActions] of Object.entries(actions)) {
      const matchingActions = groupActions.filter(action =>
        action.name.toLowerCase().includes(query) ||
        action.description.toLowerCase().includes(query) ||
        action.tool_name.toLowerCase().includes(query) ||
        action.endpoint_path.toLowerCase().includes(query)
      )

      if (matchingActions.length > 0) {
        filtered[group] = matchingActions
      }
    }

    return filtered
  }

  return actions
})

// Methods
const toggleGroup = (group) => {
  const index = expandedGroups.value.indexOf(group)
  if (index > -1) {
    expandedGroups.value.splice(index, 1)
  } else {
    expandedGroups.value.push(group)
  }
}

const toggleActionExpanded = (actionId) => {
  const index = expandedActions.value.indexOf(actionId)
  if (index > -1) {
    expandedActions.value.splice(index, 1)
  } else {
    expandedActions.value.push(actionId)
  }
}

const toggleServiceEnabled = async () => {
  try {
    await api.updateService(props.service.id, {
      enabled: !serviceDetail.value.enabled
    })

    serviceDetail.value.enabled = !serviceDetail.value.enabled
    emit('updated')
  } catch (err) {
    console.error('Failed to toggle service:', err)
    alert('Failed to update service status')
  }
}

const toggleActionEnabled = async (actionId, enabled) => {
  try {
    // This would need a new endpoint to update individual actions
    // For now, just update locally
    for (const group in serviceDetail.value.actions_by_group) {
      const action = serviceDetail.value.actions_by_group[group].find(a => a.id === actionId)
      if (action) {
        action.enabled = enabled
        break
      }
    }

    // Update enabled count
    let enabledCount = 0
    for (const group in serviceDetail.value.actions_by_group) {
      enabledCount += serviceDetail.value.actions_by_group[group].filter(a => a.enabled).length
    }
    serviceDetail.value.enabled_actions = enabledCount

    emit('updated')
  } catch (err) {
    console.error('Failed to toggle action:', err)
    alert('Failed to update action status')
  }
}

const handleDeleteService = async () => {
  if (!confirm(`Are you sure you want to delete "${serviceDetail.value.name}"? This will delete all ${serviceDetail.value.total_actions} actions and cannot be undone.`)) {
    return
  }

  try {
    await api.deleteService(props.service.id)
    emit('updated')
    emit('close')
  } catch (err) {
    console.error('Failed to delete service:', err)
    alert('Failed to delete service')
  }
}

const handleEditService = () => {
  // Could open an edit modal or switch to edit mode
  alert('Edit functionality coming soon')
}

// Utility functions
const formatAuthType = (authType) => {
  const types = {
    'bearer': 'Bearer Token',
    'api_key': 'API Key',
    'oauth2': 'OAuth 2.0',
    'basic': 'Basic Auth',
    'none': 'No Authentication'
  }
  return types[authType] || authType
}

const formatCategory = (category) => {
  return category.split('_').map(word =>
    word.charAt(0).toUpperCase() + word.slice(1)
  ).join(' ')
}

const formatActionGroup = (group) => {
  return group.split('_').map(word =>
    word.charAt(0).toUpperCase() + word.slice(1)
  ).join(' ')
}

const formatKnowledgeType = (type) => {
  const types = {
    'api_docs': '📖 API Documentation',
    'example': '💡 Example',
    'guide': '📝 Guide',
    'faq': '❓ FAQ',
    'best_practice': '⭐ Best Practice'
  }
  return types[type] || type
}

const formatDate = (dateString) => {
  if (!dateString) return 'N/A'
  const date = new Date(dateString)
  return date.toLocaleDateString() + ' ' + date.toLocaleTimeString()
}

const formatExecutionTime = (ms) => {
  if (!ms) return 'N/A'
  if (ms < 1000) return `${Math.round(ms)}ms`
  return `${(ms / 1000).toFixed(2)}s`
}

const getGroupEnabledCount = (actions) => {
  return actions.filter(a => a.enabled).length
}

const getTotalExecutions = () => {
  let total = 0
  for (const group in serviceDetail.value.actions_by_group || {}) {
    for (const action of serviceDetail.value.actions_by_group[group]) {
      total += action.execution_count || 0
    }
  }
  return total
}

const getSuccessRate = () => {
  let totalExecutions = 0
  let totalSuccesses = 0

  for (const group in serviceDetail.value.actions_by_group || {}) {
    for (const action of serviceDetail.value.actions_by_group[group]) {
      totalExecutions += action.execution_count || 0
      totalSuccesses += action.success_count || 0
    }
  }

  if (totalExecutions === 0) return 0
  return Math.round((totalSuccesses / totalExecutions) * 100)
}

const getActionSuccessRate = (action) => {
  if (action.execution_count === 0) return 0
  return Math.round((action.success_count / action.execution_count) * 100)
}
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: 20px;
}

.service-detail-modal {
  width: 100%;
  max-width: 1200px;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
}

.modal-content {
  background: white;
  border-radius: 12px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
  overflow: hidden;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 24px;
  border-bottom: 1px solid #e5e7eb;
}

.modal-header h2 {
  margin: 0;
  font-size: 24px;
  font-weight: 600;
}

.close-button {
  background: none;
  border: none;
  font-size: 24px;
  cursor: pointer;
  color: #6b7280;
  padding: 8px;
  line-height: 1;
}

.close-button:hover {
  color: #1f2937;
}

.modal-body {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
}

.modal-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 24px;
  border-top: 1px solid #e5e7eb;
  background: #f9fafb;
}

.section {
  margin-bottom: 32px;
}

.section h3 {
  font-size: 18px;
  font-weight: 600;
  margin-bottom: 16px;
  color: #1f2937;
}

/* Info Grid */
.info-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
}

.info-item label {
  display: block;
  font-size: 12px;
  font-weight: 600;
  color: #6b7280;
  text-transform: uppercase;
  margin-bottom: 4px;
}

.info-item p {
  margin: 0;
  color: #1f2937;
}

/* Stats Grid */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}

.stat-card {
  background: #f9fafb;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 16px;
  text-align: center;
}

.stat-value {
  font-size: 32px;
  font-weight: 700;
  color: #1f2937;
  margin-bottom: 4px;
}

.stat-label {
  font-size: 12px;
  color: #6b7280;
  text-transform: uppercase;
}

/* Search and Filter */
.search-input {
  padding: 8px 12px;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  font-size: 14px;
  width: 250px;
}

.filter-select {
  padding: 8px 12px;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  font-size: 14px;
}

/* Actions List */
.actions-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.action-group {
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  overflow: hidden;
}

.action-group-header {
  background: #f9fafb;
  padding: 12px 16px;
  cursor: pointer;
  display: flex;
  justify-content: space-between;
  align-items: center;
  user-select: none;
}

.action-group-header:hover {
  background: #f3f4f6;
}

.action-group-title {
  font-weight: 600;
  color: #1f2937;
}

.action-count {
  color: #6b7280;
  font-weight: 400;
  margin-left: 8px;
}

.action-group-stats {
  font-size: 14px;
}

.action-items {
  padding: 8px;
}

.action-item {
  padding: 12px;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  margin-bottom: 8px;
  background: white;
}

.action-item:last-child {
  margin-bottom: 0;
}

.action-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.action-name {
  font-weight: 600;
  color: #1f2937;
}

.http-method-badge {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
}

.method-get { background: #dbeafe; color: #1e40af; }
.method-post { background: #d1fae5; color: #065f46; }
.method-put { background: #fef3c7; color: #92400e; }
.method-patch { background: #fce7f3; color: #831843; }
.method-delete { background: #fee2e2; color: #991b1b; }

.action-description {
  font-size: 14px;
  color: #6b7280;
  margin: 4px 0;
}

.action-meta {
  display: flex;
  gap: 8px;
  font-size: 12px;
  color: #9ca3af;
  margin-top: 8px;
}

.expand-button {
  background: #f3f4f6;
  border: none;
  border-radius: 4px;
  width: 24px;
  height: 24px;
  cursor: pointer;
  font-weight: 700;
  color: #6b7280;
}

.expand-button:hover {
  background: #e5e7eb;
}

/* Action Details */
.action-details {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid #e5e7eb;
}

.detail-section {
  margin-bottom: 16px;
}

.detail-section h5 {
  font-size: 14px;
  font-weight: 600;
  color: #1f2937;
  margin-bottom: 8px;
}

.parameters-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.parameter-item {
  padding: 12px;
  background: #f9fafb;
  border-radius: 6px;
  font-size: 14px;
}

.parameter-name {
  font-weight: 600;
  color: #1f2937;
}

.parameter-type {
  color: #6b7280;
  font-size: 12px;
  margin-left: 8px;
}

.parameter-description {
  color: #6b7280;
  font-size: 13px;
  margin: 4px 0 0 0;
}

.parameter-default {
  color: #6b7280;
  font-size: 12px;
  margin: 4px 0 0 0;
}

.parameter-default code {
  background: #e5e7eb;
  padding: 2px 6px;
  border-radius: 3px;
  font-family: monospace;
}

.execution-stats {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px;
  background: #f9fafb;
  padding: 12px;
  border-radius: 6px;
}

.stat-item {
  display: flex;
  justify-content: space-between;
  font-size: 14px;
}

.stat-item .stat-label {
  color: #6b7280;
}

.stat-item .stat-value {
  font-weight: 600;
  color: #1f2937;
}

/* Knowledge Base */
.knowledge-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.knowledge-item {
  padding: 16px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #f9fafb;
}

.knowledge-header {
  margin-bottom: 8px;
}

.knowledge-type {
  font-size: 12px;
  font-weight: 600;
  color: #6b7280;
  text-transform: uppercase;
}

.knowledge-header h4 {
  margin: 4px 0 0 0;
  font-size: 16px;
  font-weight: 600;
  color: #1f2937;
}

.knowledge-content {
  color: #374151;
  font-size: 14px;
  line-height: 1.6;
  margin: 8px 0;
}

.knowledge-footer {
  margin-top: 8px;
}

.knowledge-tags {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}

.tag {
  background: #e5e7eb;
  padding: 4px 12px;
  border-radius: 12px;
  font-size: 12px;
  color: #374151;
}

/* Status Badge */
.status-badge-active {
  padding: 4px 12px;
  border-radius: 12px;
  background: #d1fae5;
  color: #065f46;
  font-size: 14px;
  font-weight: 600;
}

.status-badge-inactive {
  padding: 4px 12px;
  border-radius: 12px;
  background: #f3f4f6;
  color: #6b7280;
  font-size: 14px;
  font-weight: 600;
}

/* Buttons */
.btn-primary {
  background: #3b82f6;
  color: white;
  border: none;
  padding: 10px 20px;
  border-radius: 6px;
  font-weight: 600;
  cursor: pointer;
}

.btn-primary:hover {
  background: #2563eb;
}

.btn-secondary {
  background: white;
  color: #374151;
  border: 1px solid #d1d5db;
  padding: 10px 20px;
  border-radius: 6px;
  font-weight: 600;
  cursor: pointer;
}

.btn-secondary:hover {
  background: #f9fafb;
}

.btn-danger {
  background: #ef4444;
  color: white;
  border: none;
  padding: 10px 20px;
  border-radius: 6px;
  font-weight: 600;
  cursor: pointer;
}

.btn-danger:hover {
  background: #dc2626;
}

.btn-sm {
  padding: 4px 12px;
  font-size: 12px;
  border-radius: 4px;
  border: 1px solid #d1d5db;
  background: white;
  cursor: pointer;
}

.btn-sm:hover {
  background: #f9fafb;
}

/* Loading & Error States */
.loading-container,
.error-container,
.empty-state {
  text-align: center;
  padding: 48px;
}

.spinner {
  border: 4px solid #f3f4f6;
  border-top: 4px solid #3b82f6;
  border-radius: 50%;
  width: 40px;
  height: 40px;
  animation: spin 1s linear infinite;
  margin: 0 auto 16px;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

/* Utility Classes */
.flex {
  display: flex;
}

.items-center {
  align-items: center;
}

.justify-between {
  justify-content: space-between;
}

.gap-2 {
  gap: 8px;
}

.gap-3 {
  gap: 12px;
}

.text-gray-400 {
  color: #9ca3af;
}

.text-gray-500 {
  color: #6b7280;
}

.text-red-600 {
  color: #dc2626;
}

.text-green-600 {
  color: #16a34a;
}

.text-blue-600 {
  color: #2563eb;
}

.hover\:underline:hover {
  text-decoration: underline;
}

.font-mono {
  font-family: monospace;
}

.text-xs {
  font-size: 12px;
}

.text-sm {
  font-size: 14px;
}
</style>
