<template>
  <div class="space-y-6">
    <header class="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
      <div>
        <h1 class="text-2xl font-bold text-gray-900">Benchmarks</h1>
        <p class="text-sm text-gray-500">
          Configure benchmark runs, track progress, and review reports.
        </p>
      </div>
      <div class="text-sm text-gray-500">
        <span v-if="lastUpdated">Last updated {{ lastUpdated }}</span>
      </div>
    </header>

    <RunConfig
      :systems="systems"
      :models="models"
      :config="runConfig"
      :running="isStarting"
      @update-config="updateRunConfig"
      @run="startRun"
    />

    <RunStatus :run="activeRun" />

    <BenchmarkDashboard
      :active-runs="activeRuns"
      :reports="reports"
    />

    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <ReportsList
        :reports="reports"
        :selected-id="selectedReportId"
        @select="selectReport"
      />
      <ReportDetail :report="selectedReport" />
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, inject, computed } from 'vue'
import api from '../services/api'
import RunConfig from '../components/benchmarks/RunConfig.vue'
import RunStatus from '../components/benchmarks/RunStatus.vue'
import BenchmarkDashboard from '../components/benchmarks/BenchmarkDashboard.vue'
import ReportsList from '../components/benchmarks/ReportsList.vue'
import ReportDetail from '../components/benchmarks/ReportDetail.vue'

const notify = inject('notify', () => {})

const systems = ref([])
const models = ref([])
const reports = ref([])
const selectedReport = ref(null)
const selectedReportId = ref(null)
const activeRun = ref(null)
const isStarting = ref(false)
const lastUpdatedAt = ref(null)
let pollingTimer = null

const runConfig = ref({
  systemId: '',
  modelIds: [],
  agentModes: ['crs-only'],
  suiteSize: 20,
  taskTypes: ['read']
})

const updateRunConfig = (nextConfig) => {
  runConfig.value = nextConfig
}

const loadInitial = async () => {
  try {
    const [systemsResponse, modelsResponse, reportsResponse] = await Promise.all([
      api.getSystems(),
      api.getLlmModels(),
      api.getBenchmarkReports()
    ])

    const systemsData = systemsResponse.data?.results || systemsResponse.data || []
    const modelsData = modelsResponse.data?.results || modelsResponse.data || []
    const reportsData = reportsResponse.data?.results || reportsResponse.data || []

    systems.value = systemsData
    models.value = modelsData
    reports.value = reportsData
    lastUpdatedAt.value = new Date()
  } catch (error) {
    console.error('Failed to load benchmark data:', error)
    notify('Failed to load benchmark data.', 'error')
  }
}

const startRun = async () => {
  if (isStarting.value) {
    return
  }

  isStarting.value = true
  try {
    const payload = {
      system_id: runConfig.value.systemId,
      model_ids: runConfig.value.modelIds,
      agent_modes: runConfig.value.agentModes,
      suite_size: runConfig.value.suiteSize,
      task_types: runConfig.value.taskTypes
    }
    const response = await api.createBenchmarkRun(payload)
    activeRun.value = response.data
    notify('Benchmark run started.', 'success')
    startPolling()
  } catch (error) {
    console.error('Failed to start benchmark run:', error)
    notify('Failed to start benchmark run.', 'error')
  } finally {
    isStarting.value = false
  }
}

const selectReport = async (id) => {
  selectedReportId.value = id
  try {
    const response = await api.getBenchmarkReport(id)
    selectedReport.value = response.data
  } catch (error) {
    console.error('Failed to load report:', error)
    notify('Failed to load report details.', 'error')
  }
}

const refreshReports = async () => {
  try {
    const response = await api.getBenchmarkReports()
    reports.value = response.data?.results || response.data || []
    lastUpdatedAt.value = new Date()
  } catch (error) {
    console.error('Failed to refresh reports:', error)
  }
}

const pollRun = async () => {
  if (!activeRun.value?.id) {
    return
  }
  try {
    const response = await api.getBenchmarkRun(activeRun.value.id)
    activeRun.value = response.data
    lastUpdatedAt.value = new Date()
    if (['completed', 'failed'].includes(activeRun.value.status)) {
      stopPolling()
      await refreshReports()
      if (activeRun.value.report_id) {
        await selectReport(activeRun.value.report_id)
      }
    }
  } catch (error) {
    console.error('Failed to poll run status:', error)
  }
}

const startPolling = () => {
  stopPolling()
  pollingTimer = window.setInterval(pollRun, 5000)
}

const stopPolling = () => {
  if (pollingTimer) {
    window.clearInterval(pollingTimer)
    pollingTimer = null
  }
}

const lastUpdated = computed(() => {
  if (!lastUpdatedAt.value) {
    return null
  }
  return lastUpdatedAt.value.toLocaleTimeString()
})

const activeRuns = computed(() => {
  if (!activeRun.value) {
    return []
  }
  if (['completed', 'failed'].includes(activeRun.value.status)) {
    return []
  }
  return [activeRun.value]
})

onMounted(async () => {
  await loadInitial()
})

onUnmounted(() => {
  stopPolling()
})
</script>
