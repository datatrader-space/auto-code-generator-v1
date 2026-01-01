<template>
  <section class="bg-white shadow-sm rounded-lg border border-gray-200 p-6">
    <div class="flex items-center justify-between mb-4">
      <div>
        <h2 class="text-lg font-semibold text-gray-900">Run configuration</h2>
        <p class="text-sm text-gray-500">Pick the target system, models, and agent modes.</p>
      </div>
      <button
        class="inline-flex items-center px-4 py-2 rounded-md text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 disabled:opacity-50"
        :disabled="!canRun || running"
        @click="emit('run')"
      >
        {{ running ? 'Starting…' : 'Run benchmark' }}
      </button>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <div>
        <label class="block text-sm font-medium text-gray-700">System</label>
        <select
          class="mt-1 w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500"
          :value="config.systemId"
          @change="updateField('systemId', $event.target.value)"
        >
          <option value="" disabled>Select a system</option>
          <option v-for="system in systems" :key="system.id" :value="system.id">
            {{ system.name }}
          </option>
        </select>
      </div>

      <div>
        <label class="block text-sm font-medium text-gray-700">Suite size</label>
        <input
          type="number"
          min="1"
          class="mt-1 w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500"
          :value="config.suiteSize"
          @input="updateField('suiteSize', Number($event.target.value))"
        />
      </div>
    </div>

    <div class="mt-6">
      <h3 class="text-sm font-medium text-gray-700 mb-2">Models</h3>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-3 max-h-48 overflow-y-auto pr-2">
        <label
          v-for="model in models"
          :key="model.id"
          class="flex items-center space-x-2 bg-gray-50 border border-gray-200 rounded-md px-3 py-2"
        >
          <input
            type="checkbox"
            class="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
            :checked="config.modelIds.includes(model.id)"
            @change="toggleArray('modelIds', model.id)"
          />
          <div>
            <p class="text-sm font-medium text-gray-900">{{ model.display_name || model.name }}</p>
            <p class="text-xs text-gray-500">
              {{ model.provider_name || model.provider || 'Unknown provider' }}
            </p>
          </div>
        </label>
      </div>
    </div>

    <div class="mt-6 grid grid-cols-1 md:grid-cols-2 gap-6">
      <div>
        <h3 class="text-sm font-medium text-gray-700 mb-2">Agent modes</h3>
        <div class="space-y-2">
          <label v-for="mode in agentModes" :key="mode.value" class="flex items-center space-x-2">
            <input
              type="checkbox"
              class="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
              :checked="config.agentModes.includes(mode.value)"
              @change="toggleArray('agentModes', mode.value)"
            />
            <span class="text-sm text-gray-700">{{ mode.label }}</span>
          </label>
        </div>
      </div>

      <div>
        <h3 class="text-sm font-medium text-gray-700 mb-2">Task types</h3>
        <div class="space-y-2">
          <label v-for="task in taskTypes" :key="task.value" class="flex items-center space-x-2">
            <input
              type="checkbox"
              class="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
              :checked="config.taskTypes.includes(task.value)"
              @change="toggleArray('taskTypes', task.value)"
            />
            <span class="text-sm text-gray-700">{{ task.label }}</span>
          </label>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed } from 'vue'
const props = defineProps({
  systems: {
    type: Array,
    default: () => []
  },
  models: {
    type: Array,
    default: () => []
  },
  config: {
    type: Object,
    required: true
  },
  running: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['update-config', 'run'])

const agentModes = [
  { value: 'crs-only', label: 'CRS-only' },
  { value: 'files-only', label: 'Files-only' },
  { value: 'hybrid', label: 'Hybrid' }
]

const taskTypes = [
  { value: 'read', label: 'Read tasks' },
  { value: 'write', label: 'Write tasks' }
]

const updateField = (field, value) => {
  emit('update-config', { ...props.config, [field]: value })
}

const toggleArray = (field, value) => {
  const next = props.config[field].includes(value)
    ? props.config[field].filter((entry) => entry !== value)
    : [...props.config[field], value]

  emit('update-config', { ...props.config, [field]: next })
}

const canRun = computed(() => {
  return (
    props.config.systemId &&
    props.config.modelIds.length > 0 &&
    props.config.agentModes.length > 0 &&
    props.config.taskTypes.length > 0
  )
})
</script>
