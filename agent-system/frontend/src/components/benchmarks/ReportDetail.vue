<template>
  <section class="bg-white shadow-sm rounded-lg border border-gray-200 p-6">
    <div class="flex items-center justify-between mb-4">
      <div>
        <h2 class="text-lg font-semibold text-gray-900">Report detail</h2>
        <p class="text-sm text-gray-500">Deep dive on the selected benchmark report.</p>
      </div>
      <a
        v-if="report?.trace_url"
        :href="report.trace_url"
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

const props = defineProps({
  report: {
    type: Object,
    default: null
  }
})

const tabs = [
  { key: 'summary', label: 'Summary metrics' },
  { key: 'retrieval', label: 'Retrieval vs representation' },
  { key: 'verification', label: 'Write-task verification' },
  { key: 'backlog', label: 'CRS backlog' }
]

const activeTab = ref('summary')

watch(
  () => props.report,
  () => {
    activeTab.value = 'summary'
  }
)

const metrics = computed(() => props.report?.summary_metrics || {})

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
</script>
