<template>
  <div
    v-if="results.length > 0"
    class="execution-results-panel fixed bottom-4 right-4 w-96 max-h-[600px] bg-white rounded-lg shadow-2xl border border-gray-200 flex flex-col z-40"
  >
    <!-- Header -->
    <div class="bg-gradient-to-r from-blue-600 to-blue-700 text-white px-4 py-3 rounded-t-lg flex items-center justify-between">
      <div class="flex items-center gap-2">
        <span class="text-lg">⚡</span>
        <h3 class="font-semibold text-sm">Execution Results</h3>
        <span class="bg-white/20 px-2 py-0.5 rounded-full text-xs">{{ results.length }}</span>
      </div>
      <button
        @click="$emit('clear')"
        class="text-white/80 hover:text-white text-xs px-2 py-1 hover:bg-white/10 rounded transition"
      >
        Clear All
      </button>
    </div>

    <!-- Results List -->
    <div class="overflow-y-auto flex-1 p-3 space-y-2">
      <div
        v-for="result in results"
        :key="result.id"
        class="border rounded-lg overflow-hidden transition-all"
        :class="result.success ? 'border-green-200 bg-green-50' : 'border-red-200 bg-red-50'"
      >
        <!-- Result Header -->
        <div
          class="px-3 py-2 flex items-center justify-between cursor-pointer hover:bg-black/5 transition"
          @click="toggleExpanded(result.id)"
        >
          <div class="flex items-center gap-2 flex-1 min-w-0">
            <span class="text-lg flex-shrink-0">
              {{ result.success ? '✅' : '❌' }}
            </span>
            <div class="flex-1 min-w-0">
              <div class="font-mono text-xs font-semibold truncate">
                {{ result.tool_name }}
              </div>
              <div class="text-xs text-gray-500">
                {{ formatTime(result.timestamp) }}
              </div>
            </div>
          </div>
          <button class="text-gray-400 ml-2 flex-shrink-0">
            <span v-if="expandedResults.has(result.id)">▼</span>
            <span v-else>▶</span>
          </button>
        </div>

        <!-- Expanded Details -->
        <div v-if="expandedResults.has(result.id)" class="border-t border-gray-200 bg-white">
          <!-- Success Output -->
          <div v-if="result.output" class="p-3">
            <div class="text-xs font-medium text-gray-700 mb-1">Output:</div>
            <pre class="text-xs bg-gray-50 border border-gray-200 rounded p-2 overflow-x-auto max-h-48 overflow-y-auto">{{ result.output }}</pre>
          </div>

          <!-- Error -->
          <div v-if="result.error" class="p-3 bg-red-50">
            <div class="text-xs font-medium text-red-700 mb-1">Error:</div>
            <pre class="text-xs bg-red-100 border border-red-200 rounded p-2 overflow-x-auto text-red-800">{{ result.error }}</pre>
          </div>

          <!-- Metadata -->
          <div v-if="result.metadata && Object.keys(result.metadata).length > 0" class="p-3 border-t border-gray-100">
            <div class="text-xs font-medium text-gray-700 mb-1">Metadata:</div>
            <div class="text-xs space-y-1">
              <div v-for="(value, key) in result.metadata" :key="key" class="flex gap-2">
                <span class="text-gray-500 font-medium">{{ key }}:</span>
                <span class="text-gray-700">{{ formatMetadataValue(value) }}</span>
              </div>
            </div>
          </div>

          <!-- Citations -->
          <div v-if="result.citations && result.citations.length > 0" class="p-3 border-t border-gray-100">
            <div class="text-xs font-medium text-gray-700 mb-2">Citations:</div>
            <div class="flex flex-wrap gap-1">
              <span
                v-for="(citation, idx) in result.citations"
                :key="idx"
                class="inline-block px-2 py-1 bg-blue-100 text-blue-700 rounded text-xs font-mono cursor-pointer hover:bg-blue-200 transition"
                :title="citation"
              >
                {{ citation }}
              </span>
            </div>
          </div>

          <!-- Trace -->
          <div v-if="result.trace && result.trace.length > 0" class="p-3 border-t border-gray-100">
            <div class="text-xs font-medium text-gray-700 mb-2">Execution Trace:</div>
            <div class="space-y-1">
              <div
                v-for="(step, idx) in result.trace"
                :key="idx"
                class="text-xs bg-gray-50 border border-gray-200 rounded p-2"
              >
                <div class="font-mono text-blue-600">{{ step.tool }}</div>
                <div class="text-gray-500 text-[10px]">{{ formatTime(step.timestamp) }}</div>
              </div>
            </div>
          </div>

          <!-- Execution Time -->
          <div v-if="result.metadata?.execution_time" class="px-3 py-2 bg-gray-50 border-t border-gray-100">
            <div class="text-xs text-gray-600">
              ⏱️ Execution time: <span class="font-medium">{{ result.metadata.execution_time.toFixed(2) }}s</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Empty State (shouldn't show due to v-if on container) -->
    <div v-if="results.length === 0" class="p-6 text-center text-gray-400 text-sm">
      No executions yet
    </div>
  </div>
</template>

<script>
import { ref, watch } from 'vue'

export default {
  name: 'ExecutionResultsPanel',
  props: {
    results: {
      type: Array,
      default: () => []
    }
  },
  emits: ['clear'],
  setup(props) {
    const expandedResults = ref(new Set())

    // Auto-expand the latest result when a new one arrives
    watch(() => props.results.length, (newLength, oldLength) => {
      if (newLength > oldLength && props.results.length > 0) {
        const latestResult = props.results[0]
        expandedResults.value.add(latestResult.id)
      }
    })

    const toggleExpanded = (id) => {
      if (expandedResults.value.has(id)) {
        expandedResults.value.delete(id)
      } else {
        expandedResults.value.add(id)
      }
      // Trigger reactivity
      expandedResults.value = new Set(expandedResults.value)
    }

    const formatTime = (timestamp) => {
      const date = new Date(timestamp)
      const now = new Date()
      const diff = now - date

      if (diff < 60000) {
        return 'Just now'
      } else if (diff < 3600000) {
        const mins = Math.floor(diff / 60000)
        return `${mins}m ago`
      } else if (diff < 86400000) {
        const hours = Math.floor(diff / 3600000)
        return `${hours}h ago`
      } else {
        return date.toLocaleString('en-US', {
          month: 'short',
          day: 'numeric',
          hour: '2-digit',
          minute: '2-digit'
        })
      }
    }

    const formatMetadataValue = (value) => {
      if (typeof value === 'object') {
        return JSON.stringify(value, null, 2)
      }
      return String(value)
    }

    return {
      expandedResults,
      toggleExpanded,
      formatTime,
      formatMetadataValue
    }
  }
}
</script>

<style scoped>
/* Custom scrollbar for results panel */
.execution-results-panel ::-webkit-scrollbar {
  width: 6px;
}

.execution-results-panel ::-webkit-scrollbar-track {
  background: #f1f1f1;
  border-radius: 3px;
}

.execution-results-panel ::-webkit-scrollbar-thumb {
  background: #888;
  border-radius: 3px;
}

.execution-results-panel ::-webkit-scrollbar-thumb:hover {
  background: #555;
}
</style>
