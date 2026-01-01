<template>
  <div class="repository-profile-viewer">
    <div v-if="profile">
      <div class="profile-section">
        <h4>🏛️ Architecture</h4>
        <div class="info-grid">
          <div class="info-item">
            <label>Style:</label>
            <span class="badge badge-primary">{{ profile.architecture?.style || 'Unknown' }}</span>
          </div>
          <div class="info-item">
            <label>Pattern:</label>
            <span class="badge badge-secondary">{{ profile.architecture?.pattern || 'Unknown' }}</span>
          </div>
          <div class="info-item">
            <label>Domain:</label>
            <span class="badge badge-info">{{ profile.architecture?.domain || 'Unknown' }}</span>
          </div>
        </div>
      </div>

      <div class="profile-section">
        <h4>⚙️ Tech Stack</h4>
        <div class="info-grid">
          <div class="info-item">
            <label>Language:</label>
            <span>{{ profile.tech_stack?.language || 'Unknown' }}</span>
          </div>
          <div class="info-item">
            <label>Framework:</label>
            <span>{{ profile.tech_stack?.framework || 'Unknown' }}</span>
          </div>
          <div class="info-item">
            <label>Conventions:</label>
            <span>{{ profile.tech_stack?.conventions || 'Unknown' }}</span>
          </div>
        </div>
      </div>

      <div v-if="profile.architecture?.artifact_counts" class="profile-section">
        <h4>📦 Artifacts</h4>
        <div class="artifact-counts">
          <div
            v-for="(count, kind) in profile.architecture.artifact_counts"
            :key="kind"
            class="artifact-count-item">
            <span class="artifact-kind">{{ formatKind(kind) }}</span>
            <span class="artifact-count">{{ count }}</span>
          </div>
        </div>
      </div>

      <div v-if="profile.repository" class="profile-section">
        <h4>🔗 Repository Info</h4>
        <div class="info-grid">
          <div class="info-item">
            <label>Name:</label>
            <span>{{ profile.repository.name }}</span>
          </div>
          <div class="info-item">
            <label>GitHub URL:</label>
            <a :href="profile.repository.github_url" target="_blank" class="link">
              {{ profile.repository.github_url }}
            </a>
          </div>
          <div v-if="profile.extracted_at" class="info-item">
            <label>Extracted:</label>
            <span>{{ formatDate(profile.extracted_at) }}</span>
          </div>
        </div>
      </div>
    </div>

    <div v-else class="no-profile">
      <p>No repository profile available. Please extract knowledge first.</p>
    </div>
  </div>
</template>

<script>
export default {
  name: 'RepositoryProfileViewer',
  props: {
    profile: {
      type: Object,
      default: null
    }
  },
  methods: {
    formatKind(kind) {
      return kind.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
    },
    formatDate(dateString) {
      return new Date(dateString).toLocaleString();
    }
  }
};
</script>

<style scoped>
.repository-profile-viewer {
  padding: 16px;
}

.profile-section {
  margin-bottom: 24px;
  padding-bottom: 16px;
  border-bottom: 1px solid #e0e0e0;
}

.profile-section:last-child {
  border-bottom: none;
}

.profile-section h4 {
  margin: 0 0 12px 0;
  font-size: 1.1em;
}

.info-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 12px;
}

.info-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.info-item label {
  font-weight: 600;
  font-size: 0.9em;
  color: #666;
}

.badge {
  display: inline-block;
  padding: 4px 12px;
  border-radius: 4px;
  font-size: 0.9em;
  font-weight: 600;
}

.badge-primary {
  background: #007bff;
  color: white;
}

.badge-secondary {
  background: #6c757d;
  color: white;
}

.badge-info {
  background: #17a2b8;
  color: white;
}

.artifact-counts {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 8px;
}

.artifact-count-item {
  display: flex;
  justify-content: space-between;
  padding: 8px 12px;
  background: #f8f9fa;
  border-radius: 4px;
  border-left: 3px solid #007bff;
}

.artifact-kind {
  font-weight: 600;
}

.artifact-count {
  color: #007bff;
  font-weight: 700;
}

.link {
  color: #007bff;
  text-decoration: none;
}

.link:hover {
  text-decoration: underline;
}

.no-profile {
  text-align: center;
  padding: 40px;
  color: #666;
}
</style>
