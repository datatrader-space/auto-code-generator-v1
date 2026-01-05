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

  // Repository Documentation
  getRepositoryRequirements: (systemId, repoId) =>
    api.get(`/systems/${systemId}/repositories/${repoId}/requirements/`),

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

  // Services
  discoverServiceActions: (data) => api.post('/services/discover/', data)
}
