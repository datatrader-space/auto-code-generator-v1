<template>
  <div class="domain-model-viewer">
    <div v-if="docs && docs.length > 0">
      <div v-for="doc in docs" :key="doc.spec_id" class="domain-model-doc">
        <h4>{{ doc.description || 'Domain Model' }}</h4>

        <div v-if="doc.entities && doc.entities.length > 0" class="entities-section">
          <h5>📦 Entities ({{ doc.entities.length }})</h5>
          <div class="entities-grid">
            <div
              v-for="entity in doc.entities"
              :key="entity.id"
              class="entity-card"
              :class="`role-${entity.role}`">
              <div class="entity-header">
                <span class="entity-name">{{ entity.name }}</span>
                <span class="entity-role-badge">{{ formatRole(entity.role) }}</span>
              </div>
              <div class="entity-location">
                {{ entity.file }}:{{ entity.line }}
              </div>
              <div v-if="doc.relationships && doc.relationships[entity.name]" class="entity-relationships">
                <div v-if="doc.relationships[entity.name].outgoing && doc.relationships[entity.name].outgoing.length > 0" class="rel-section">
                  <strong>Outgoing:</strong> {{ doc.relationships[entity.name].outgoing.slice(0, 3).map(r => r.target || r).join(', ') }}
                  <span v-if="doc.relationships[entity.name].outgoing.length > 3">...</span>
                </div>
                <div v-if="doc.relationships[entity.name].incoming && doc.relationships[entity.name].incoming.length > 0" class="rel-section">
                  <strong>Incoming:</strong> {{ doc.relationships[entity.name].incoming.slice(0, 3).map(r => r.source || r).join(', ') }}
                  <span v-if="doc.relationships[entity.name].incoming.length > 3">...</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div v-else class="no-docs">
      <p>No domain model documents available.</p>
      <button @click="$emit('refresh')" class="btn btn-sm">Refresh</button>
    </div>
  </div>
</template>

<script>
export default {
  name: 'DomainModelViewer',
  props: {
    docs: {
      type: Array,
      default: () => []
    }
  },
  methods: {
    formatRole(role) {
      return role.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
    }
  }
};
</script>

<style scoped>
.domain-model-viewer {
  padding: 16px;
}

.domain-model-doc {
  margin-bottom: 24px;
}

.domain-model-doc h4 {
  margin: 0 0 16px 0;
}

.entities-section h5 {
  margin: 0 0 12px 0;
  color: #666;
}

.entities-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 12px;
}

.entity-card {
  padding: 12px;
  border: 2px solid #e0e0e0;
  border-radius: 6px;
  background: white;
}

.entity-card.role-identity {
  border-left-color: #007bff;
}

.entity-card.role-transaction {
  border-left-color: #28a745;
}

.entity-card.role-master_data {
  border-left-color: #ffc107;
}

.entity-card.role-referenced_entity {
  border-left-color: #17a2b8;
}

.entity-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.entity-name {
  font-weight: 700;
  font-size: 1.1em;
}

.entity-role-badge {
  background: #f0f0f0;
  padding: 2px 8px;
  border-radius: 3px;
  font-size: 0.8em;
  color: #666;
}

.entity-location {
  font-family: monospace;
  font-size: 0.85em;
  color: #666;
  margin-bottom: 8px;
}

.entity-relationships {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid #f0f0f0;
  font-size: 0.85em;
}

.rel-section {
  margin: 4px 0;
  color: #666;
}

.no-docs {
  text-align: center;
  padding: 40px;
  color: #666;
}

.btn {
  padding: 6px 12px;
  border: 1px solid #007bff;
  background: white;
  color: #007bff;
  border-radius: 4px;
  cursor: pointer;
}

.btn:hover {
  background: #007bff;
  color: white;
}
</style>
