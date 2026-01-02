<template>
  <div>
    <!-- Loading -->
    <div v-if="loading" class="text-center py-12">
      <div class="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      <p class="mt-4 text-gray-600">Loading system...</p>
    </div>
    
    <!-- System Detail -->
    <div v-else-if="system">
      <!-- Header -->
      <div class="mb-8">
        <div class="flex items-center justify-between">
          <div class="flex items-center">
            <button
              @click="$router.push('/')"
              class="mr-4 text-gray-600 hover:text-gray-900"
            >
              ← Back
            </button>
            <div>
              <h1 class="text-3xl font-bold text-gray-900">{{ system.name }}</h1>
              <p class="mt-1 text-gray-600">{{ system.description }}</p>
            </div>
          </div>
          
          <div class="flex items-center gap-3">
            <router-link 
              to="/benchmarks"
              class="px-3 py-1 text-sm font-medium bg-indigo-100 text-indigo-700 rounded-full hover:bg-indigo-200 transition-colors"
            >
              Benchmarks
            </router-link>
            <span
              class="px-3 py-1 text-sm font-medium rounded-full"
              :class="{
                'bg-green-100 text-green-800': system.status === 'ready',
                'bg-yellow-100 text-yellow-800': system.status === 'initializing',
                'bg-red-100 text-red-800': system.status === 'error'
              }"
            >
              {{ system.status }}
            </span>
          </div>
        </div>
      </div>
      
      <!-- Stats -->
      <div class="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
        <div class="bg-white rounded-lg shadow p-6">
          <div class="flex items-center">
            <div class="flex-shrink-0 bg-blue-500 rounded-md p-3">
              <svg class="h-6 w-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
              </svg>
            </div>
            <div class="ml-5">
              <p class="text-2xl font-bold text-gray-900">{{ repositories.length }}</p>
              <p class="text-sm text-gray-500">Repositories</p>
            </div>
          </div>
        </div>
        
        <div class="bg-white rounded-lg shadow p-6">
          <div class="flex items-center">
            <div class="flex-shrink-0 bg-purple-500 rounded-md p-3">
              <svg class="h-6 w-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
            </div>
            <div class="ml-5">
              <p class="text-2xl font-bold text-gray-900">{{ system.knowledge_count }}</p>
              <p class="text-sm text-gray-500">Knowledge Items</p>
            </div>
          </div>
        </div>
        
        <div class="bg-white rounded-lg shadow p-6">
          <div class="flex items-center">
            <div class="flex-shrink-0 bg-green-500 rounded-md p-3">
              <svg class="h-6 w-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
            <div class="ml-5">
              <p class="text-2xl font-bold text-gray-900">{{ readyRepos }}</p>
              <p class="text-sm text-gray-500">Ready Repos</p>
            </div>
          </div>
        </div>
      </div>

      <!-- System Planner Chat -->
      <div class="bg-white rounded-lg shadow mb-8">
        <div class="px-6 py-4 border-b flex items-center justify-between">
          <div>
            <h2 class="text-lg font-semibold text-gray-900 flex items-center">
              <svg class="w-5 h-5 mr-2 text-purple-600" fill="currentColor" viewBox="0 0 20 20">
                <path d="M9 2a1 1 0 000 2h2a1 1 0 100-2H9z" />
                <path fill-rule="evenodd" d="M4 5a2 2 0 012-2 3 3 0 003 3h2a3 3 0 003-3 2 2 0 012 2v11a2 2 0 01-2 2H6a2 2 0 01-2-2V5zm3 4a1 1 0 000 2h.01a1 1 0 100-2H7zm3 0a1 1 0 000 2h3a1 1 0 100-2h-3zm-3 4a1 1 0 100 2h.01a1 1 0 100-2H7zm3 0a1 1 0 100 2h3a1 1 0 100-2h-3z" clip-rule="evenodd" />
              </svg>
              System Planner
            </h2>
            <p class="text-sm text-gray-500 mt-1">
              Plan changes across all repositories with AI assistance
            </p>
          </div>
          <button
            @click="showPlannerChat = !showPlannerChat"
            class="px-4 py-2 rounded-lg text-sm font-medium transition-colors"
            :class="showPlannerChat ? 'bg-gray-200 text-gray-700 hover:bg-gray-300' : 'bg-purple-600 text-white hover:bg-purple-700'"
          >
            {{ showPlannerChat ? 'Hide Chat' : 'Open Planner' }}
          </button>
        </div>

        <div v-if="showPlannerChat" class="p-4">
          <PlannerChat :system-id="parseInt(systemId)" :repository-count="repositories.length" />
        </div>

        <div v-else class="px-6 py-4 bg-purple-50 border-t">
          <div class="flex items-center text-sm text-gray-600">
            <svg class="w-5 h-5 mr-2 text-purple-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
            <span>Chat with an AI planner that has access to all {{ repositories.length }} repositories in this system</span>
          </div>
        </div>
      </div>

      <!-- Intent & Constraints -->
      <div class="bg-white rounded-lg shadow mb-8">
        <div class="px-6 py-4 border-b flex items-center justify-between">
          <div>
            <h2 class="text-lg font-semibold text-gray-900">Intent & Constraints</h2>
            <p class="text-sm text-gray-500">
              Capture your system goals and non-negotiables before analysis.
            </p>
          </div>
          <button
            @click="openIntentModal"
            class="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm"
          >
            {{ hasIntentConstraints ? 'Edit' : 'Add' }} Intent
          </button>
        </div>
        <div class="px-6 py-4">
          <div v-if="hasIntentConstraints" class="space-y-4">
            <div>
              <p class="text-xs uppercase tracking-wide text-gray-400">Intent summary</p>
              <p class="text-gray-800 mt-1">{{ intentSummary }}</p>
            </div>
            <div>
              <p class="text-xs uppercase tracking-wide text-gray-400">Constraints</p>
              <ul class="list-disc list-inside text-gray-800 mt-1 space-y-1">
                <li v-for="constraint in intentConstraints" :key="constraint">
                  {{ constraint }}
                </li>
              </ul>
            </div>
          </div>
          <div v-else class="text-gray-500">
            No intent or constraints yet. Add them to guide repository analysis.
          </div>
        </div>
      </div>
      
      <!-- Repositories Section -->
      <div class="bg-white rounded-lg shadow mb-8">
        <div class="px-6 py-4 border-b flex justify-between items-center">
          <h2 class="text-lg font-semibold text-gray-900">Repositories</h2>
          <button
            @click="showAddRepoModal = true"
            class="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm"
          >
            + Add Repository
          </button>
        </div>
        
        <!-- Repositories List -->
        <div v-if="repositories.length > 0" class="divide-y">
          <div
            v-for="repo in repositories"
            :key="repo.id"
            class="px-6 py-4 hover:bg-gray-50 cursor-pointer"
            @click="selectRepository(repo)"
          >
            <div class="flex items-center justify-between">
              <div class="flex-1">
                <div class="flex items-center">
                  <h3 class="text-base font-medium text-gray-900">{{ repo.name }}</h3>
                  <span
                    class="ml-3 px-2 py-1 text-xs font-medium rounded-full"
                    :class="{
                      'bg-green-100 text-green-800': repo.status === 'ready' || repo.status === 'questions_answered',
                      'bg-yellow-100 text-yellow-800': repo.status === 'analyzing' || repo.status === 'questions_generated',
                      'bg-gray-100 text-gray-800': repo.status === 'pending',
                      'bg-red-100 text-red-800': repo.status === 'error'
                    }"
                  >
                    {{ repo.status }}
                  </span>
                </div>
                <p class="text-sm text-gray-500 mt-1">{{ repo.github_url }}</p>
                <div class="flex items-center mt-2 text-xs text-gray-400">
                  <span v-if="repo.questions_count > 0">
                    {{ repo.questions_answered }}/{{ repo.questions_count }} questions answered
                  </span>
                </div>
              </div>
              
              <div class="ml-4">
                <button
                  v-if="repo.status === 'pending'"
                  @click.stop="analyzeRepo(repo)"
                  class="px-3 py-1 bg-blue-600 text-white rounded text-sm hover:bg-blue-700"
                >
                  Analyze
                </button>
                <button
                  v-else-if="repo.status === 'questions_generated'"
                  @click.stop="answerQuestions(repo)"
                  class="px-3 py-1 bg-green-600 text-white rounded text-sm hover:bg-green-700"
                >
                  Answer Questions
                </button>
                <button
                  v-else-if="repo.status === 'questions_answered'"
                  @click.stop="runCrs(repo)"
                  class="px-3 py-1 bg-purple-600 text-white rounded text-sm hover:bg-purple-700"
                >
                  Run CRS
                </button>
                <button
                  v-else-if="repo.status === 'crs_running'"
                  disabled
                  class="px-3 py-1 bg-gray-200 text-gray-500 rounded text-sm"
                >
                  CRS Running
                </button>
                <button
                  v-else-if="repo.status === 'crs_ready' || repo.status === 'ready' || repo.crs_status === 'ready'"
                  @click.stop="openCrsModal(repo)"
                  class="px-3 py-1 bg-gray-900 text-white rounded text-sm hover:bg-black"
                >
                  View CRS
                </button>
              </div>
            </div>
          </div>
        </div>
        
        <!-- Empty State -->
        <div v-else class="px-6 py-12 text-center">
          <p class="text-gray-500">No repositories yet</p>
          <button
            @click="showAddRepoModal = true"
            class="mt-4 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
          >
            Add Your First Repository
          </button>
        </div>
      </div>
      
      <!-- Repository Detail Panel (Inline) -->
      <div v-if="showRepositoryPanel && selectedRepo" class="mt-8 bg-white rounded-lg shadow">
        <div class="px-6 py-4 border-b flex items-center justify-between bg-gray-50">
          <div>
            <h3 class="text-lg font-semibold text-gray-900">{{ selectedRepo.name }}</h3>
            <p class="text-sm text-gray-500 mt-1">{{ selectedRepo.github_url }}</p>
          </div>
          <button
            @click="closeRepositoryPanel"
            class="text-gray-500 hover:text-gray-700 text-xl font-bold px-3 py-1 rounded hover:bg-gray-200"
          >
            ✕
          </button>
        </div>
        
        <!-- Repository Tabs -->
        <div class="border-b px-6">
          <div class="flex space-x-4 overflow-x-auto">
            <button
              @click="repoTab = 'knowledge'"
              class="px-3 py-3 text-sm font-medium border-b-2 transition-colors whitespace-nowrap"
              :class="repoTab === 'knowledge' ? 'border-blue-600 text-blue-600' : 'border-transparent text-gray-600 hover:text-gray-900'"
            >
              📚 Knowledge
            </button>
            <button
              @click="repoTab = 'docs'"
              class="px-3 py-3 text-sm font-medium border-b-2 transition-colors whitespace-nowrap"
              :class="repoTab === 'docs' ? 'border-blue-600 text-blue-600' : 'border-transparent text-gray-600 hover:text-gray-900'"
            >
              📄 Docs
            </button>
            <button
              @click="repoTab = 'code'"
              class="px-3 py-3 text-sm font-medium border-b-2 transition-colors whitespace-nowrap"
              :class="repoTab === 'code' ? 'border-blue-600 text-blue-600' : 'border-transparent text-gray-600 hover:text-gray-900'"
            >
              💻 Code
            </button>
            <button
              @click="repoTab = 'chat'"
              class="px-3 py-3 text-sm font-medium border-b-2 transition-colors whitespace-nowrap"
              :class="repoTab === 'chat' ? 'border-blue-600 text-blue-600' : 'border-transparent text-gray-600 hover:text-gray-900'"
            >
              💬 Chat
            </button>
            <button
              @click="setCrsTabInline('pipeline')"
              class="px-3 py-3 text-sm font-medium border-b-2 transition-colors whitespace-nowrap"
              :class="repoTab === 'pipeline' ? 'border-blue-600 text-blue-600' : 'border-transparent text-gray-600 hover:text-gray-900'"
            >
              🔄 Pipeline
            </button>
            <button
              @click="setCrsTabInline('trace')"
              class="px-3 py-3 text-sm font-medium border-b-2 transition-colors whitespace-nowrap"
              :class="repoTab === 'trace' ? 'border-blue-600 text-blue-600' : 'border-transparent text-gray-600 hover:text-gray-900'"
            >
              📊 Trace
            </button>
            <button
              @click="setCrsTabInline('summary')"
              class="px-3 py-3 text-sm font-medium border-b-2 transition-colors whitespace-nowrap"
              :class="repoTab === 'summary' ? 'border-blue-600 text-blue-600' : 'border-transparent text-gray-600 hover:text-gray-900'"
            >
              📋 Summary
            </button>
            <button
              @click="setCrsTabInline('blueprints')"
              class="px-3 py-3 text-sm font-medium border-b-2 transition-colors whitespace-nowrap"
              :class="repoTab === 'blueprints' ? 'border-blue-600 text-blue-600' : 'border-transparent text-gray-600 hover:text-gray-900'"
            >
              📐 Blueprints
            </button>
            <button
              @click="setCrsTabInline('artifacts')"
              class="px-3 py-3 text-sm font-medium border-b-2 transition-colors whitespace-nowrap"
              :class="repoTab === 'artifacts' ? 'border-blue-600 text-blue-600' : 'border-transparent text-gray-600 hover:text-gray-900'"
            >
              📦 Artifacts
            </button>
            <button
              @click="setCrsTabInline('relationships')"
              class="px-3 py-3 text-sm font-medium border-b-2 transition-colors whitespace-nowrap"
              :class="repoTab === 'relationships' ? 'border-blue-600 text-blue-600' : 'border-transparent text-gray-600 hover:text-gray-900'"
            >
              🔗 Relationships
            </button>
          </div>
        </div>
        
        <!-- Tab Content -->
        <div>
          <RepositoryKnowledge
            v-if="repoTab === 'knowledge'"
            :repository-id="selectedRepo.id"
            :system-id="systemId"
          />
          <RepositoryDocs
            v-else-if="repoTab === 'docs'"
            :repository="selectedRepo"
          />
          <div v-else-if="repoTab === 'code'" style="height: 600px;">
            <CodeBrowser
              :repository-id="selectedRepo.id"
              :system-id="systemId"
              :artifacts="crsPayloads.artifacts || []"
            />
          </div>
          <div v-else-if="repoTab === 'chat'" class="p-6">
            <RepositoryChat
              :repository="selectedRepo"
              :system-id="systemId"
            />
          </div>
          
          <!-- CRS Pipeline Tab -->
          <div v-else-if="repoTab === 'pipeline'">
            <CRSPipelineDashboard
              :repository-id="selectedRepo.id"
              :system-id="systemId"
            />
          </div>
          
          <!-- Trace Tab -->
          <div v-else-if="repoTab === 'trace'">
            <SessionTrace
              :repository-id="selectedRepo.id"
            />
          </div>
          
          <!-- Summary Tab -->
          <div v-else-if="repoTab === 'summary'" class="p-6">
            <div v-if="crsLoading" class="text-center py-8">
              <div class="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
              <p class="mt-2 text-gray-600">Loading CRS data...</p>
            </div>
            <div v-else-if="crsSummary" class="space-y-3 text-sm text-gray-700">
              <p><strong>Status:</strong> {{ crsSummary.status }}</p>
              <p><strong>CRS Status:</strong> {{ crsSummary.crs_status }}</p>
              <p><strong>Last CRS Run:</strong> {{ crsSummary.last_crs_run || '—' }}</p>
              <p><strong>Blueprint Files:</strong> {{ crsSummary.blueprints_count }}</p>
              <p><strong>Artifacts:</strong> {{ crsSummary.artifact_items }}</p>
              <p><strong>Relationships:</strong> {{ crsSummary.relationship_items }}</p>
            </div>
            <div v-else class="text-gray-500">No CRS summary available.</div>
          </div>
          
          <!-- Blueprints Tab -->
          <div v-else-if="repoTab === 'blueprints'">
            <div v-if="crsLoading" class="text-center py-8">
              <div class="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
              <p class="mt-2 text-gray-600">Loading blueprints...</p>
            </div>
            <BlueprintViewer v-else :blueprints="crsPayloads.blueprints || {}" />
          </div>
          
          <!-- Artifacts Tab -->
          <div v-else-if="repoTab === 'artifacts'">
            <div v-if="crsLoading" class="text-center py-8">
              <div class="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
              <p class="mt-2 text-gray-600">Loading artifacts...</p>
            </div>
            <ArtifactViewer v-else :artifacts="artifactsList" />
          </div>
          
          <!-- Relationships Tab -->
          <div v-else-if="repoTab === 'relationships'">
            <div v-if="crsLoading" class="text-center py-8">
              <div class="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
              <p class="mt-2 text-gray-600">Loading relationships...</p>
            </div>
            <RelationshipViewer v-else :relationships="crsPayloads.relationships || {}" />
          </div>
        </div>
      </div>
      
      <!-- Knowledge Section -->
      <div v-if="system.knowledge_count > 0" class="bg-white rounded-lg shadow">
        <div class="px-6 py-4 border-b">
          <h2 class="text-lg font-semibold text-gray-900">System Knowledge</h2>
        </div>
        <div class="px-6 py-4">
          <button
            @click="loadKnowledge"
            class="text-blue-600 hover:text-blue-700 text-sm"
          >
            View {{ system.knowledge_count }} knowledge items →
          </button>
        </div>
      </div>
    </div>
    
    <!-- Add Repository Modal -->
    <div
      v-if="showAddRepoModal"
      class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50"
      @click.self="closeAddRepoModal"
    >
      <div class="bg-white rounded-lg max-w-3xl w-full p-6 max-h-[90vh] overflow-y-auto">
        <h2 class="text-xl font-bold mb-4">Add Repository</h2>

        <!-- Tabs -->
        <div class="flex border-b mb-4">
          <button
            @click="addRepoTab = 'browse'"
            type="button"
            :class="[
              'px-4 py-2 font-medium',
              addRepoTab === 'browse'
                ? 'text-blue-600 border-b-2 border-blue-600'
                : 'text-gray-500 hover:text-gray-700'
            ]"
          >
            Browse GitHub
          </button>
          <button
            @click="addRepoTab = 'manual'"
            type="button"
            :class="[
              'px-4 py-2 font-medium',
              addRepoTab === 'manual'
                ? 'text-blue-600 border-b-2 border-blue-600'
                : 'text-gray-500 hover:text-gray-700'
            ]"
          >
            Manual Entry
          </button>
        </div>

        <!-- Browse GitHub Tab -->
        <div v-if="addRepoTab === 'browse'">
          <!-- Loading -->
          <div v-if="loadingGithubRepos" class="text-center py-8">
            <div class="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
            <p class="mt-2 text-gray-600">Loading your GitHub repositories...</p>
          </div>

          <!-- Error -->
          <div v-else-if="githubReposError" class="bg-red-50 border border-red-200 rounded-lg p-4 mb-4">
            <p class="text-red-800 font-medium">{{ githubReposError }}</p>
            <p class="text-red-600 text-sm mt-1">Make sure GITHUB_TOKEN is set in .env</p>
            <button
              @click="loadGithubRepos"
              type="button"
              class="mt-2 text-sm text-red-600 hover:text-red-800 underline"
            >
              Try again
            </button>
          </div>

          <!-- Repositories List -->
          <div v-else-if="githubRepos.length > 0">
            <!-- Search -->
            <input
              v-model="repoSearchQuery"
              type="text"
              placeholder="Search repositories..."
              class="w-full px-3 py-2 border rounded-lg mb-4 focus:ring-2 focus:ring-blue-500"
            />

            <!-- Repo Grid -->
            <div class="space-y-2 max-h-96 overflow-y-auto">
              <div
                v-for="repo in filteredGithubRepos"
                :key="repo.full_name"
                @click="selectGithubRepo(repo)"
                class="border rounded-lg p-4 hover:bg-blue-50 hover:border-blue-500 cursor-pointer transition"
              >
                <div class="flex items-start justify-between">
                  <div class="flex-1">
                    <h3 class="font-medium text-gray-900">{{ repo.name }}</h3>
                    <p class="text-sm text-gray-500 mt-1">{{ repo.full_name }}</p>
                    <p v-if="repo.description" class="text-sm text-gray-600 mt-2">
                      {{ repo.description }}
                    </p>
                    <div class="flex items-center gap-4 mt-2">
                      <span v-if="repo.language" class="text-xs text-gray-500">
                        {{ repo.language }}
                      </span>
                      <span class="text-xs text-gray-500">
                        ⭐ {{ repo.stars }}
                      </span>
                      <span
                        v-if="repo.private"
                        class="text-xs bg-yellow-100 text-yellow-800 px-2 py-0.5 rounded"
                      >
                        Private
                      </span>
                    </div>
                  </div>
                  <button
                    type="button"
                    class="ml-4 px-3 py-1 bg-blue-600 text-white text-sm rounded hover:bg-blue-700"
                  >
                    Select
                  </button>
                </div>
              </div>
            </div>

            <p class="text-sm text-gray-500 mt-4">
              Showing {{ filteredGithubRepos.length }} of {{ githubRepos.length }} repositories
            </p>
          </div>
        </div>

        <!-- Manual Entry Tab -->
        <div v-if="addRepoTab === 'manual'">
          <form @submit.prevent="addRepository">
            <div class="mb-4">
              <label class="block text-sm font-medium text-gray-700 mb-2">
                Repository Name *
              </label>
              <input
                v-model="newRepo.name"
                type="text"
                required
                class="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
                placeholder="e.g., worker"
              />
            </div>

            <div class="mb-4">
              <label class="block text-sm font-medium text-gray-700 mb-2">
                GitHub URL *
              </label>
              <input
                v-model="newRepo.github_url"
                type="url"
                required
                class="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
                placeholder="https://github.com/org/repo"
              />
            </div>

            <div class="mb-6">
              <label class="block text-sm font-medium text-gray-700 mb-2">
                Branch
              </label>
              <input
                v-model="newRepo.github_branch"
                type="text"
                class="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
                placeholder="main"
              />
            </div>

            <div class="flex justify-end space-x-3">
              <button
                type="button"
                @click="closeAddRepoModal"
                class="px-4 py-2 text-gray-700 hover:bg-gray-100 rounded-lg"
              >
                Cancel
              </button>
              <button
                type="submit"
                :disabled="adding"
                class="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
              >
                {{ adding ? 'Adding...' : 'Add Repository' }}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
    
    <!-- Questions Modal -->
    <div
      v-if="showQuestionsModal && selectedRepo"
      class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50 overflow-y-auto"
      @click.self="showQuestionsModal = false"
    >
      <div class="bg-white rounded-lg max-w-2xl w-full p-6 my-8">
        <h2 class="text-xl font-bold mb-4">Answer Questions: {{ selectedRepo.name }}</h2>
        
        <div v-if="loadingQuestions" class="text-center py-8">
          <div class="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
        </div>
        
        <form v-else @submit.prevent="submitAnswers" class="space-y-6">
          <div
            v-for="(question, index) in questions"
            :key="question.id"
            class="border-b pb-4"
          >
            <label class="block text-sm font-medium text-gray-900 mb-2">
              {{ index + 1 }}. {{ question.question_text }}
              <span v-if="question.required" class="text-red-500">*</span>
            </label>
            
            <!-- Yes/No -->
            <div v-if="question.question_type === 'yes_no'" class="space-x-4">
              <label class="inline-flex items-center">
                <input
                  v-model="answers[question.question_key]"
                  type="radio"
                  value="yes"
                  class="mr-2"
                />
                Yes
              </label>
              <label class="inline-flex items-center">
                <input
                  v-model="answers[question.question_key]"
                  type="radio"
                  value="no"
                  class="mr-2"
                />
                No
              </label>
            </div>
            
            <!-- Multiple Choice -->
            <select
              v-else-if="question.question_type === 'multiple_choice'"
              v-model="answers[question.question_key]"
              class="w-full px-3 py-2 border rounded-lg"
            >
              <option value="">Select an option...</option>
              <option v-for="opt in question.options" :key="opt" :value="opt">
                {{ opt }}
              </option>
            </select>
            
            <!-- Text -->
            <input
              v-else-if="question.question_type === 'text'"
              v-model="answers[question.question_key]"
              type="text"
              class="w-full px-3 py-2 border rounded-lg"
              placeholder="Your answer..."
            />
            
            <!-- List -->
            <textarea
              v-else-if="question.question_type === 'list'"
              v-model="answers[question.question_key]"
              rows="2"
              class="w-full px-3 py-2 border rounded-lg"
              placeholder="Comma-separated list..."
            ></textarea>
          </div>
          
          <div class="flex justify-end space-x-3 pt-4">
            <button
              type="button"
              @click="showQuestionsModal = false"
              class="px-4 py-2 text-gray-700 hover:bg-gray-100 rounded-lg"
            >
              Cancel
            </button>
            <button
              type="submit"
              :disabled="submitting"
              class="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
            >
              {{ submitting ? 'Submitting...' : 'Submit Answers' }}
            </button>
          </div>
        </form>
      </div>
    </div>

    <!-- CRS Output Modal -->
    <div
      v-if="showCrsModal && selectedCrsRepo"
      class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50 overflow-y-auto"
      @click.self="closeCrsModal"
    >
      <div class="bg-white rounded-lg max-w-4xl w-full p-6 my-8">
        <div class="flex items-center justify-between mb-4">
          <h2 class="text-xl font-bold">CRS Outputs: {{ selectedCrsRepo.name }}</h2>
          <button
            @click="closeCrsModal"
            class="text-gray-500 hover:text-gray-700"
          >
            ✕
          </button>
        </div>

        <div class="flex border-b mb-4">
          <button
            @click="setCrsTab('chat')"
            type="button"
            :class="[
              'px-4 py-2 font-medium',
              crsTab === 'chat'
                ? 'text-blue-600 border-b-2 border-blue-600'
                : 'text-gray-500 hover:text-gray-700'
            ]"
          >
            💬 Chat
          </button>
          <button
            @click="setCrsTab('pipeline')"
            type="button"
            :class="[
              'px-4 py-2 font-medium',
              crsTab === 'pipeline'
                ? 'text-blue-600 border-b-2 border-blue-600'
                : 'text-gray-500 hover:text-gray-700'
            ]"
          >
            Pipeline
          </button>
          <button
            @click="setCrsTab('trace')"
            type="button"
            :class="[
              'px-4 py-2 font-medium',
              crsTab === 'trace'
                ? 'text-blue-600 border-b-2 border-blue-600'
                : 'text-gray-500 hover:text-gray-700'
            ]"
          >
            📊 Trace
          </button>
          <button
            @click="setCrsTab('summary')"
            type="button"
            :class="[
              'px-4 py-2 font-medium',
              crsTab === 'summary'
                ? 'text-blue-600 border-b-2 border-blue-600'
                : 'text-gray-500 hover:text-gray-700'
            ]"
          >
            Summary
          </button>
          <button
            @click="setCrsTab('blueprints')"
            type="button"
            :class="[
              'px-4 py-2 font-medium',
              crsTab === 'blueprints'
                ? 'text-blue-600 border-b-2 border-blue-600'
                : 'text-gray-500 hover:text-gray-700'
            ]"
          >
            Blueprints
          </button>
          <button
            @click="setCrsTab('artifacts')"
            type="button"
            :class="[
              'px-4 py-2 font-medium',
              crsTab === 'artifacts'
                ? 'text-blue-600 border-b-2 border-blue-600'
                : 'text-gray-500 hover:text-gray-700'
            ]"
          >
            Artifacts
          </button>
          <button
            @click="setCrsTab('relationships')"
            type="button"
            :class="[
              'px-4 py-2 font-medium',
              crsTab === 'relationships'
                ? 'text-blue-600 border-b-2 border-blue-600'
                : 'text-gray-500 hover:text-gray-700'
            ]"
          >
            Relationships
          </button>
        </div>

        <!-- Chat Tab -->
        <div v-if="crsTab === 'chat'">
          <RepositoryChat
            :repository="selectedCrsRepo"
            :system-id="systemId"
          />
        </div>

        <!-- Pipeline Dashboard -->
        <div v-else-if="crsTab === 'pipeline'">
          <CRSPipelineDashboard
            :repository-id="selectedCrsRepo.id"
            :system-id="systemId"
          />
        </div>

        <!-- Trace Tab -->
        <div v-else-if="crsTab === 'trace'">
          <SessionTrace
            :repository-id="selectedCrsRepo.id"
          />
        </div>

        <!-- Summary Tab -->
        <div v-else-if="crsLoading" class="text-center py-8">
          <div class="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
          <p class="mt-2 text-gray-600">Loading CRS data...</p>
        </div>

        <div v-else>
          <div v-if="crsTab === 'summary'">
            <div v-if="crsSummary" class="space-y-3 text-sm text-gray-700">
              <p><strong>Status:</strong> {{ crsSummary.status }}</p>
              <p><strong>CRS Status:</strong> {{ crsSummary.crs_status }}</p>
              <p><strong>Last CRS Run:</strong> {{ crsSummary.last_crs_run || '—' }}</p>
              <p><strong>Blueprint Files:</strong> {{ crsSummary.blueprints_count }}</p>
              <p><strong>Artifacts:</strong> {{ crsSummary.artifact_items }}</p>
              <p><strong>Relationships:</strong> {{ crsSummary.relationship_items }}</p>
            </div>
            <div v-else class="text-gray-500">No CRS summary available.</div>
          </div>

          <!-- Blueprints Tab with Interactive Viewer -->
          <div v-else-if="crsTab === 'blueprints'">
            <BlueprintViewer :blueprints="crsPayloads.blueprints || {}" />
          </div>

          <!-- Artifacts Tab with Card Viewer -->
          <div v-else-if="crsTab === 'artifacts'">
            <ArtifactViewer :artifacts="artifactsList" />
          </div>

          <!-- Relationships Tab with Interactive Viewer -->
          <div v-else-if="crsTab === 'relationships'">
            <RelationshipViewer :relationships="crsPayloads.relationships || {}" />
          </div>
        </div>
      </div>
    </div>

    <!-- Intent & Constraints Modal -->
    <div
      v-if="showIntentModal"
      class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50"
      @click.self="showIntentModal = false"
    >
      <div class="bg-white rounded-lg max-w-lg w-full p-6">
        <h2 class="text-xl font-bold mb-4">Intent & Constraints</h2>

        <form @submit.prevent="saveIntentConstraints">
          <div class="mb-4">
            <label class="block text-sm font-medium text-gray-700 mb-2">
              Intent summary
            </label>
            <textarea
              v-model="intentForm.summary"
              rows="3"
              class="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
              placeholder="Describe the primary goal for this system..."
            ></textarea>
          </div>

          <div class="mb-6">
            <label class="block text-sm font-medium text-gray-700 mb-2">
              Constraints (one per line)
            </label>
            <textarea
              v-model="intentForm.constraints"
              rows="4"
              class="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
              placeholder="e.g.\nMust remain HIPAA compliant\nOnly use existing Kafka topics"
            ></textarea>
          </div>

          <div class="flex justify-end space-x-3">
            <button
              type="button"
              @click="showIntentModal = false"
              class="px-4 py-2 text-gray-700 hover:bg-gray-100 rounded-lg"
            >
              Cancel
            </button>
            <button
              type="submit"
              :disabled="savingIntent"
              class="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
            >
              {{ savingIntent ? 'Saving...' : 'Save Intent' }}
            </button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, inject, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '../services/api'
import CRSPipelineDashboard from '../components/CRSPipelineDashboard.vue'
import RepositoryChat from '../components/RepositoryChat.vue'
import PlannerChat from '../components/PlannerChat.vue'
import ArtifactViewer from '../components/ArtifactViewer.vue'
import BlueprintViewer from '../components/BlueprintViewer.vue'
import RelationshipViewer from '../components/RelationshipViewer.vue'
import SessionTrace from '../components/SessionTrace.vue'
import RepositoryKnowledge from '../components/RepositoryKnowledge.vue'
import RepositoryDocs from '../components/RepositoryDocs.vue'
import CodeBrowser from '../components/CodeBrowser.vue'

const route = useRoute()
const router = useRouter()
const notify = inject('notify')

const systemId = parseInt(route.params.id)
const system = ref(null)
const repositories = ref([])
const loading = ref(true)
const showAddRepoModal = ref(false)
const showQuestionsModal = ref(false)
const showIntentModal = ref(false)
const showCrsModal = ref(false)
const showPlannerChat = ref(false)
const showRepositoryPanel = ref(false)
const repoTab = ref('knowledge')
const adding = ref(false)
const loadingQuestions = ref(false)
const submitting = ref(false)
const savingIntent = ref(false)
const crsLoading = ref(false)
const crsSummary = ref(null)
const crsTab = ref('summary')
const selectedCrsRepo = ref(null)
const crsPayloads = ref({
  blueprints: null,
  artifacts: null,
  relationships: null
})

const newRepo = ref({
  name: '',
  github_url: '',
  github_branch: 'main'
})

const selectedRepo = ref(null)
const questions = ref([])
const answers = ref({})
const intentForm = ref({
  summary: '',
  constraints: ''
})

// GitHub browsing
const addRepoTab = ref('browse')
const githubRepos = ref([])
const loadingGithubRepos = ref(false)
const githubReposError = ref(null)
const repoSearchQuery = ref('')

// Computed
const readyRepos = computed(() => {
  return repositories.value.filter(r =>
    r.status === 'ready' || r.status === 'questions_answered'
  ).length
})

const hasIntentConstraints = computed(() => {
  const intent = system.value?.intent_constraints
  return Boolean(intent?.summary || (intent?.constraints || []).length)
})

const intentSummary = computed(() => {
  return system.value?.intent_constraints?.summary || '—'
})

const intentConstraints = computed(() => {
  return system.value?.intent_constraints?.constraints || []
})

const formattedCrsPayload = computed(() => {
  const payload = crsPayloads.value[crsTab.value]
  if (!payload) return 'No data loaded.'
  return JSON.stringify(payload, null, 2)
})

const artifactsList = computed(() => {
  const artifactsData = crsPayloads.value.artifacts
  if (!artifactsData) return []

  // Convert artifacts object to array
  if (Array.isArray(artifactsData)) {
    return artifactsData
  }

  // If it's an object with artifact entries
  if (typeof artifactsData === 'object') {
    return Object.entries(artifactsData).map(([name, data]) => ({
      name,
      ...data
    }))
  }

  return []
})

const filteredGithubRepos = computed(() => {
  if (!repoSearchQuery.value) return githubRepos.value

  const query = repoSearchQuery.value.toLowerCase()
  return githubRepos.value.filter(repo =>
    repo.name.toLowerCase().includes(query) ||
    repo.full_name.toLowerCase().includes(query) ||
    (repo.description && repo.description.toLowerCase().includes(query))
  )
})

// Load system
const loadSystem = async () => {
  try {
    loading.value = true
    const response = await api.getSystem(systemId)
    system.value = response.data
    repositories.value = response.data.repositories || []
  } catch (error) {
    notify('Failed to load system', 'error')
    console.error(error)
  } finally {
    loading.value = false
  }
}

// Add repository
const addRepository = async () => {
  try {
    adding.value = true
    await api.createRepository(systemId, newRepo.value)
    
    notify('Repository added!', 'success')
    showAddRepoModal.value = false
    newRepo.value = { name: '', github_url: '', github_branch: 'main' }
    
    await loadSystem()
  } catch (error) {
    notify('Failed to add repository', 'error')
    console.error(error)
  } finally {
    adding.value = false
  }
}

// Navigate to repository detail page
const selectRepository = (repo) => {
  console.log('Selecting repo:', repo)
  console.log('System ID:', systemId)
  if (!repo || !repo.id) {
    console.error('Repository ID is missing!', repo)
    notify('Error: Repository ID is missing', 'error')
    return
  }
  // Navigate to dedicated repository page
  router.push(`/systems/${systemId}/repositories/${repo.id}`)
}

// Analyze repository
const analyzeRepo = async (repo) => {
  try {
    notify('Analyzing repository...', 'info')
    await api.analyzeRepository(systemId, repo.id)
    notify('Analysis complete!', 'success')
    await loadSystem()
  } catch (error) {
    notify('Analysis failed', 'error')
    console.error(error)
  }
}

// Answer questions
const answerQuestions = async (repo) => {
  try {
    selectedRepo.value = repo
    loadingQuestions.value = true
    showQuestionsModal.value = true
    
    const response = await api.getQuestions(systemId, repo.id)
    questions.value = response.data.questions
    answers.value = {}
  } catch (error) {
    notify('Failed to load questions', 'error')
    console.error(error)
  } finally {
    loadingQuestions.value = false
  }
}

// Submit answers
const submitAnswers = async () => {
  try {
    submitting.value = true
    await api.submitAnswers(systemId, selectedRepo.value.id, answers.value)
    
    notify('Answers submitted successfully!', 'success')
    showQuestionsModal.value = false
    await loadSystem()
  } catch (error) {
    notify('Failed to submit answers', 'error')
    console.error(error)
  } finally {
    submitting.value = false
  }
}

const runCrs = async (repo) => {
  try {
    notify('Running CRS pipeline...', 'info')
    await api.runCrs(systemId, repo.id)
    notify('CRS pipeline complete!', 'success')
    await loadSystem()
  } catch (error) {
    notify('Failed to run CRS pipeline', 'error')
    console.error(error)
  }
}

const openCrsModal = async (repo) => {
  selectedCrsRepo.value = repo
  showCrsModal.value = true
  crsTab.value = 'chat'  // Default to chat tab
  await loadCrsSummary(repo)
}

const closeCrsModal = () => {
  showCrsModal.value = false
  selectedCrsRepo.value = null
  crsTab.value = 'summary'
  crsSummary.value = null
  crsPayloads.value = { blueprints: null, artifacts: null, relationships: null }
}

const setCrsTab = async (tab) => {
  crsTab.value = tab
  if (tab === 'summary') {
    return
  }
  await loadCrsPayload(tab)
}

const loadCrsSummary = async (repo) => {
  try {
    crsLoading.value = true
    const response = await api.getCrsSummary(systemId, repo.id)
    crsSummary.value = response.data
  } catch (error) {
    console.error('Failed to load CRS summary:', error)
    notify('Failed to load CRS summary', 'error')
  } finally {
    crsLoading.value = false
  }
}

const loadCrsPayload = async (payloadType) => {
  if (!selectedCrsRepo.value || crsPayloads.value[payloadType]) {
    return
  }
  try {
    crsLoading.value = true
    let response
    if (payloadType === 'blueprints') {
      response = await api.getCrsBlueprints(systemId, selectedCrsRepo.value.id)
    } else if (payloadType === 'artifacts') {
      response = await api.getCrsArtifacts(systemId, selectedCrsRepo.value.id)
    } else {
      response = await api.getCrsRelationships(systemId, selectedCrsRepo.value.id)
    }
    crsPayloads.value[payloadType] = response.data
  } catch (error) {
    console.error(`Failed to load CRS ${payloadType}:`, error)
    notify(`Failed to load CRS ${payloadType}`, 'error')
  } finally {
    crsLoading.value = false
  }
}

const openIntentModal = () => {
  const intent = system.value?.intent_constraints || {}
  intentForm.value = {
    summary: intent.summary || '',
    constraints: (intent.constraints || []).join('\n')
  }
  showIntentModal.value = true
}

const saveIntentConstraints = async () => {
  try {
    savingIntent.value = true
    const constraintsList = intentForm.value.constraints
      .split('\n')
      .map(item => item.trim())
      .filter(Boolean)
    const payload = {
      name: system.value.name,
      description: system.value.description,
      status: system.value.status,
      intent_constraints: {
        summary: intentForm.value.summary.trim(),
        constraints: constraintsList
      }
    }
    const response = await api.updateSystem(systemId, payload)
    system.value = response.data
    showIntentModal.value = false
    notify('Intent & constraints saved!', 'success')
  } catch (error) {
    notify('Failed to save intent & constraints', 'error')
    console.error(error)
  } finally {
    savingIntent.value = false
  }
}

const closeRepositoryPanel = () => {
  showRepositoryPanel.value = false
  selectedRepo.value = null
  repoTab.value = 'knowledge'
  crsSummary.value = null
  crsPayloads.value = { blueprints: null, artifacts: null, relationships: null }
}

const setCrsTabInline = async (tab) => {
  repoTab.value = tab
  if (tab === 'summary') {
    return
  }
  await loadCrsPayload(tab)
}

const loadCrsSummaryForRepo = async (repo) => {
  try {
    crsLoading.value = true
    const response = await api.getCrsSummary(systemId, repo.id)
    crsSummary.value = response.data
  } catch (error) {
    console.error('Failed to load CRS summary:', error)
  } finally {
    crsLoading.value = false
  }
}

// Load knowledge
const loadKnowledge = async () => {
  notify('Knowledge viewer coming soon!', 'info')
}

// GitHub repository browsing
const loadGithubRepos = async () => {
  try {
    loadingGithubRepos.value = true
    githubReposError.value = null

    const response = await api.githubListRepos()

    if (response.data.success) {
      githubRepos.value = response.data.repositories
      notify(`Loaded ${response.data.count} repositories`, 'success')
    } else {
      githubReposError.value = response.data.error || 'Failed to load repositories'
    }
  } catch (error) {
    console.error('Failed to load GitHub repos:', error)
    githubReposError.value = error.response?.data?.error || 'Failed to load repositories. Check your GitHub token.'
  } finally {
    loadingGithubRepos.value = false
  }
}

const selectGithubRepo = async (repo) => {
  // Auto-fill the form with selected repo
  newRepo.value = {
    name: repo.name,
    github_url: repo.clone_url,
    github_branch: repo.default_branch || 'main'
  }

  // Switch to manual tab to show the filled form
  addRepoTab.value = 'manual'
  notify(`Selected: ${repo.full_name}`, 'success')
}

const closeAddRepoModal = () => {
  showAddRepoModal.value = false
  addRepoTab.value = 'browse'
  repoSearchQuery.value = ''
  githubReposError.value = null
}

// Watch for modal opening to load GitHub repos
watch(showAddRepoModal, (newVal) => {
  if (newVal && addRepoTab.value === 'browse' && githubRepos.value.length === 0) {
    loadGithubRepos()
  }
})

// Load on mount
onMounted(() => {
  loadSystem()
})
</script>
