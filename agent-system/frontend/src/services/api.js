// src/services/api.js
/**
 * API Service - Centralized Axios configuration
 */

import axios from 'axios'

// Create axios instance
const api = axios.create({
  baseURL: 'http://localhost:8000/api',
  timeout: 30000,
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json'
  }
})
function getCookie(name) {
  let cookieValue = null
  if (document.cookie && document.cookie !== '') {
    const cookies = document.cookie.split(';')
    for (let i = 0; i < cookies.length; i++) {
      const cookie = cookies[i].trim()
      if (cookie.substring(0, name.length + 1) === (name + '=')) {
        cookieValue = decodeURIComponent(cookie.substring(name.length + 1))
        break
      }
    }
  }
  return cookieValue
}
// Request interceptor
api.interceptors.request.use(
  (config) => {
    // Add CSRF token for Django
    const csrfToken = getCookie('csrftoken')
    if (csrfToken) {
      config.headers['X-CSRFToken'] = csrfToken
    }

    // Session-based auth (cookies are sent automatically with withCredentials: true)
    // No need to add Authorization header for session auth

    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// Response interceptor
api.interceptors.response.use(
  (response) => {
    return response
  },
  (error) => {
    // Handle errors globally
    if (error.response) {
      // Server responded with error
      console.error('API Error:', error.response.status, error.response.data)
    } else if (error.request) {
      // Request made but no response
      console.error('Network Error:', error.request)
    } else {
      // Something else happened
      console.error('Error:', error.message)
    }

    return Promise.reject(error)
  }
)

// API methods
export default {
  // Generic methods
  get: (url, config) => api.get(url, config),
  post: (url, data, config) => api.post(url, data, config),
  put: (url, data, config) => api.put(url, data, config),
  patch: (url, data, config) => api.patch(url, data, config),
  delete: (url, config) => api.delete(url, config),

  // Systems
  getSystems: () => api.get('/systems/'),
  getSystem: (id) => api.get(`/systems/${id}/`),
  createSystem: (data) => api.post('/systems/', data),
  updateSystem: (id, data) => api.put(`/systems/${id}/`, data),
  deleteSystem: (id) => api.delete(`/systems/${id}/`),

  // Repositories
  getRepositories: (systemId) => api.get(`/systems/${systemId}/repositories/`),
  getRepository: (systemId, repoId) => api.get(`/systems/${systemId}/repositories/${repoId}/`),
  createRepository: (systemId, data) => api.post(`/systems/${systemId}/repositories/`, data),
  analyzeRepository: (systemId, repoId, force = false) =>
    api.post(`/systems/${systemId}/repositories/${repoId}/analyze/`, { force }),
  getQuestions: (systemId, repoId) =>
    api.get(`/systems/${systemId}/repositories/${repoId}/questions/`),
  submitAnswers: (systemId, repoId, answers) =>
    api.post(`/systems/${systemId}/repositories/${repoId}/submit_answers/`, { answers }),

  // Repository Knowledge
  getKnowledgeSummary: (systemId, repoId) =>
    api.get(`/systems/${systemId}/repositories/${repoId}/knowledge/summary/`),
  getKnowledgeDocs: (systemId, repoId) =>
    api.get(`/systems/${systemId}/repositories/${repoId}/knowledge/docs/`),
  extractKnowledge: (systemId, repoId, force = true) =>
    api.post(`/systems/${systemId}/repositories/${repoId}/knowledge/extract/`, { force }),
  analyzeKnowledgeDoc: (systemId, repoId, kind, specId) =>
    api.post(`/systems/${systemId}/repositories/${repoId}/knowledge/analyze_doc/`, { kind, spec_id: specId }),

  // Repository Documentation
  getRepositoryRequirements: (systemId, repoId) =>
    api.get(`/systems/${systemId}/repositories/${repoId}/requirements/`),

  // Service Management
  getServices: () => api.get('/services/'),
  getService: (id) => api.get(`/services/${id}/`),
  createService: (data) => api.post('/services/create/', data),
  updateService: (id, data) => api.post(`/services/${id}/update/`, data),
  deleteService: (id) => api.delete(`/services/${id}/delete/`),
  createServiceActions: (id, data) => api.post(`/services/${id}/actions/create/`, data),
  discoverServiceActions: (data) => api.post('/services/discover/', data),


  // Repository Files
  getRepositoryFiles: (systemId, repoId) =>
    api.get(`/systems/${systemId}/repositories/${repoId}/files/`),
  getFileContent: (systemId, repoId, filePath) =>
    api.get(`/systems/${systemId}/repositories/${repoId}/files/content/`, {
      params: { path: filePath }
    }),

  // Knowledge
  getKnowledge: (systemId) => api.get(`/systems/${systemId}/knowledge/`),

  // Tasks
  getTasks: (systemId) => api.get(`/systems/${systemId}/tasks/`),
  getTask: (systemId, taskId) => api.get(`/systems/${systemId}/tasks/${taskId}/`),
  createTask: (systemId, data) => api.post(`/systems/${systemId}/tasks/`, data),
  approveTask: (systemId, taskId, notes = '') =>
    api.post(`/systems/${systemId}/tasks/${taskId}/approve/`, { notes }),
  rejectTask: (systemId, taskId, notes = '') =>
    api.post(`/systems/${systemId}/tasks/${taskId}/reject/`, { notes }),

  // LLM
  checkLLMHealth: () => api.get('/llm/health/'),
  getLlmStats: () => api.get('/llm/stats/'),
  getLlmProviders: () => api.get('/llm/providers/'),
  createLlmProvider: (data) => api.post('/llm/providers/', data),
  updateLlmProvider: (id, data) => api.put(`/llm/providers/${id}/`, data),
  deleteLlmProvider: (id) => api.delete(`/llm/providers/${id}/`),
  syncOllamaModels: (id) => api.post(`/llm/providers/${id}/sync_ollama_models/`),
  getLlmModels: (params = {}) => api.get('/llm/models/', { params }),
  createLlmModel: (data) => api.post('/llm/models/', data),
  updateLlmModel: (id, data) => api.put(`/llm/models/${id}/`, data),
  deleteLlmModel: (id) => api.delete(`/llm/models/${id}/`),

  // Authentication
  register: (data) => api.post('/auth/register', data),
  login: (data) => api.post('/auth/login', data),
  logout: () => api.post('/auth/logout'),
  getCurrentUser: () => api.get('/auth/me'),
  checkAuth: () => api.get('/auth/check'),

  // GitHub OAuth
  githubConfig: () => api.get('/auth/github/config'),
  githubLogin: () => api.get('/auth/github/login'),
  githubTestToken: (token = null) => {
    const url = token ? `/auth/github/test?token=${token}` : '/auth/github/test'
    return api.get(url)
  },
  githubListRepos: () => api.get('/auth/github/repos'),
  githubGetRepoInfo: (githubUrl) => api.post('/auth/github/repo-info', { github_url: githubUrl }),

  // CRS outputs
  runCrs: (systemId, repoId) => api.post(`/systems/${systemId}/repositories/${repoId}/crs/run/`),
  getCrsSummary: (systemId, repoId) => api.get(`/systems/${systemId}/repositories/${repoId}/crs/summary/`),
  getCrsBlueprints: (systemId, repoId) => api.get(`/systems/${systemId}/repositories/${repoId}/crs/blueprints/`),
  getCrsArtifacts: (systemId, repoId) => api.get(`/systems/${systemId}/repositories/${repoId}/crs/artifacts/`),
  getCrsRelationships: (systemId, repoId) => api.get(`/systems/${systemId}/repositories/${repoId}/crs/relationships/`),

  // Benchmarks
  getBenchmarkReports: () => api.get('/benchmarks/reports/'),
  getBenchmarkReport: (id) => api.get(`/benchmarks/reports/${id}/`),
  createBenchmarkRun: (data) => api.post('/benchmarks/runs/', data),
  getBenchmarkRun: (id) => api.get(`/benchmarks/runs/${id}/`),
  getBenchmarkReportDownloadUrl: (id, filePath) => {
    const base = api.defaults.baseURL || ''
    const encoded = encodeURIComponent(filePath)
    return `${base}/benchmarks/reports/${id}/download?file=${encoded}`
  },

  // Context Files
  getConversations: (params) => api.get('/conversations/', { params }),
  getConversation: (id) => api.get(`/conversations/${id}/`),
  createConversation: (data) => api.post('/conversations/', data),

  uploadContextFile: (conversationPk, file, agentId = null) => {
    const formData = new FormData()
    formData.append('file', file)
    if (agentId) {
      formData.append('agent_profile_id', agentId)
    }

    // If agentId is provided, we can use a direct endpoint or the same one if generic
    // But since current URL is /conversations/:id/files/, we need a generic one or assume conversationPk is null
    // Let's use the generic viewset if no conversationPk, but our URLs are nested.
    // Actually, I didn't add a generic router for files.
    // I should probably add a generic path or assume conversationPk might be 'agent' placeholder?
    // BETTER: Use a new generic endpoint in api.js?
    // Wait, the backend logic I added to ContextFileViewSet creates a generic endpoint if I register it.
    // Let's assume I need to register strict /context_files/ endpoint in urls.py for this to work clean.
    // For now, let's keep the nested URL for conversation, and use a different strategy or Assume user adds generic route.

    // Changing strategy: I will assume I added `router.register(r'context_files', ...)` or similiar.
    // But I didn't. I only modified the ViewSet code.
    // I need to register the generic route in urls.py first.
    // Let's modify api.js assuming the route exists as /agents/:id/files/ or /context_files/

    // Let's assume /context_files/ for generic access
    let url = `/conversations/${conversationPk}/files/`
    if (agentId && !conversationPk) {
      // Generic endpoint required.
      // Pass.
    }
    return api.post(url, formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    })
  },
  // RE-WRITING properly below
  uploadAgentFile: (agentId, file) => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('agent_profile', agentId);
    // We need a generic endpoint. I will add 'context_files' to router in next step.
    return api.post('/context_files/', formData, { headers: { 'Content-Type': 'multipart/form-data' } });
  },
  uploadConversationFile: (conversationPk, file) => {
    const formData = new FormData();
    formData.append('file', file);
    return api.post(`/conversations/${conversationPk}/files/`, formData, { headers: { 'Content-Type': 'multipart/form-data' } });
  },
  getContextFiles: (conversationPk) => api.get(`/conversations/${conversationPk}/files/`),
  deleteContextFile: (conversationPk, fileId) => api.delete(`/conversations/${conversationPk}/files/${fileId}/`),

  // Agent Chat
  startAgentChat: (agentProfileId, repositoryId = null) => {
    const payload = {};
    if (repositoryId) payload.repository_id = repositoryId;
    return api.post(`/agents/${agentProfileId}/chat/`, payload);
  },

  // New Agent Knowledge
  analyzeContextFile: (fileId) => api.post(`/context_files/${fileId}/analyze/`),
}
