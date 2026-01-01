<template>
  <section class="bg-white shadow-sm rounded-lg border border-gray-200 p-6">
    <div class="flex items-center justify-between mb-4">
      <div>
        <h2 class="text-lg font-semibold text-gray-900">Dashboard</h2>
        <p class="text-sm text-gray-500">Active runs and completed model comparisons.</p>
      </div>
    </div>

    <div class="space-y-6">
      <div>
        <h3 class="text-sm font-medium text-gray-700 mb-3">Active runs</h3>
        <div v-if="activeRuns.length" class="space-y-3">
          <div
            v-for="run in activeRuns"
            :key="run.id || run.run_id"
            class="border border-gray-200 rounded-lg p-4"
          >
            <div class="flex items-start justify-between mb-2">
              <div>
                <p class="text-sm font-medium text-gray-900">Run {{ run.id || run.run_id }}</p>
                <p class="text-xs text-gray-500">{{ formatDate(run.started_at) }}</p>
              </div>
              <span
                class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium"
                :class="statusClass(run.status)"
              >
                {{ run.status || 'running' }}
              </span>
            </div>
            <div class="space-y-2">
              <div class="flex justify-between text-xs text-gray-500">
                <span>Progress</span>
                <span>{{ progressPercent(run) }}%</span>
              </div>
              <div class="w-full h-2 bg-gray-200 rounded-full">
                <div
                  class="h-2 rounded-full bg-blue-500 transition-all"
                  :style="{ width: `${progressPercent(run)}%` }"
                ></div>
              </div>
              <p class="text-xs text-gray-500">
                ETA: {{ etaLabel(run) }}
              </p>
            </div>
          </div>
        </div>
        <p v-else class="text-sm text-gray-500">No active benchmark runs.</p>
      </div>

      <div>
        <div class="flex items-center justify-between mb-3">
          <h3 class="text-sm font-medium text-gray-700">Completed runs</h3>
          <div class="flex items-center gap-2 text-xs text-gray-500">
            <span>Sort by</span>
            <select
              v-model="sortKey"
              class="border border-gray-200 rounded px-2 py-1 text-xs text-gray-600"
            >
              <option value="created_at">Most recent</option>
              <option value="overall_score">Overall score</option>
              <option value="best_model">Best model</option>
              <option value="avg_latency_ms">Avg latency</option>
            </select>
            <button
              class="text-blue-600 hover:text-blue-700"
              @click="toggleSortDirection"
            >
              {{ sortDirection === 'asc' ? 'Asc' : 'Desc' }}
            </button>
          </div>
        </div>

        <div v-if="sortedReports.length" class="overflow-x-auto">
          <table class="min-w-full text-sm">
            <thead class="text-xs text-gray-500 uppercase text-left">
              <tr>
                <th class="py-2 pr-4">Run</th>
                <th class="py-2 pr-4">Models</th>
                <th class="py-2 pr-4">Overall score</th>
                <th class="py-2 pr-4">Top model</th>
                <th class="py-2">Avg latency</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-gray-200">
              <tr v-for="report in sortedReports" :key="report.id">
                <td class="py-2 pr-4">
                  <p class="font-medium text-gray-900">{{ report.title || report.id }}</p>
                  <p class="text-xs text-gray-500">{{ formatDate(report.created_at) }}</p>
                </td>
                <td class="py-2 pr-4 text-gray-600">
                  {{ report.models_summary || '—' }}
                </td>
                <td class="py-2 pr-4 text-gray-600">
                  {{ formatScore(report.summary_metrics?.overall_score) }}
                </td>
                <td class="py-2 pr-4 text-gray-600">
                  {{ bestModelLabel(report) }}
                </td>
                <td class="py-2 text-gray-600">
                  {{ formatLatency(bestModelLatency(report)) }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <p v-else class="text-sm text-gray-500">No completed benchmark reports yet.</p>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  activeRuns: {
    type: Array,
    default: () => []
  },
  reports: {
    type: Array,
    default: () => []
  }
})

const sortKey = ref('created_at')
const sortDirection = ref('desc')

const sortedReports = computed(() => {
  const reports = [...props.reports]
  const direction = sortDirection.value === 'asc' ? 1 : -1
  return reports.sort((a, b) => {
    const valueA = sortValue(a, sortKey.value)
    const valueB = sortValue(b, sortKey.value)
    if (valueA === valueB) {
      return 0
    }
    if (valueA === null) {
      return 1
    }
    if (valueB === null) {
      return -1
    }
    return valueA > valueB ? direction : -direction
  })
})

const sortValue = (report, key) => {
  if (key === 'overall_score') {
    return report.summary_metrics?.overall_score ?? null
  }
  if (key === 'best_model') {
    return bestModelLabel(report) || null
  }
  if (key === 'avg_latency_ms') {
    return bestModelLatency(report)
  }
  if (key === 'created_at') {
    return report.created_at ? new Date(report.created_at).getTime() : null
  }
  return null
}

const toggleSortDirection = () => {
  sortDirection.value = sortDirection.value === 'asc' ? 'desc' : 'asc'
}

const progressPercent = (run) => {
  const progress = run?.progress ?? 0
  return Math.min(100, Math.max(0, Math.round(progress)))
}

const etaLabel = (run) => {
  if (!run?.started_at) {
    return '—'
  }
  const progress = progressPercent(run)
  if (progress <= 0 || progress >= 100) {
    return '—'
  }
  const startedAt = new Date(run.started_at)
  const elapsedMs = Date.now() - startedAt.getTime()
  if (elapsedMs <= 0) {
    return '—'
  }
  const remainingMs = (elapsedMs / progress) * (100 - progress)
  const minutes = Math.round(remainingMs / 60000)
  if (minutes < 1) {
    return 'Less than a minute'
  }
  if (minutes < 60) {
    return `${minutes} min`
  }
  const hours = Math.floor(minutes / 60)
  const remainder = minutes % 60
  return `${hours}h ${remainder}m`
}

const statusClass = (status) => {
  if (status === 'completed') {
    return 'bg-green-100 text-green-800'
  }
  if (status === 'failed') {
    return 'bg-red-100 text-red-800'
  }
  if (status === 'running') {
    return 'bg-blue-100 text-blue-800'
  }
  return 'bg-gray-100 text-gray-700'
}

const formatDate = (value) => {
  if (!value) {
    return 'Unknown date'
  }
  const date = new Date(value)
  return date.toLocaleString()
}

const formatScore = (value) => {
  if (value === null || value === undefined) {
    return '—'
  }
  return value.toFixed(2)
}

const bestModelLabel = (report) => {
  const top = report.model_ranking?.[0]
  if (!top) {
    return '—'
  }
  return resolveModelName(report, top.model_id)
}

const bestModelLatency = (report) => {
  const top = report.model_ranking?.[0]
  if (!top) {
    return null
  }
  return top.avg_latency_ms ?? null
}

const resolveModelName = (report, modelId) => {
  const match = report.models?.find((model) => String(model.model_id) === String(modelId))
  return match?.name || modelId
}

const formatLatency = (value) => {
  if (value === null || value === undefined) {
    return '—'
  }
  return `${Math.round(value)} ms`
}
</script>
