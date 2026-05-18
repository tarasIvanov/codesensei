<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import Card from '../components/primitives/Card.vue'
import StatusDot from '../components/primitives/StatusDot.vue'

type ProbeStatus = 'ok' | 'down' | 'missing' | 'unknown' | 'pending'
type ProviderStatus = 'ok' | 'unconfigured' | 'unreachable' | 'pending'
type WorkerStatus = 'ok' | 'down' | 'unreachable' | 'pending'

type AnyStatus = ProbeStatus | ProviderStatus | WorkerStatus

interface HealthEnvelope {
  status: 'ok' | 'degraded'
  db: 'ok' | 'down'
  redis: 'ok' | 'down'
  extensions: { vector: 'ok' | 'missing' | 'unknown' }
  providers: { llm: ProviderStatus; embedding: ProviderStatus }
  worker: WorkerStatus
  failing?: string[]
}

interface Row {
  label: string
  status: AnyStatus
  error?: string | null
}

const overall = ref<ProbeStatus>('pending')
const rows = ref<Row[]>([])
const errorMessage = ref('')

function dotState(status: AnyStatus): 'ok' | 'degraded' | 'error' {
  if (status === 'ok') return 'ok'
  if (status === 'pending') return 'degraded'
  if (status === 'unconfigured') return 'degraded'
  if (status === 'missing') return 'degraded'
  if (status === 'unknown') return 'degraded'
  return 'error'
}

onMounted(async () => {
  try {
    const response = await fetch('/api/healthz')
    const body = (await response.json()) as HealthEnvelope
    overall.value = body.status === 'ok' ? 'ok' : 'down'
    rows.value = [
      { label: 'db', status: body.db },
      { label: 'redis', status: body.redis },
      { label: 'pgvector', status: body.extensions.vector },
      { label: 'llm', status: body.providers?.llm ?? 'unconfigured' },
      { label: 'embedding', status: body.providers?.embedding ?? 'unconfigured' },
      { label: 'worker', status: body.worker ?? 'unreachable' },
    ]
    if (body.status !== 'ok' && body.failing && body.failing.length) {
      errorMessage.value = 'Failing: ' + body.failing.join(', ')
    }
  } catch (err) {
    overall.value = 'down'
    rows.value = [
      { label: 'db', status: 'down' },
      { label: 'redis', status: 'down' },
      { label: 'pgvector', status: 'unknown' },
      { label: 'llm', status: 'unreachable' },
      { label: 'embedding', status: 'unreachable' },
      { label: 'worker', status: 'unreachable' },
    ]
    errorMessage.value = (err as Error).message || 'healthcheck call failed'
  }
})

const overallText = computed(() => `${overall.value.toUpperCase()}`)
</script>

<template>
  <Card>
    <template #header>
      <div class="flex items-center justify-between gap-4">
        <div>
          <h1 class="text-2xl font-semibold m-0" :style="{ color: 'var(--color-text)' }">
            CodeSensei status
          </h1>
          <p class="text-sm text-muted m-0 mt-1">
            Live healthcheck for every backend dependency and provider.
          </p>
        </div>
        <StatusDot
          :state="dotState(overall)"
          :label="overallText"
          :error="errorMessage || null"
        />
      </div>
    </template>
    <ul class="m-0 p-0 list-none flex flex-col gap-3">
      <li
        v-for="row in rows"
        :key="row.label"
        class="flex items-center gap-3 font-mono text-sm"
      >
        <StatusDot
          :state="dotState(row.status)"
          :label="row.label"
          :error="row.status === 'ok' ? null : String(row.status)"
        />
        <span class="text-muted">·</span>
        <strong :style="{ color: 'var(--color-text)' }">{{ row.status }}</strong>
      </li>
    </ul>
    <p v-if="errorMessage" class="text-sm mt-4" :style="{ color: 'var(--color-danger-fg)' }">
      {{ errorMessage }}
    </p>
  </Card>
</template>
