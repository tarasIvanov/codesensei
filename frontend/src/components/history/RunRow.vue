<script setup lang="ts">
import { computed } from 'vue'
import Badge from '../primitives/Badge.vue'
import type { ReviewRunSummary } from '../../api/reviews'

const props = defineProps<{ run: ReviewRunSummary }>()
defineEmits<{ (e: 'click', runId: string): void }>()

const VERDICT_TONE: Record<string, 'success' | 'danger' | 'info'> = {
  approve: 'success',
  request_changes: 'danger',
  comment: 'info',
}

const VERDICT_LABEL: Record<string, string> = {
  approve: 'approve',
  request_changes: 'request changes',
  comment: 'comment',
}

function relativeTimestamp(iso: string): string {
  const then = new Date(iso).getTime()
  const now = Date.now()
  const diffSec = Math.round((now - then) / 1000)
  if (diffSec < 60) return diffSec <= 5 ? 'just now' : `${diffSec}s ago`
  if (diffSec < 3600) return `${Math.round(diffSec / 60)} min ago`
  if (diffSec < 86400) return `${Math.round(diffSec / 3600)} h ago`
  return `${Math.round(diffSec / 86400)} d ago`
}

function shortPrUrl(url: string): string {
  const m = url.match(/github\.com\/([^/]+)\/([^/]+)\/pull\/(\d+)/)
  if (m) return `${m[1]}/${m[2]}#${m[3]}`
  return url
}

const verdictTone = computed(() => VERDICT_TONE[props.run.verdict] ?? 'info')
const verdictLabel = computed(() => VERDICT_LABEL[props.run.verdict] ?? props.run.verdict)
</script>

<template>
  <button
    type="button"
    class="focus-ring w-full text-left transition-colors duration-150 cursor-pointer"
    :style="{
      padding: '0.75rem 1rem',
      borderTop: '1px solid var(--color-border)',
      backgroundColor: 'var(--color-bg-card)',
    }"
    @click="$emit('click', run.id)"
  >
    <div class="flex items-center gap-3 flex-wrap">
      <Badge :tone="verdictTone">{{ verdictLabel }}</Badge>
      <span class="text-xs font-mono" :style="{ color: 'var(--color-text-muted)' }">
        {{ relativeTimestamp(run.created_at) }}
      </span>
      <Badge tone="neutral">{{ run.provider }}</Badge>
      <span class="text-xs" :style="{ color: 'var(--color-text-muted)' }">
        {{ run.finding_count }} {{ run.finding_count === 1 ? 'finding' : 'findings' }}
      </span>
      <span v-if="run.has_temporal" class="text-xs" :style="{ color: 'var(--color-text-muted)' }">
        · with history
      </span>
      <span
        v-if="run.pr_url"
        class="text-xs font-mono truncate"
        :style="{ color: 'var(--color-text-muted)', maxWidth: '20rem' }"
        :title="run.pr_url"
      >
        {{ shortPrUrl(run.pr_url) }}
      </span>
      <span
        class="ml-auto text-xs font-mono"
        :style="{ color: 'var(--color-text-muted)' }"
      >
        {{ run.elapsed_ms }} ms
      </span>
    </div>
  </button>
</template>
