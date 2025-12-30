<template>
  <div class="crs-dashboard">
    <!-- Header -->
    <div class="dashboard-header">
      <h2 class="text-2xl font-bold text-gray-900">CRS Pipeline</h2>
      <div class="flex items-center space-x-4">
        <span v-if="connected" class="flex items-center text-sm text-green-600">
          <span class="w-2 h-2 bg-green-500 rounded-full mr-2"></span>
          Live
        </span>
        <span v-else class="flex items-center text-sm text-gray-400">
          <span class="w-2 h-2 bg-gray-300 rounded-full mr-2"></span>
          Disconnected
        </span>
        <button
          @click="refreshStatus"
          class="px-3 py-1 text-sm bg-blue-600 text-white rounded hover:bg-blue-700"
        >
          Refresh Status
        </button>
      </div>
    </div>

    <!-- Pipeline Steps -->
    <div class="pipeline-steps">
      <div
        v-for="step in steps"
        :key="step.name"
        class="step-card"
        :class="stepCardClass(step)"
      >
        <!-- Step Header -->
        <div class="step-header">
          <div class="flex items-center space-x-3">
            <div class="step-icon" :class="stepIconClass(step)">
              {{ stepIcon(step) }}
            </div>
            <div>
              <h3 class="font-semibold text-gray-900">{{ step.label }}</h3>
              <p class="text-sm text-gray-500">{{ step.description }}</p>
            </div>
          </div>

          <!-- Step Controls -->
          <div class="step-controls">
            <button
              @click="runStep(step.name, false)"
              :disabled="step.status === 'running' || !canRunStep(step)"
              class="btn btn-primary"
            >
              <span v-if="step.status === 'running'">Running...</span>
              <span v-else>Run</span>
            </button>
            <button
              @click="runStep(step.name, true)"
              :disabled="step.status === 'running'"
              class="btn btn-secondary"
              title="Force rerun"
            >
              🔄 Force
            </button>
          </div>
        </div>

        <!-- Step Progress -->
        <div v-if="step.progress" class="step-progress">
          <div class="progress-bar">
            <div
              class="progress-fill"
              :style="{ width: step.progress.percentage + '%' }"
            ></div>
          </div>
          <p class="text-sm text-gray-600 mt-1">
            {{ step.progress.message || `${step.progress.current}/${step.progress.total}` }}
            ({{ step.progress.percentage }}%)
          </p>
        </div>

        <!-- Step Result -->
        <div v-if="step.result && step.status === 'complete'" class="step-result">
          <div class="text-sm text-gray-700">
            <div v-if="step.result.file_count">
              ✓ Files: {{ step.result.file_count }}
            </div>
            <div v-if="step.result.artifacts_count">
              ✓ Artifacts: {{ step.result.artifacts_count }}
            </div>
            <div v-if="step.result.relationships_count">
              ✓ Relationships: {{ step.result.relationships_count }}
            </div>
            <div v-if="step.result.duration">
              ⏱ Duration: {{ step.result.duration.toFixed(2) }}s
            </div>
          </div>
        </div>

        <!-- Step Error -->
        <div v-if="step.error" class="step-error">
          <p class="font-semibold text-red-700">Error: {{ step.error.error }}</p>
          <p class="text-sm text-red-600">{{ step.error.error_type }}</p>
        </div>
      </div>
    </div>

    <!-- Live Logs -->
    <div class="logs-section">
      <div class="logs-header">
        <h3 class="font-semibold text-gray-900">Live Logs</h3>
        <div class="logs-controls">
          <select v-model="logFilter" class="log-filter">
            <option value="all">All Logs</option>
            <option value="info">Info</option>
            <option value="warning">Warning</option>
            <option value="error">Errors Only</option>
          </select>
          <button @click="clearLogs" class="btn btn-sm">Clear</button>
        </div>
      </div>

      <div ref="logsContainer" class="logs-container">
        <div
          v-for="(log, index) in filteredLogs"
          :key="index"
          class="log-entry"
          :class="`log-${log.level}`"
        >
          <span class="log-time">{{ formatTime(log.timestamp) }}</span>
          <span class="log-step">[{{ log.step_name }}]</span>
          <span class="log-message">{{ log.message }}</span>
        </div>
        <div v-if="filteredLogs.length === 0" class="text-gray-400 text-center py-4">
          No logs yet. Run a pipeline step to see live updates.
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import api from '../services/api'

const props = defineProps({
  repositoryId: {
    type: Number,
    required: true
  },
  systemId: {
    type: Number,
    required: true
  }
})

// State
const steps = ref([
  {
    name: 'blueprints',
    label: 'Blueprints',
    description: 'Index source files',
    status: 'pending', // pending, running, complete, error, skipped
    progress: null,
    result: null,
    error: null
  },
  {
    name: 'artifacts',
    label: 'Artifacts',
    description: 'Extract code artifacts',
    status: 'pending',
    progress: null,
    result: null,
    error: null
  },
  {
    name: 'relationships',
    label: 'Relationships',
    description: 'Build relationship graph',
    status: 'pending',
    progress: null,
    result: null,
    error: null
  },
  {
    name: 'impact',
    label: 'Impact Analysis',
    description: 'Analyze change impact',
    status: 'pending',
    progress: null,
    result: null,
    error: null
  }
])

const logs = ref([])
const logFilter = ref('all')
const connected = ref(false)
const logsContainer = ref(null)

let eventSource = null

// Computed
const filteredLogs = computed(() => {
  if (logFilter.value === 'all') return logs.value
  return logs.value.filter(log => log.level === logFilter.value)
})

// Methods
const stepCardClass = (step) => {
  return {
    'step-pending': step.status === 'pending',
    'step-running': step.status === 'running',
    'step-complete': step.status === 'complete',
    'step-error': step.status === 'error',
    'step-skipped': step.status === 'skipped'
  }
}

const stepIconClass = (step) => {
  return {
    'icon-pending': step.status === 'pending',
    'icon-running': step.status === 'running',
    'icon-complete': step.status === 'complete',
    'icon-error': step.status === 'error'
  }
}

const stepIcon = (step) => {
  if (step.status === 'running') return '⏳'
  if (step.status === 'complete') return '✅'
  if (step.status === 'error') return '❌'
  if (step.status === 'skipped') return '⏭'
  return '⏸'
}

const canRunStep = (step) => {
  // Can always run blueprints
  if (step.name === 'blueprints') return true

  // For other steps, blueprints must be complete
  const blueprintsStep = steps.value.find(s => s.name === 'blueprints')
  if (blueprintsStep.status !== 'complete') return false

  // Artifacts needs blueprints
  if (step.name === 'artifacts') return true

  // Relationships needs artifacts
  if (step.name === 'relationships') {
    const artifactsStep = steps.value.find(s => s.name === 'artifacts')
    return artifactsStep.status === 'complete'
  }

  return true
}

const runStep = async (stepName, force = false) => {
  const step = steps.value.find(s => s.name === stepName)
  if (!step) return

  step.status = 'running'
  step.progress = null
  step.result = null
  step.error = null

  try {
    const response = await api.post(
      `/systems/${props.systemId}/repositories/${props.repositoryId}/crs/steps/${stepName}/run/`,
      { force }
    )

    if (response.data.result && response.data.result.skipped) {
      step.status = 'skipped'
    } else {
      step.status = 'complete'
      step.result = response.data.result?.result || {}
    }
  } catch (error) {
    console.error(`Step ${stepName} failed:`, error)
    step.status = 'error'
    step.error = {
      error: error.response?.data?.error || error.message,
      error_type: error.response?.data?.type || 'Error'
    }
  }
}

const refreshStatus = async () => {
  try {
    const response = await api.get(
      `/systems/${props.systemId}/repositories/${props.repositoryId}/crs/steps/status/`
    )

    const status = response.data

    // Update step statuses based on decision
    if (status.decision) {
      steps.value.forEach(step => {
        // Check if file exists
        const fileExists = status.files_exist?.[step.name]
        if (fileExists) {
          step.status = 'complete'
        } else {
          step.status = 'pending'
        }
      })
    }
  } catch (error) {
    console.error('Failed to refresh status:', error)
  }
}

const clearLogs = () => {
  logs.value = []
}

const formatTime = (timestamp) => {
  const date = new Date(timestamp * 1000)
  return date.toLocaleTimeString()
}

const connectEventSource = () => {
  const url = `/api/systems/${props.systemId}/repositories/${props.repositoryId}/crs/events/`

  eventSource = new EventSource(url)

  eventSource.onopen = () => {
    connected.value = true
    console.log('SSE connected')
  }

  eventSource.onerror = () => {
    connected.value = false
    console.error('SSE connection error')
  }

  eventSource.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)
      handleEvent(data)
    } catch (error) {
      console.error('Failed to parse SSE event:', error)
    }
  }
}

const handleEvent = (event) => {
  const { event_type, step_name, data } = event

  const step = steps.value.find(s => s.name === step_name)

  switch (event_type) {
    case 'step_start':
      if (step) {
        step.status = 'running'
        step.progress = null
        step.result = null
        step.error = null
      }
      break

    case 'step_progress':
      if (step && data) {
        step.progress = {
          current: data.current,
          total: data.total,
          percentage: data.percentage,
          message: data.message
        }
      }
      break

    case 'step_log':
      if (data) {
        logs.value.push({
          timestamp: event.timestamp,
          step_name: step_name || 'system',
          level: data.level || 'info',
          message: data.message
        })
        // Auto-scroll to bottom
        nextTick(() => {
          if (logsContainer.value) {
            logsContainer.value.scrollTop = logsContainer.value.scrollHeight
          }
        })
      }
      break

    case 'step_complete':
      if (step) {
        step.status = 'complete'
        step.result = data?.result || {}
        step.progress = null
      }
      break

    case 'step_error':
      if (step && data) {
        step.status = 'error'
        step.error = {
          error: data.error,
          error_type: data.error_type,
          traceback: data.traceback
        }
      }
      break
  }
}

// Lifecycle
onMounted(() => {
  refreshStatus()
  connectEventSource()
})

onUnmounted(() => {
  if (eventSource) {
    eventSource.close()
  }
})
</script>

<style scoped>
.crs-dashboard {
  @apply space-y-6;
}

.dashboard-header {
  @apply flex justify-between items-center pb-4 border-b;
}

.pipeline-steps {
  @apply grid gap-4;
}

.step-card {
  @apply border rounded-lg p-4 transition-all;
}

.step-pending {
  @apply bg-gray-50 border-gray-200;
}

.step-running {
  @apply bg-blue-50 border-blue-300 shadow-md;
}

.step-complete {
  @apply bg-green-50 border-green-300;
}

.step-error {
  @apply bg-red-50 border-red-300;
}

.step-skipped {
  @apply bg-gray-100 border-gray-300;
}

.step-header {
  @apply flex justify-between items-start;
}

.step-icon {
  @apply w-10 h-10 rounded-full flex items-center justify-center text-xl;
}

.icon-pending {
  @apply bg-gray-200;
}

.icon-running {
  @apply bg-blue-200 animate-pulse;
}

.icon-complete {
  @apply bg-green-200;
}

.icon-error {
  @apply bg-red-200;
}

.step-controls {
  @apply flex gap-2;
}

.btn {
  @apply px-3 py-1 rounded text-sm font-medium transition-colors;
}

.btn-primary {
  @apply bg-blue-600 text-white hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed;
}

.btn-secondary {
  @apply bg-gray-200 text-gray-700 hover:bg-gray-300 disabled:bg-gray-100 disabled:cursor-not-allowed;
}

.btn-sm {
  @apply px-2 py-1 text-xs;
}

.step-progress {
  @apply mt-3;
}

.progress-bar {
  @apply w-full bg-gray-200 rounded-full h-2;
}

.progress-fill {
  @apply bg-blue-600 h-2 rounded-full transition-all duration-300;
}

.step-result {
  @apply mt-3 p-2 bg-white rounded border border-green-200;
}

.step-error {
  @apply mt-3 p-2 bg-white rounded border border-red-300;
}

.logs-section {
  @apply border rounded-lg overflow-hidden;
}

.logs-header {
  @apply flex justify-between items-center p-3 bg-gray-50 border-b;
}

.logs-controls {
  @apply flex items-center gap-2;
}

.log-filter {
  @apply px-2 py-1 border rounded text-sm;
}

.logs-container {
  @apply bg-gray-900 text-gray-100 p-4 font-mono text-sm h-96 overflow-y-auto;
}

.log-entry {
  @apply py-1 border-l-2 pl-2 mb-1;
}

.log-info {
  @apply border-blue-500;
}

.log-warning {
  @apply border-yellow-500 text-yellow-300;
}

.log-error {
  @apply border-red-500 text-red-300;
}

.log-time {
  @apply text-gray-400 text-xs mr-2;
}

.log-step {
  @apply text-blue-400 mr-2;
}

.log-message {
  @apply text-gray-100;
}
</style>
