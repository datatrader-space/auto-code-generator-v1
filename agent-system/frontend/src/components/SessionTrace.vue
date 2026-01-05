<template>
  <div class="session-trace-viewer">
    <div class="header">
      <h2>Agent Session Traces</h2>
      <div class="filters">
        <select v-model="filterType" @change="loadSessions" class="filter-select">
          <option value="">All Types</option>
          <option value="chat">Chat</option>
          <option value="task">Task</option>
          <option value="hybrid">Hybrid</option>
        </select>
        <select v-model="filterStatus" @change="loadSessions" class="filter-select">
          <option value="">All Status</option>
          <option value="success">Success</option>
          <option value="failed">Failed</option>
          <option value="running">Running</option>
        </select>
        <button @click="loadSessions" class="refresh-btn">🔄 Refresh</button>
      </div>
    </div>

    <div v-if="loading" class="loading">Loading sessions...</div>

    <div v-else-if="sessions.length === 0" class="empty-state">
      No sessions found. Send a message to create a session trace.
    </div>

    <div v-else class="sessions-list">
      <div 
        v-for="session in sessions" 
        :key="session.id" 
        class="session-card"
        @click="viewDetails(session)"
      >
        <div class="session-header">
          <span class="session-type" :class="session.session_type">
            {{ session.session_type.toUpperCase() }}
          </span>
          <span class="session-status" :class="session.status">
            {{ session.status }}
          </span>
          <span class="session-time">{{ formatTime(session.created_at) }}</span>
        </div>

        <p class="user-request">{{ session.user_request }}</p>

        <div class="session-meta">
          <span class="meta-item">⏱️ {{ session.duration_ms || 0 }}ms</span>
          <span class="meta-item">🔧 {{ session.step_count || 0 }} steps</span>
          <span class="meta-item">📦 {{ session.repository_name }}</span>
        </div>
      </div>
    </div>

    <!-- Detail Modal -->
    <div v-if="selectedSession" class="modal-overlay" @click="closeDetails">
      <div class="modal-content" @click.stop>
        <div class="modal-header">
          <h3>Session Details</h3>
          <button @click="closeDetails" class="close-btn">✕</button>
        </div>

        <div class="session-details">
          <div class="detail-section">
            <h4>Session Info</h4>
            <div class="detail-grid">
              <div><strong>ID:</strong> {{ selectedSession.session_id }}</div>
              <div><strong>Type:</strong> {{ selectedSession.session_type }}</div>
              <div><strong>Status:</strong> {{ selectedSession.status }}</div>
              <div><strong>Duration:</strong> {{ selectedSession.duration_ms }}ms</div>
              <div><strong>Intent:</strong> {{ selectedSession.intent_classified_as || 'N/A' }}</div>
              <div v-if="selectedSession.conversation_title"><strong>Conversation:</strong> {{ selectedSession.conversation_title }}</div>
              <div v-if="selectedSession.llm_model_name"><strong>LLM Model:</strong> {{ selectedSession.llm_model_name }}</div>
              <div><strong>Created:</strong> {{ formatDateTime(selectedSession.created_at) }}</div>
              <div v-if="selectedSession.completed_at"><strong>Completed:</strong> {{ formatDateTime(selectedSession.completed_at) }}</div>
            </div>
          </div>

          <div class="detail-section">
            <h4>Request</h4>
            <p class="request-text">{{ selectedSession.user_request }}</p>
          </div>
          
          <div v-if="selectedSession.plan" class="detail-section">
            <h4>Execution Plan</h4>
            <pre class="plan-text">{{ JSON.stringify(selectedSession.plan, null, 2) }}</pre>
          </div>

          <div v-if="selectedSession.steps && selectedSession.steps.length" class="detail-section">
            <h4>Execution Steps ({{ selectedSession.steps.length }})</h4>
            <div v-for="(step, idx) in selectedSession.steps" :key="idx" class="step-item">
              <span class="step-number">{{ idx + 1 }}</span>
              <span class="step-action">{{ step.action }}</span>
              <span class="step-status" :class="step.status">{{ step.status }}</span>
              <span class="step-duration">{{ step.duration_ms }}ms</span>
            </div>
          </div>
          
          <div v-if="selectedSession.final_answer" class="detail-section">
            <h4>Final Answer</h4>
            <div class="final-answer-text">{{ selectedSession.final_answer }}</div>
          </div>

          <div v-if="selectedSession.tools_called && selectedSession.tools_called.length" class="detail-section">
            <h4>Tools Called ({{ selectedSession.tools_called.length }})</h4>
            <div class="tools-list">
              <span v-for="tool in selectedSession.tools_called" :key="tool" class="tool-badge">
                {{ tool }}
              </span>
            </div>
          </div>

          <div v-if="selectedSession.artifacts_used && selectedSession.artifacts_used.length" class="detail-section">
            <h4>Artifacts Used ({{ selectedSession.artifacts_used.length }})</h4>
            <div class="artifacts-list">
              <code v-for="artifact in selectedSession.artifacts_used" :key="artifact" class="artifact-item">
                {{ artifact }}
              </code>
            </div>
          </div>
          
          <div v-if="selectedSession.knowledge_context && Object.keys(selectedSession.knowledge_context).length" class="detail-section">
            <h4>Knowledge Context</h4>
            <pre class="context-text">{{ JSON.stringify(selectedSession.knowledge_context, null, 2) }}</pre>
          </div>

          <div v-if="selectedSession.error_message" class="detail-section error-section">
            <h4>Error</h4>
            <pre class="error-message">{{ selectedSession.error_message }}</pre>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import axios from 'axios'

const props = defineProps({
  repositoryId: {
    type: Number,
    default: null
  },
  sessionId: {
    type: String,
    default: null
  }
})

const sessions = ref([])
const selectedSession = ref(null)
const loading = ref(false)
const filterType = ref('')
const filterStatus = ref('')

const loadSessions = async () => {
  loading.value = true
  try {
    const params = {}
    if (props.repositoryId) params.repository = props.repositoryId
    // If sessionId is provided, use it to filter
    if (props.sessionId) params.session_id = props.sessionId
    
    if (filterType.value) params.session_type = filterType.value
    if (filterStatus.value) params.status = filterStatus.value

    const response = await axios.get('/api/sessions/', { params })
    sessions.value = response.data.results || response.data
    
    // Auto-select if only one session found and it matches requested ID
    if (props.sessionId && sessions.value.length === 1) {
        viewDetails(sessions.value[0]);
    }
  } catch (error) {
    console.error('Failed to load sessions:', error)
  } finally {
    loading.value = false
  }
}

const viewDetails = async (session) => {
  try {
    // If session object is sparse, fetch details
    const response = await axios.get(`/api/sessions/${session.id}/`)
    console.log('📊 Session detail response:', response.data)
    selectedSession.value = response.data
  } catch (error) {
    console.error('Failed to load session details:', error)
  }
}

const closeDetails = () => {
  selectedSession.value = null
}

const formatTime = (timestamp) => {
  const date = new Date(timestamp)
  const now = new Date()
  const diff = now - date
  
  if (diff < 60000) return 'Just now'
  if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`
  return date.toLocaleDateString()
}

const formatDateTime = (timestamp) => {
  if (!timestamp) return 'N/A'
  const date = new Date(timestamp)
  return date.toLocaleString()
}

onMounted(loadSessions)

watch(() => props.sessionId, () => {
    loadSessions();
});

// Auto-refresh every 10 seconds
setInterval(loadSessions, 10000)
</script>

<style scoped>
.session-trace-viewer {
  padding: 20px;
  max-width: 1200px;
  margin: 0 auto;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.header h2 {
  margin: 0;
  color: #2c3e50;
}

.filters {
  display: flex;
  gap: 10px;
}

.filter-select {
  padding: 8px 12px;
  border: 1px solid #ddd;
  border-radius: 4px;
  background: white;
  cursor: pointer;
}

.refresh-btn {
  padding: 8px 16px;
  background: #3498db;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
}

.refresh-btn:hover {
  background: #2980b9;
}

.loading, .empty-state {
  text-align: center;
  padding: 40px;
  color: #7f8c8d;
}

.sessions-list {
  display: grid;
  gap: 16px;
}

.session-card {
  background: white;
  border: 1px solid #e1e8ed;
  border-radius: 8px;
  padding: 16px;
  cursor: pointer;
  transition: all 0.2s;
}

.session-card:hover {
  border-color: #3498db;
  box-shadow: 0 2px 8px rgba(52, 152, 219, 0.1);
}

.session-header {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-bottom: 12px;
}

.session-type {
  padding: 4px 12px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
}

.session-type.chat {
  background: #e3f2fd;
  color: #1976d2;
}

.session-type.task {
  background: #f3e5f5;
  color: #7b1fa2;
}

.session-type.hybrid {
  background: #fff3e0;
  color: #f57c00;
}

.session-status {
  padding: 4px 12px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 600;
}

.session-status.success {
  background: #e8f5e9;
  color: #2e7d32;
}

.session-status.failed {
  background: #ffebee;
  color: #c62828;
}

.session-status.running {
  background: #fff9c4;
  color: #f57f17;
}

.session-time {
  margin-left: auto;
  font-size: 12px;
  color: #95a5a6;
}

.user-request {
  margin: 0 0 12px 0;
  color: #2c3e50;
  font-size: 14px;
}

.session-meta {
  display: flex;
  gap: 16px;
  font-size: 12px;
  color: #7f8c8d;
}

.meta-item {
  display: flex;
  align-items: center;
  gap: 4px;
}

/* Modal Styles */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-content {
  background: white;
  border-radius: 12px;
  width: 90%;
  max-width: 800px;
  max-height: 90vh;
  overflow-y: auto;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px;
  border-bottom: 1px solid #e1e8ed;
}

.modal-header h3 {
  margin: 0;
  color: #2c3e50;
}

.close-btn {
  background: none;
  border: none;
  font-size: 24px;
  cursor: pointer;
  color: #95a5a6;
  padding: 0;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
}

.close-btn:hover {
  background: #f5f5f5;
  color: #2c3e50;
}

.session-details {
  padding: 20px;
}

.detail-section {
  margin-bottom: 24px;
}

.detail-section h4 {
  margin: 0 0 12px 0;
  color: #2c3e50;
  font-size: 14px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 12px;
  font-size: 14px;
}

.request-text {
  background: #f8f9fa;
  padding: 12px;
  border-radius: 6px;
  margin: 0;
  font-size: 14px;
  line-height: 1.6;
}

.step-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 12px;
  background: #f8f9fa;
  border-radius: 6px;
  margin-bottom: 8px;
  font-size: 13px;
}

.step-number {
  background: #3498db;
  color: white;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 600;
}

.step-action {
  flex: 1;
  font-weight: 500;
}

.step-duration {
  color: #7f8c8d;
  font-size: 12px;
}

.tools-list, .artifacts-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.tool-badge {
  background: #e3f2fd;
  color: #1976d2;
  padding: 6px 12px;
  border-radius: 16px;
  font-size: 12px;
  font-weight: 600;
}

.artifact-item {
  display: block;
  background: #f5f5f5;
  padding: 8px 12px;
  border-radius: 4px;
  font-size: 12px;
  margin-bottom: 4px;
  word-break: break-all;
}

.error-section {
  background: #ffebee;
  padding: 16px;
  border-radius: 8px;
}

.error-message {
  margin: 0;
  color: #c62828;
  font-size: 13px;
  white-space: pre-wrap;
  word-break: break-word;
}

.plan-text, .context-text {
  margin: 0;
  background: #f5f5f5;
  padding: 12px;
  border-radius: 4px;
  font-size: 12px;
  overflow-x: auto;
  max-height: 400px;
  overflow-y: auto;
}

.final-answer-text {
  background: #e8f5e9;
  padding: 12px;
  border-radius: 6px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
