<template>
  <section class="bg-white shadow-sm rounded-lg border border-gray-200 p-6">
    <div class="flex items-center justify-between mb-4">
      <div>
        <h2 class="text-lg font-semibold text-gray-900">Run status</h2>
        <p class="text-sm text-gray-500">Live progress for the active benchmark run.</p>
      </div>
      <span
        class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium"
        :class="statusClass"
      >
        {{ statusLabel }}
      </span>
    </div>

    <div class="space-y-4">
      <div>
        <div class="flex justify-between text-xs text-gray-500 mb-1">
          <span>Progress</span>
          <span>{{ progressPercent }}%</span>
        </div>
        <div class="w-full h-2 bg-gray-200 rounded-full">
          <div
            class="h-2 rounded-full bg-blue-500 transition-all"
            :style="{ width: `${progressPercent}%` }"
          ></div>
        </div>
      </div>

      <div class="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
        <div class="bg-gray-50 rounded-lg p-3">
          <p class="text-xs text-gray-500">Queued</p>
          <p class="text-lg font-semibold text-gray-900">{{ counts.queued }}</p>
        </div>
        <div class="bg-gray-50 rounded-lg p-3">
          <p class="text-xs text-gray-500">Running</p>
          <p class="text-lg font-semibold text-gray-900">{{ counts.running }}</p>
        </div>
        <div class="bg-gray-50 rounded-lg p-3">
          <p class="text-xs text-gray-500">Succeeded</p>
          <p class="text-lg font-semibold text-gray-900">{{ counts.succeeded }}</p>
        </div>
        <div class="bg-gray-50 rounded-lg p-3">
          <p class="text-xs text-gray-500">Failed</p>
          <p class="text-lg font-semibold text-gray-900">{{ counts.failed }}</p>
        </div>
      </div>

      <div class="text-xs text-gray-500">
        <p v-if="run?.started_at">Started {{ formatDate(run.started_at) }}</p>
        <p v-if="run?.updated_at">Last update {{ formatDate(run.updated_at) }}</p>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  run: {
    type: Object,
    default: null
  }
})

const statusLabel = computed(() => props.run?.status || 'Idle')

const statusClass = computed(() => {
  const status = props.run?.status
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
})

const progressPercent = computed(() => {
  if (!props.run) {
    return 0
  }
  const progress = props.run.progress ?? 0
  return Math.min(100, Math.max(0, Math.round(progress)))
})

const counts = computed(() => {
  return {
    queued: props.run?.counts?.queued ?? 0,
    running: props.run?.counts?.running ?? 0,
    succeeded: props.run?.counts?.succeeded ?? 0,
    failed: props.run?.counts?.failed ?? 0
  }
})

const formatDate = (value) => {
  const date = new Date(value)
  return date.toLocaleString()
}
</script>
