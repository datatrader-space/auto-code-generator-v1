<template>
  <div class="repository-knowledge">
    <div class="knowledge-header">
      <h3>📚 Repository Knowledge</h3>
      <div class="knowledge-actions">
        <button
          @click="extractKnowledge"
          :disabled="isExtracting"
          class="btn btn-primary">
          <span v-if="isExtracting">⏳ Extracting...</span>
          <span v-else>{{ knowledge.status === 'ready' ? '🔄 Refresh Knowledge' : '✨ Extract Knowledge' }}</span>
        </button>
      </div>
    </div>

    <!-- Status Banner -->
    <div v-if="knowledge.status" class="status-banner" :class="`status-${knowledge.status}`">
      <div class="status-info">
        <strong>Status:</strong> {{ formatStatus(knowledge.status) }}
        <span v-if="knowledge.last_extracted" class="status-timestamp">
          • Last extracted: {{ formatDate(knowledge.last_extracted) }}
        </span>
      </div>
      <div v-if="knowledge.docs_count > 0" class="status-stats">
        {{ knowledge.docs_count }} knowledge documents
      </div>
    </div>

    <!-- Extraction Progress -->
    <div v-if="isExtracting" class="extraction-progress">
      <div class="progress-header">
        <h4>🔍 Extracting Knowledge...</h4>
      </div>
      <div class="progress-events">
        <div v-for="event in extractionEvents" :key="event.id" class="progress-event">
          <span class="event-icon">{{ event.icon }}</span>
          <span class="event-message">{{ event.message }}</span>
          <span v-if="event.timestamp" class="event-time">{{ formatTime(event.timestamp) }}</span>
        </div>
      </div>
    </div>

    <!-- Knowledge Content -->
    <div v-if="knowledge.status === 'ready' && !isExtracting" class="knowledge-content">

      <!-- Summary Card -->
      <div class="knowledge-summary-card">
        <h4>📊 Repository Profile</h4>
        <div v-if="knowledge.profile" class="profile-grid">
          <div class="profile-item">
            <label>Architecture Style:</label>
            <span class="profile-value">{{ knowledge.profile.architecture?.style || 'Unknown' }}</span>
          </div>
          <div class="profile-item">
            <label>Pattern:</label>
            <span class="profile-value">{{ knowledge.profile.architecture?.pattern || 'Unknown' }}</span>
          </div>
          <div class="profile-item">
            <label>Domain:</label>
            <span class="profile-value">{{ knowledge.profile.architecture?.domain || 'Unknown' }}</span>
          </div>
          <div class="profile-item">
            <label>Framework:</label>
            <span class="profile-value">{{ knowledge.profile.tech_stack?.framework || 'Unknown' }}</span>
          </div>
          <div class="profile-item">
            <label>Total Artifacts:</label>
            <span class="profile-value">{{ knowledge.profile.architecture?.total_artifacts || 0 }}</span>
          </div>
          <div class="profile-item">
            <label>Knowledge Docs:</label>
            <span class="profile-value">{{ knowledge.total_docs || 0 }}</span>
          </div>
        </div>
      </div>

      <!-- Knowledge Categories Tabs -->
      <div class="knowledge-categories">
        <div class="category-tabs">
          <button
            v-for="category in categories"
            :key="category.kind"
            @click="selectedCategory = category.kind"
            :class="{ active: selectedCategory === category.kind }"
            class="category-tab">
            {{ category.icon }} {{ category.label }} <span class="tab-count">({{ category.count }})</span>
          </button>
        </div>

        <!-- Category Content -->
        <div class="category-content">
          <!-- Repository Profile -->
          <div v-if="selectedCategory === 'repository_profile'" class="category-panel">
            <RepositoryProfileViewer :profile="knowledge.profile" />
          </div>

          <!-- Domain Model -->
          <div v-else-if="selectedCategory === 'domain_model'" class="category-panel">
            <DomainModelViewer
              :docs="getDocsByKind('domain_model')"
              @refresh="loadKnowledgeDocs" />
          </div>

          <!-- Coding Conventions -->
          <div v-else-if="selectedCategory === 'coding_convention'" class="category-panel">
            <ConventionsList
              :conventions="getDocsByKind('coding_convention')"
              @refresh="loadKnowledgeDocs" />
          </div>

          <!-- Usage Guides -->
          <div v-else-if="selectedCategory === 'usage_guide'" class="category-panel">
            <UsageGuidesList
              :guides="getDocsByKind('usage_guide')"
              @refresh="loadKnowledgeDocs" />
          </div>

          <!-- All Documents -->
          <div v-else-if="selectedCategory === 'all'" class="category-panel">
            <div class="all-docs-list">
              <h4>All Knowledge Documents</h4>
              <div v-for="doc in allDocs" :key="doc.spec_id" class="doc-item">
                <div class="doc-header">
                  <span class="doc-kind-badge">{{ doc.kind }}</span>
                  <span class="doc-title">{{ doc.spec_id }}</span>
                </div>
                <div v-if="doc.description" class="doc-description">
                  {{ doc.description }}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Empty State -->
    <div v-else-if="knowledge.status === 'pending'" class="empty-state">
      <div class="empty-icon">📚</div>
      <h4>No Knowledge Extracted Yet</h4>
      <p>Extract repository knowledge to see architecture patterns, domain models, and coding conventions.</p>
      <button @click="extractKnowledge" class="btn btn-primary btn-lg">
        ✨ Extract Knowledge
      </button>
    </div>

    <!-- Error State -->
    <div v-else-if="knowledge.status === 'error'" class="error-state">
      <div class="error-icon">⚠️</div>
      <h4>Knowledge Extraction Failed</h4>
      <p>An error occurred during knowledge extraction. Please try again.</p>
      <button @click="extractKnowledge" class="btn btn-primary">
        🔄 Retry Extraction
      </button>
    </div>
  </div>
</template>

<script>
import api from '../services/api';
import RepositoryProfileViewer from './knowledge/RepositoryProfileViewer.vue';
import DomainModelViewer from './knowledge/DomainModelViewer.vue';
import ConventionsList from './knowledge/ConventionsList.vue';
import UsageGuidesList from './knowledge/UsageGuidesList.vue';

export default {
  name: 'RepositoryKnowledge',
  components: {
    RepositoryProfileViewer,
    DomainModelViewer,
    ConventionsList,
    UsageGuidesList
  },
  props: {
    repositoryId: {
      type: Number,
      required: true
    },
    systemId: {
      type: Number,
      required: true
    }
  },
  data() {
    return {
      knowledge: {
        status: 'pending',
        profile: null,
        docs_by_kind: {},
        last_extracted: null,
        docs_count: 0,
        total_docs: 0
      },
      allDocs: [],
      selectedCategory: 'repository_profile',
      isExtracting: false,
      extractionEvents: [],
      ws: null,
      apiBaseUrl: 'http://localhost:8000'
    };
  },
  computed: {
    categories() {
      return [
        {
          kind: 'repository_profile',
          label: 'Profile',
          icon: '📊',
          count: this.knowledge.profile ? 1 : 0
        },
        {
          kind: 'domain_model',
          label: 'Domain Model',
          icon: '🏗️',
          count: this.knowledge.docs_by_kind['domain_model'] || 0
        },
        {
          kind: 'coding_convention',
          label: 'Conventions',
          icon: '📝',
          count: this.knowledge.docs_by_kind['coding_convention'] || 0
        },
        {
          kind: 'usage_guide',
          label: 'Usage Guides',
          icon: '📚',
          count: this.knowledge.docs_by_kind['usage_guide'] || 0
        },
        {
          kind: 'all',
          label: 'All Documents',
          icon: '📄',
          count: this.knowledge.total_docs || 0
        }
      ];
    }
  },
  mounted() {
    this.loadKnowledgeSummary();
    this.connectWebSocket();
  },
  beforeUnmount() {
    if (this.ws) {
      this.ws.close();
    }
  },
  methods: {
    async loadKnowledgeSummary() {
      try {
        const response = await api.getKnowledgeSummary(this.systemId, this.repositoryId);
        this.knowledge = response.data;

        // Load all docs if knowledge is ready
        if (this.knowledge.status === 'ready') {
          await this.loadKnowledgeDocs();
        }
      } catch (error) {
        console.error('Failed to load knowledge summary:', error);
      }
    },

    async loadKnowledgeDocs() {
      try {
        const response = await api.getKnowledgeDocs(this.systemId, this.repositoryId);
        this.allDocs = response.data.docs;
      } catch (error) {
        console.error('Failed to load knowledge docs:', error);
      }
    },

    async extractKnowledge() {
      this.isExtracting = true;
      this.extractionEvents = [];

      try {
        const response = await api.extractKnowledge(this.systemId, this.repositoryId, true);

        // Reload knowledge after extraction
        await this.loadKnowledgeSummary();
      } catch (error) {
        console.error('Knowledge extraction failed:', error);
        this.addExtractionEvent('❌', 'Extraction failed: ' + (error.response?.data?.error || error.message));
      } finally {
        this.isExtracting = false;
      }
    },

    connectWebSocket() {
      const wsUrl = `ws://localhost:8000/ws/knowledge/${this.repositoryId}/`;
      this.ws = new WebSocket(wsUrl);

      this.ws.onopen = () => {
        console.log('Knowledge WebSocket connected');
      };

      this.ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        this.handleWebSocketEvent(data);
      };

      this.ws.onerror = (error) => {
        console.error('WebSocket error:', error);
      };

      this.ws.onclose = () => {
        console.log('Knowledge WebSocket disconnected');
      };
    },

    handleWebSocketEvent(data) {
      if (data.type === 'knowledge_extraction_started') {
        this.isExtracting = true;
        this.extractionEvents = [];
        this.addExtractionEvent('🚀', 'Knowledge extraction started');
      }
      else if (data.type === 'knowledge_extraction_progress') {
        const stageIcons = {
          'repository_profile': '📊',
          'domain_model': '🏗️',
          'patterns': '🎨',
          'conventions': '📝',
          'usage_guides': '📚'
        };
        const icon = stageIcons[data.stage] || '⚙️';
        this.addExtractionEvent(icon, data.message);
      }
      else if (data.type === 'knowledge_extraction_complete') {
        this.addExtractionEvent('✅', `Extraction complete! Created ${data.docs_created} documents in ${data.duration_ms}ms`);
        setTimeout(() => {
          this.isExtracting = false;
          this.loadKnowledgeSummary();
        }, 1000);
      }
      else if (data.type === 'knowledge_extraction_error') {
        this.addExtractionEvent('❌', 'Error: ' + data.error);
        setTimeout(() => {
          this.isExtracting = false;
        }, 2000);
      }
    },

    addExtractionEvent(icon, message) {
      this.extractionEvents.push({
        id: Date.now() + Math.random(),
        icon: icon,
        message: message,
        timestamp: new Date()
      });
    },

    getDocsByKind(kind) {
      return this.allDocs.filter(doc => doc.kind === kind);
    },

    formatStatus(status) {
      const statusMap = {
        'pending': 'Pending Extraction',
        'extracting': 'Extracting...',
        'ready': 'Ready',
        'error': 'Error'
      };
      return statusMap[status] || status;
    },

    formatDate(dateString) {
      if (!dateString) return 'Never';
      return new Date(dateString).toLocaleString();
    },

    formatTime(date) {
      return date.toLocaleTimeString();
    }
  }
};
</script>

<style scoped>
.repository-knowledge {
  padding: 20px;
}

.knowledge-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.knowledge-header h3 {
  margin: 0;
  font-size: 1.5em;
}

.btn {
  padding: 8px 16px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.2s;
}

.btn-primary {
  background: #007bff;
  color: white;
}

.btn-primary:hover:not(:disabled) {
  background: #0056b3;
}

.btn-primary:disabled {
  background: #6c757d;
  cursor: not-allowed;
}

.btn-lg {
  padding: 12px 24px;
  font-size: 16px;
}

.status-banner {
  padding: 12px 16px;
  border-radius: 6px;
  margin-bottom: 20px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.status-pending {
  background: #fff3cd;
  border-left: 4px solid #ffc107;
}

.status-extracting {
  background: #d1ecf1;
  border-left: 4px solid #17a2b8;
}

.status-ready {
  background: #d4edda;
  border-left: 4px solid #28a745;
}

.status-error {
  background: #f8d7da;
  border-left: 4px solid #dc3545;
}

.status-timestamp {
  color: #666;
  font-size: 0.9em;
  margin-left: 8px;
}

.extraction-progress {
  background: #f8f9fa;
  border: 1px solid #dee2e6;
  border-radius: 6px;
  padding: 16px;
  margin-bottom: 20px;
}

.progress-header h4 {
  margin: 0 0 12px 0;
}

.progress-events {
  max-height: 300px;
  overflow-y: auto;
}

.progress-event {
  padding: 8px;
  margin: 4px 0;
  background: white;
  border-radius: 4px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.event-icon {
  font-size: 1.2em;
}

.event-message {
  flex: 1;
  font-family: monospace;
  font-size: 0.9em;
}

.event-time {
  color: #666;
  font-size: 0.8em;
}

.knowledge-summary-card {
  background: #f8f9fa;
  padding: 20px;
  border-radius: 8px;
  margin-bottom: 20px;
}

.knowledge-summary-card h4 {
  margin: 0 0 16px 0;
}

.profile-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 16px;
}

.profile-item {
  display: flex;
  flex-direction: column;
}

.profile-item label {
  font-weight: 600;
  font-size: 0.9em;
  color: #666;
  margin-bottom: 4px;
}

.profile-value {
  font-size: 1.1em;
  color: #333;
}

.category-tabs {
  display: flex;
  gap: 8px;
  margin-bottom: 20px;
  border-bottom: 2px solid #e0e0e0;
  overflow-x: auto;
}

.category-tab {
  padding: 12px 20px;
  border: none;
  background: none;
  cursor: pointer;
  border-bottom: 3px solid transparent;
  white-space: nowrap;
  transition: all 0.2s;
}

.category-tab:hover {
  background: #f8f9fa;
}

.category-tab.active {
  border-bottom-color: #007bff;
  color: #007bff;
  font-weight: 600;
}

.tab-count {
  color: #666;
  font-size: 0.9em;
}

.category-content {
  min-height: 400px;
}

.category-panel {
  padding: 20px;
  background: white;
  border: 1px solid #dee2e6;
  border-radius: 6px;
}

.all-docs-list {
  max-height: 600px;
  overflow-y: auto;
}

.doc-item {
  padding: 12px;
  border: 1px solid #dee2e6;
  border-radius: 4px;
  margin-bottom: 8px;
}

.doc-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.doc-kind-badge {
  background: #007bff;
  color: white;
  padding: 2px 8px;
  border-radius: 3px;
  font-size: 0.8em;
  font-weight: 600;
}

.doc-title {
  font-weight: 600;
}

.doc-description {
  color: #666;
  font-size: 0.9em;
}

.empty-state, .error-state {
  text-align: center;
  padding: 60px 20px;
}

.empty-icon, .error-icon {
  font-size: 4em;
  margin-bottom: 16px;
}

.empty-state h4, .error-state h4 {
  margin: 0 0 12px 0;
  font-size: 1.3em;
}

.empty-state p, .error-state p {
  color: #666;
  margin-bottom: 24px;
}
</style>
