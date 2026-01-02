<template>
  <section class="bg-white shadow-sm rounded-lg border border-gray-200 p-6">
    <div class="flex items-center justify-between mb-4">
      <div>
        <h2 class="text-lg font-semibold text-gray-900">Reports</h2>
        <p class="text-sm text-gray-500">Past benchmark runs and exports.</p>
      </div>
    </div>

    <div v-if="reports.length" class="space-y-3">
      <button
        v-for="report in reports"
        :key="report.id"
        class="w-full text-left border rounded-lg px-4 py-3 transition"
        :class="selectedId === report.id ? 'border-blue-500 bg-blue-50' : 'border-gray-200 hover:border-gray-300'"
        @click="emit('select', report.id)"
      >
        <div class="flex justify-between items-start">
          <div>
            <p class="text-sm font-medium text-gray-900">{{ report.title || `Run #${report.id}` }}</p>
            <p class="text-xs text-gray-500">
              {{ report.system_name || report.system || 'Unknown system' }}
            </p>
          </div>
          <span class="text-xs text-gray-500">{{ formatDate(report.created_at) }}</span>
        </div>
        <div class="mt-2 flex flex-wrap gap-2 text-xs">
          <span class="px-2 py-0.5 rounded-full bg-gray-100 text-gray-600">
            {{ report.models_summary || `${report.model_count || 0} models` }}
          </span>
          <span class="px-2 py-0.5 rounded-full bg-gray-100 text-gray-600">
            {{ report.mode_summary || `${report.agent_modes?.length || 0} modes` }}
          </span>
          <span class="px-2 py-0.5 rounded-full bg-gray-100 text-gray-600">
            {{ report.task_summary || `${report.task_types?.length || 0} task types` }}
          </span>
        </div>
      </button>
    </div>

    <div v-else class="text-sm text-gray-500">No benchmark reports yet.</div>
  </section>
</template>

<script setup>
const props = defineProps({
  reports: {
    type: Array,
    default: () => []
  },
  selectedId: {
    type: [String, Number],
    default: null
  }
})

const emit = defineEmits(['select'])

const formatDate = (value) => {
  if (!value) {
    return 'Unknown date'
  }
  const date = new Date(value)
  return date.toLocaleDateString()
}
</script>
