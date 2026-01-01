<template>
  <div class="conventions-list">
    <div v-if="conventions && conventions.length > 0">
      <div v-for="conv in conventions" :key="conv.spec_id" class="convention-item">
        <h4>{{ conv.description || conv.spec_id }}</h4>
        <div v-if="conv.category" class="convention-category">
          Category: <span class="badge">{{ conv.category }}</span>
        </div>

        <div v-if="conv.rules && conv.rules.length > 0" class="rules-section">
          <h5>Rules</h5>
          <div v-for="(rule, index) in conv.rules" :key="index" class="rule-item">
            <div class="rule-name">{{ rule.name || 'Rule ' + (index + 1) }}</div>
            <div v-if="rule.pattern" class="rule-pattern">
              <strong>Pattern:</strong> <code>{{ rule.pattern }}</code>
            </div>
            <div v-if="rule.value !== undefined" class="rule-value">
              <strong>Value:</strong> {{ rule.value }}
            </div>
            <div v-if="rule.description" class="rule-description">
              {{ rule.description }}
            </div>
            <div v-if="rule.rationale" class="rule-rationale">
              <em>Rationale:</em> {{ rule.rationale }}
            </div>
          </div>
        </div>

        <div v-if="conv.examples && conv.examples.length > 0" class="examples-section">
          <h5>Examples</h5>
          <div class="examples-grid">
            <div v-for="(example, index) in conv.examples" :key="index" class="example-item">
              <div v-if="example.model">{{ example.model }}</div>
              <div v-if="example.file" class="example-location">
                {{ example.file }}
                <span v-if="example.line">:{{ example.line }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div v-else class="no-conventions">
      <p>No coding conventions documented yet.</p>
      <button @click="$emit('refresh')" class="btn btn-sm">Refresh</button>
    </div>
  </div>
</template>

<script>
export default {
  name: 'ConventionsList',
  props: {
    conventions: {
      type: Array,
      default: () => []
    }
  }
};
</script>

<style scoped>
.conventions-list {
  padding: 16px;
}

.convention-item {
  margin-bottom: 24px;
  padding-bottom: 24px;
  border-bottom: 1px solid #e0e0e0;
}

.convention-item:last-child {
  border-bottom: none;
}

.convention-item h4 {
  margin: 0 0 8px 0;
}

.convention-category {
  margin-bottom: 12px;
  color: #666;
}

.badge {
  background: #007bff;
  color: white;
  padding: 2px 8px;
  border-radius: 3px;
  font-size: 0.9em;
}

.rules-section, .examples-section {
  margin-top: 16px;
}

.rules-section h5, .examples-section h5 {
  margin: 0 0 12px 0;
  color: #666;
  font-size: 1em;
}

.rule-item {
  padding: 12px;
  background: #f8f9fa;
  border-left: 3px solid #007bff;
  border-radius: 4px;
  margin-bottom: 8px;
}

.rule-name {
  font-weight: 600;
  margin-bottom: 8px;
}

.rule-pattern, .rule-value, .rule-description {
  margin: 4px 0;
  font-size: 0.95em;
}

.rule-pattern code {
  background: #e9ecef;
  padding: 2px 6px;
  border-radius: 3px;
  font-family: monospace;
}

.rule-rationale {
  margin-top: 8px;
  color: #666;
  font-size: 0.9em;
}

.examples-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
  gap: 8px;
}

.example-item {
  padding: 8px;
  background: #f8f9fa;
  border-radius: 4px;
  font-size: 0.9em;
}

.example-location {
  font-family: monospace;
  color: #666;
  font-size: 0.85em;
}

.no-conventions {
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
