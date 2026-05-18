<script setup lang="ts">
import { computed } from 'vue'

import Badge from './primitives/Badge.vue'
import Button from './primitives/Button.vue'
import Collapsible from './primitives/Collapsible.vue'
import type { RepoEntry } from '../api/repos'

const props = defineProps<{ repos: RepoEntry[] }>()

defineEmits<{
  (e: 'delete', repoId: string): void
  (e: 'reindex', repo: RepoEntry): void
}>()

const sortedRepos = computed<RepoEntry[]>(() => [...props.repos])

function formatTimestamp(iso: string | null): string {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}

function badgeToneFor(status: RepoEntry['status']): 'success' | 'info' | 'danger' | 'neutral' {
  switch (status) {
    case 'ready':
      return 'success'
    case 'indexing':
      return 'info'
    case 'failed':
      return 'danger'
    default:
      return 'neutral'
  }
}

function statusLabel(status: RepoEntry['status']): string {
  if (status === 'indexing') return 'INDEXING…'
  return status.toUpperCase()
}
</script>

<template>
  <div
    v-if="sortedRepos.length === 0"
    class="px-4 py-3 text-sm text-muted"
    :style="{
      border: '1px dashed var(--color-border)',
      borderRadius: 'var(--radius-md)',
    }"
  >
    No repositories indexed yet. Submit one above.
  </div>
  <div v-else class="flex flex-col gap-2">
    <Collapsible v-for="r in sortedRepos" :key="r.repo_id" :default-open="false">
      <template #header="{ open }">
        <div
          class="flex items-center justify-between gap-3 px-4 py-3 surface-card"
          :style="{ borderRadius: open ? 'var(--radius-md) var(--radius-md) 0 0' : 'var(--radius-md)' }"
        >
          <div class="flex items-center gap-3 min-w-0 flex-1">
            <span
              class="text-xs text-muted"
              aria-hidden="true"
            >{{ open ? '▾' : '▸' }}</span>
            <code
              class="font-mono text-sm truncate"
              :style="{ color: 'var(--color-text)' }"
            >{{ r.source }}</code>
          </div>
          <Badge :tone="badgeToneFor(r.status)">{{ statusLabel(r.status) }}</Badge>
        </div>
      </template>
      <template #body>
        <div
          class="px-4 py-3 surface-card text-sm"
          :style="{
            borderTop: 'none',
            borderRadius: '0 0 var(--radius-md) var(--radius-md)',
          }"
        >
          <dl class="grid grid-cols-2 gap-x-4 gap-y-2 m-0">
            <dt class="text-xs uppercase tracking-wide text-muted">Chunks</dt>
            <dd class="font-mono" :style="{ color: 'var(--color-text)' }">
              {{ r.chunk_count }}
            </dd>
            <dt class="text-xs uppercase tracking-wide text-muted">Indexed at</dt>
            <dd class="font-mono" :style="{ color: 'var(--color-text)' }">
              {{ formatTimestamp(r.indexed_at) }}
            </dd>
            <dt class="text-xs uppercase tracking-wide text-muted">Provider · Model</dt>
            <dd class="font-mono" :style="{ color: 'var(--color-text)' }">
              {{ r.embedding_provider || '—' }} · {{ r.embedding_model || '—' }}
            </dd>
            <template v-if="r.status === 'failed' && r.last_error">
              <dt class="text-xs uppercase tracking-wide text-muted">Last error</dt>
              <dd
                class="font-mono text-xs break-words"
                :style="{ color: 'var(--color-danger-fg)' }"
              >
                {{ r.last_error }}
              </dd>
            </template>
          </dl>
          <div class="flex justify-end gap-2 mt-3">
            <Button
              variant="secondary"
              size="sm"
              :disabled="r.status === 'indexing'"
              @click="$emit('reindex', r)"
            >Re-index</Button>
            <Button
              variant="danger"
              size="sm"
              :disabled="r.status === 'indexing'"
              @click="$emit('delete', r.repo_id)"
            >Delete</Button>
          </div>
        </div>
      </template>
    </Collapsible>
  </div>
</template>
