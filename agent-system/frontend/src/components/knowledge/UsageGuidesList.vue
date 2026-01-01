<template>
  <div class="usage-guides-list">
    <div v-if="guides && guides.length > 0">
      <div v-for="guide in guides" :key="guide.spec_id" class="guide-item">
        <h4>{{ guide.use_case || guide.spec_id }}</h4>
        <div v-if="guide.description" class="guide-description">
          {{ guide.description }}
        </div>

        <div v-if="guide.steps && guide.steps.length > 0" class="steps-section">
          <h5>Steps</h5>
          <div class="steps-list">
            <div v-for="(step, index) in guide.steps" :key="index" class="step-item">
              <div class="step-header">
                <span class="step-number">{{ step.step || (index + 1) }}</span>
                <span class="step-action">{{ step.action }}</span>
              </div>
              <div v-if="step.location" class="step-detail">
                <strong>Location:</strong> {{ step.location }}
              </div>
              <div v-if="step.template" class="step-detail">
                <strong>Template:</strong> {{ step.template }}
              </div>
              <div v-if="step.note" class="step-note">
                💡 {{ step.note }}
              </div>
              <div v-if="step.code" class="step-code">
                <code>{{ step.code }}</code>
              </div>
              <div v-if="step.example" class="step-example">
                <strong>Example:</strong> <code>{{ step.example }}</code>
              </div>
            </div>
          </div>
        </div>

        <div v-if="guide.reference_implementation" class="reference-section">
          <h5>Reference Implementation</h5>
          <div class="reference-link">
            📁 {{ guide.reference_implementation }}
          </div>
        </div>
      </div>
    </div>

    <div v-else class="no-guides">
      <p>No usage guides available yet.</p>
      <button @click="$emit('refresh')" class="btn btn-sm">Refresh</button>
    </div>
  </div>
</template>

<script>
export default {
  name: 'UsageGuidesList',
  props: {
    guides: {
      type: Array,
      default: () => []
    }
  }
};
</script>

<style scoped>
.usage-guides-list {
  padding: 16px;
}

.guide-item {
  margin-bottom: 32px;
  padding-bottom: 24px;
  border-bottom: 2px solid #e0e0e0;
}

.guide-item:last-child {
  border-bottom: none;
}

.guide-item h4 {
  margin: 0 0 8px 0;
  color: #333;
}

.guide-description {
  color: #666;
  margin-bottom: 16px;
}

.steps-section, .reference-section {
  margin-top: 16px;
}

.steps-section h5, .reference-section h5 {
  margin: 0 0 12px 0;
  color: #666;
  font-size: 1em;
}

.steps-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.step-item {
  padding: 16px;
  background: #f8f9fa;
  border-left: 4px solid #007bff;
  border-radius: 6px;
}

.step-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.step-number {
  background: #007bff;
  color: white;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  flex-shrink: 0;
}

.step-action {
  font-weight: 600;
  font-size: 1.05em;
}

.step-detail {
  margin: 6px 0;
  font-size: 0.95em;
}

.step-note {
  margin: 8px 0;
  padding: 8px 12px;
  background: #fff3cd;
  border-left: 3px solid #ffc107;
  border-radius: 4px;
  font-size: 0.9em;
}

.step-code, .step-example {
  margin: 8px 0;
}

code {
  background: #e9ecef;
  padding: 2px 6px;
  border-radius: 3px;
  font-family: monospace;
  font-size: 0.9em;
}

.reference-link {
  padding: 12px;
  background: #e7f3ff;
  border: 1px solid #007bff;
  border-radius: 4px;
  font-family: monospace;
}

.no-guides {
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
