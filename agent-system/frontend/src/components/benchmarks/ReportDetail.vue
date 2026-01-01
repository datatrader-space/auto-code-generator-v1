<template>
  <section class="bg-white shadow-sm rounded-lg border border-gray-200 p-6">
    <div class="flex items-center justify-between mb-4">
      <div>
        <h2 class="text-lg font-semibold text-gray-900">Report detail</h2>
        <p class="text-sm text-gray-500">Deep dive on the selected benchmark report.</p>
      </div>
      <a
        v-if="contextTraceLink"
        :href="contextTraceLink"
        target="_blank"
        rel="noreferrer"
        class="text-sm text-blue-600 hover:text-blue-700"
      >
        View traces
      </a>
    </div>

    <div v-if="!report" class="text-sm text-gray-500">Select a report to see details.</div>

    <div v-else>
      <div class="border-b border-gray-200 mb-4">
        <nav class="-mb-px flex space-x-6 text-sm">
          <button
            v-for="tab in tabs"
            :key="tab.key"
            class="pb-2"
            :class="activeTab === tab.key ? 'border-b-2 border-blue-500 text-blue-600' : 'text-gray-500'"
            @click="activeTab = tab.key"
          >
            {{ tab.label }}
          </button>
        </nav>
      </div>

      <div v-if="activeTab === 'summary'" class="space-y-4">
        <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div class="bg-gray-50 rounded-lg p-4">
            <p class="text-xs text-gray-500">Overall score</p>
            <p class="text-2xl font-semibold text-gray-900">{{ metrics.overall_score ?? '—' }}</p>
          </div>
          <div class="bg-gray-50 rounded-lg p-4">
            <p class="text-xs text-gray-500">Read success</p>
            <p class="text-2xl font-semibold text-gray-900">{{ metrics.read_success ?? '—' }}</p>
          </div>
          <div class="bg-gray-50 rounded-lg p-4">
            <p class="text-xs text-gray-500">Write success</p>
            <p class="text-2xl font-semibold text-gray-900">{{ metrics.write_success ?? '—' }}</p>
          </div>
        </div>
        <div class="text-sm text-gray-600">
          <p><span class="font-medium">System:</span> {{ report.system_name || report.system }}</p>
          <p><span class="font-medium">Models:</span> {{ report.models_summary || '—' }}</p>
          <p><span class="font-medium">Agent modes:</span> {{ report.mode_summary || '—' }}</p>
        </div>
        <div>
          <h3 class="text-sm font-medium text-gray-700">Downloads</h3>
          <div v-if="downloadLinks.length" class="flex flex-wrap gap-2 mt-2">
            <a
              v-for="item in downloadLinks"
              :key="item.path"
              :href="item.url"
              target="_blank"
              rel="noreferrer"
              class="text-xs text-blue-600 hover:text-blue-700 border border-blue-200 rounded-full px-3 py-1"
            >
              {{ item.label }}
            </a>
          </div>
          <p v-else class="text-xs text-gray-500 mt-2">No downloadable artifacts available.</p>
        </div>
      </div>

      <div v-else-if="activeTab === 'viewer'" class="space-y-6">
        <div>
          <h3 class="text-sm font-medium text-gray-700 mb-2">Per-mode comparison</h3>
          <div v-if="modeColumns.length" class="overflow-x-auto">
            <table class="min-w-full text-sm">
              <thead class="text-xs text-gray-500 uppercase text-left">
                <tr>
                  <th class="py-2 pr-4">Model</th>
                  <th v-for="mode in modeColumns" :key="mode" class="py-2 pr-4">
                    {{ mode }}
                  </th>
                </tr>
              </thead>
              <tbody class="divide-y divide-gray-200">
                <tr v-for="row in modeRows" :key="row.model_id">
                  <td class="py-2 pr-4 text-gray-900 font-medium">
                    {{ row.model_name }}
                  </td>
                  <td v-for="mode in modeColumns" :key="mode" class="py-2 pr-4 text-gray-600">
                    <div class="text-xs">
                      <div>Success: {{ formatRate(row.mode_metrics?.[mode]?.success_rate) }}</div>
                      <div>Latency: {{ formatLatency(row.mode_metrics?.[mode]?.avg_latency_ms) }}</div>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <p v-else class="text-sm text-gray-500">No mode comparison data available.</p>
        </div>

        <div>
          <div class="flex items-center justify-between mb-2">
            <h3 class="text-sm font-medium text-gray-700">Failed cases</h3>
            <span class="text-xs text-gray-500">{{ failedCases.length }} cases</span>
          </div>
          <div v-if="failedCases.length" class="space-y-3">
            <div
              v-for="(item, index) in failedCases"
              :key="`${item.model_id}-${item.mode}-${item.task_id}-${index}`"
              class="border border-gray-200 rounded-lg p-3"
            >
              <button
                class="w-full text-left flex items-start justify-between"
                @click="toggleCase(index)"
              >
                <div>
                  <p class="text-sm font-medium text-gray-900">
                    {{ resolveModelName(item.model_id) }} · {{ item.mode || 'unknown mode' }}
                  </p>
                  <p class="text-xs text-gray-500">Task {{ item.task_id || 'unknown' }}</p>
                </div>
                <span class="text-xs text-blue-600">
                  {{ expandedCase === index ? 'Hide' : 'View' }}
                </span>
              </button>
              <div v-if="expandedCase === index" class="mt-3 space-y-2 text-xs text-gray-600">
                <p><span class="font-medium">Task type:</span> {{ item.task_type || '—' }}</p>
                <p v-if="item.error"><span class="font-medium">Error:</span> {{ item.error }}</p>
                <p v-if="item.prompt"><span class="font-medium">Prompt:</span> {{ item.prompt }}</p>
                <pre v-if="item.details" class="bg-gray-50 rounded p-2 whitespace-pre-wrap">
{{ formatDetails(item.details) }}
                </pre>
                <a
                  v-if="contextTraceLink"
                  :href="contextTraceLink"
                  target="_blank"
                  rel="noreferrer"
                  class="inline-flex text-blue-600 hover:text-blue-700"
                >
                  Download context trace
                </a>
              </div>
            </div>
          </div>
          <p v-else class="text-sm text-gray-500">No failed cases captured.</p>
        </div>
      </div>

      <div v-else-if="activeTab === 'retrieval'" class="space-y-4">
        <h3 class="text-sm font-medium text-gray-700">Retrieval vs representation failures</h3>
        <ul class="space-y-3 text-sm">
          <li v-for="item in retrievalFailures" :key="item.label" class="flex justify-between">
            <span class="text-gray-600">{{ item.label }}</span>
            <span class="font-medium text-gray-900">{{ item.value }}</span>
          </li>
        </ul>
      </div>

      <div v-else-if="activeTab === 'verification'" class="space-y-4">
        <h3 class="text-sm font-medium text-gray-700">Write-task verification</h3>
        <ul class="space-y-3 text-sm">
          <li v-for="item in writeVerification" :key="item.label" class="flex justify-between">
            <span class="text-gray-600">{{ item.label }}</span>
            <span class="font-medium text-gray-900">{{ item.value }}</span>
          </li>
        </ul>
      </div>

      <div v-else class="space-y-4">
        <h3 class="text-sm font-medium text-gray-700">CRS backlog suggestions</h3>
        <ul class="space-y-3 text-sm">
          <li v-for="item in backlogSuggestions" :key="item.label" class="flex justify-between">
            <span class="text-gray-600">{{ item.label }}</span>
            <span class="font-medium text-gray-900">{{ item.value }}</span>
          </li>
        </ul>
      </div>
    </div>
  </section>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import api from '../../services/api'

const props = defineProps({
  report: {
    type: Object,
    default: null
  }
})

const tabs = [
  { key: 'summary', label: 'Summary metrics' },
  { key: 'viewer', label: 'Report viewer' },
  { key: 'retrieval', label: 'Retrieval vs representation' },
  { key: 'verification', label: 'Write-task verification' },
  { key: 'backlog', label: 'CRS backlog' }
]

const activeTab = ref('summary')
const expandedCase = ref(null)

watch(
  () => props.report,
  () => {
    activeTab.value = 'summary'
    expandedCase.value = null
  }
)

const metrics = computed(() => props.report?.summary_metrics || {})
const modelSummaries = computed(() => props.report?.model_summaries || {})
const downloads = computed(() => props.report?.downloads || [])
const failedCases = computed(() => props.report?.failed_cases || [])

const toggleCase = (index) => {
  expandedCase.value = expandedCase.value === index ? null : index
}

const modeColumns = computed(() => {
  const modes = new Set()
  Object.values(modelSummaries.value || {}).forEach((summary) => {
    const modeMetrics = summary?.mode_metrics || {}
    Object.keys(modeMetrics).forEach((mode) => modes.add(mode))
  })
  return Array.from(modes)
})

const modeRows = computed(() => {
  const summaries = modelSummaries.value || {}
  return Object.entries(summaries).map(([modelId, summary]) => {
    return {
      model_id: modelId,
      model_name: resolveModelName(modelId),
      mode_metrics: summary.mode_metrics || {}
    }
  })
})

const downloadLinks = computed(() => {
  if (!props.report?.id) {
    return []
  }
  return downloads.value.map((item) => ({
    ...item,
    url: api.getBenchmarkReportDownloadUrl(props.report.id, item.path)
  }))
})

const contextTraceLink = computed(() => {
  const trace = downloads.value.find((item) => item.kind === 'context_trace')
  if (!trace || !props.report?.id) {
    return null
  }
  return api.getBenchmarkReportDownloadUrl(props.report.id, trace.path)
})

const retrievalFailures = computed(() => {
  const failures = props.report?.failure_taxonomy || {}
  return [
    { label: 'Retrieval misses', value: failures.retrieval_misses ?? '—' },
    { label: 'Representation drift', value: failures.representation_drift ?? '—' },
    { label: 'Ambiguous instructions', value: failures.ambiguous_instructions ?? '—' }
  ]
})

const writeVerification = computed(() => {
  const verification = props.report?.write_verification || {}
  return [
    { label: 'Verified writes', value: verification.verified ?? '—' },
    { label: 'Failed tests', value: verification.failed_tests ?? '—' },
    { label: 'Manual review', value: verification.manual_review ?? '—' }
  ]
})

const backlogSuggestions = computed(() => {
  const backlog = props.report?.crs_backlog || {}
  return [
    { label: 'Index gaps', value: backlog.index_gaps ?? '—' },
    { label: 'Prompt updates', value: backlog.prompt_updates ?? '—' },
    { label: 'Workflow changes', value: backlog.workflow_changes ?? '—' }
  ]
})

const resolveModelName = (modelId) => {
  const models = props.report?.models || []
  const match = models.find((model) => String(model.model_id) === String(modelId))
  return match?.name || modelId || 'Unknown model'
}

const formatRate = (value) => {
  if (value === null || value === undefined) {
    return '—'
  }
  return `${Math.round(value * 100)}%`
}

const formatLatency = (value) => {
  if (value === null || value === undefined) {
    return '—'
  }
  return `${Math.round(value)} ms`
}

const formatDetails = (details) => {
  if (!details) {
    return ''
  }
  if (typeof details === 'string') {
    return details
  }
  return JSON.stringify(details, null, 2)
}
</script>
