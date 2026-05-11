<script setup lang="ts">
import { onMounted, ref } from 'vue'

type ProbeStatus = 'ok' | 'down' | 'missing' | 'unknown' | 'pending'

interface HealthEnvelope {
  status: 'ok' | 'degraded'
  db: 'ok' | 'down'
  redis: 'ok' | 'down'
  extensions: { vector: 'ok' | 'missing' | 'unknown' }
  failing?: string[]
}

const overall = ref<ProbeStatus>('pending')
const db = ref<ProbeStatus>('pending')
const redis = ref<ProbeStatus>('pending')
const vector = ref<ProbeStatus>('pending')
const errorMessage = ref<string>('')

function colorFor(status: ProbeStatus): string {
  if (status === 'ok') return '#16a34a'
  if (status === 'pending') return '#9ca3af'
  return '#dc2626'
}

onMounted(async () => {
  try {
    const response = await fetch('/api/healthz')
    const body = (await response.json()) as HealthEnvelope
    overall.value = body.status === 'ok' ? 'ok' : 'down'
    db.value = body.db
    redis.value = body.redis
    vector.value = body.extensions.vector
    if (body.status !== 'ok' && body.failing && body.failing.length) {
      errorMessage.value = 'Failing: ' + body.failing.join(', ')
    }
  } catch (err) {
    overall.value = 'down'
    db.value = 'down'
    redis.value = 'down'
    vector.value = 'unknown'
    errorMessage.value = (err as Error).message || 'healthcheck call failed'
  }
})
</script>

<template>
  <main>
    <h1>CodeSensei</h1>
    <p class="subtitle">Infrastructure scaffold — healthcheck</p>
    <ul class="badges">
      <li>
        <span class="dot" :style="{ background: colorFor(overall) }" aria-hidden="true"></span>
        overall: <strong>{{ overall }}</strong>
      </li>
      <li>
        <span class="dot" :style="{ background: colorFor(db) }" aria-hidden="true"></span>
        db: <strong>{{ db }}</strong>
      </li>
      <li>
        <span class="dot" :style="{ background: colorFor(redis) }" aria-hidden="true"></span>
        redis: <strong>{{ redis }}</strong>
      </li>
      <li>
        <span class="dot" :style="{ background: colorFor(vector) }" aria-hidden="true"></span>
        pgvector: <strong>{{ vector }}</strong>
      </li>
    </ul>
    <p v-if="errorMessage" class="error">{{ errorMessage }}</p>
  </main>
</template>

<style scoped>
main {
  font-family: system-ui, -apple-system, Segoe UI, sans-serif;
  max-width: 32rem;
  margin: 2rem auto;
  padding: 1rem;
  color: #0f172a;
}
h1 {
  margin: 0 0 0.25rem;
  font-size: 1.5rem;
}
.subtitle {
  color: #64748b;
  margin: 0 0 1rem;
}
.badges {
  list-style: none;
  padding: 0;
  margin: 0;
}
.badges li {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.35rem 0;
  font-family: ui-monospace, Menlo, monospace;
  font-size: 0.95rem;
}
.dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  display: inline-block;
}
.error {
  margin-top: 1rem;
  color: #dc2626;
  font-size: 0.85rem;
}
</style>
