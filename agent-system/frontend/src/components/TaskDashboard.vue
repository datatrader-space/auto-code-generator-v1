<template>
  <div class="task-dashboard p-6 bg-white rounded-xl shadow-sm border border-gray-100">
    <!-- Header: Active Task -->
    <div class="flex items-start justify-between mb-6">
      <div>
        <h2 class="text-2xl font-bold text-gray-800 tracking-tight">
          Refactor Authentication Flow
        </h2>
        <div class="flex items-center gap-3 mt-2">
          <span class="px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
            In Progress
          </span>
          <span class="text-sm text-gray-500">Started 2h ago</span>
        </div>
      </div>
      <div class="text-right">
        <div class="text-3xl font-bold text-blue-600">65%</div>
        <div class="text-xs text-gray-500 font-medium uppercase tracking-wide">Completion</div>
      </div>
    </div>

    <!-- Progress Bar -->
    <div class="w-full bg-gray-100 rounded-full h-2 mb-8">
      <div class="bg-blue-600 h-2 rounded-full transition-all duration-500 ease-out" style="width: 65%"></div>
    </div>

    <!-- Active Step -->
    <div class="mb-8">
      <h3 class="text-sm font-semibold text-gray-500 uppercase tracking-widest mb-3">
        Current Activity
      </h3>
      <div class="bg-blue-50 border border-blue-100 rounded-lg p-4 flex items-center gap-4">
        <div class="w-8 h-8 rounded-full bg-blue-100 flex items-center justify-center flex-shrink-0">
          <svg class="w-4 h-4 text-blue-600 animate-pulse" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        </div>
        <div>
          <p class="font-medium text-blue-900">Implementing OAuth2 Callback Handler</p>
          <p class="text-sm text-blue-600 mt-0.5">Updating auth/views.py</p>
        </div>
      </div>
    </div>

    <!-- Subtasks / Plan -->
    <div>
      <h3 class="text-sm font-semibold text-gray-500 uppercase tracking-widest mb-3">
        Implementation Plan
      </h3>
      <div class="space-y-3">
        <!-- Completed Item -->
        <div class="flex items-start gap-3 opacity-60">
          <div class="mt-1 w-5 h-5 rounded border border-gray-300 bg-gray-50 flex items-center justify-center">
            <svg class="w-3 h-3 text-gray-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
            </svg>
          </div>
          <span class="text-gray-600 line-through decoration-gray-400">Design database schema for user tokens</span>
        </div>

        <!-- Completed Item -->
        <div class="flex items-start gap-3 opacity-60">
          <div class="mt-1 w-5 h-5 rounded border border-gray-300 bg-gray-50 flex items-center justify-center">
            <svg class="w-3 h-3 text-gray-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
            </svg>
          </div>
          <span class="text-gray-600 line-through decoration-gray-400">Create migration files</span>
        </div>

        <!-- Current Item -->
        <div class="flex items-start gap-3">
          <div class="mt-1 w-5 h-5 rounded border-2 border-blue-500 bg-white shadow-sm flex items-center justify-center">
            <div class="w-2.5 h-2.5 rounded-sm bg-blue-500"></div>
          </div>
          <span class="font-medium text-gray-900">Implement OAuth2 Callback Handler</span>
        </div>

        <!-- Pending Item -->
        <div class="flex items-start gap-3">
          <div class="mt-1 w-5 h-5 rounded border border-gray-300 bg-white"></div>
          <span class="text-gray-600">Update frontend login form</span>
        </div>
        
        <!-- Pending Item -->
        <div class="flex items-start gap-3">
          <div class="mt-1 w-5 h-5 rounded border border-gray-300 bg-white"></div>
          <span class="text-gray-600">Verify token refresh logic</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
// Placeholder - in real implementation this would accept Task props
</script>

<style scoped>
/* Add any specific overrides here if needed */
</style>
