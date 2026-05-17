<script setup lang="ts">
import { computed } from 'vue'

import type { RepoEntry } from '../api/repos'

const props = defineProps<{
  repos: RepoEntry[]
}>()

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

function statusLabel(status: RepoEntry['status']): string {
  return status === 'ready' ? 'ready' : status === 'indexing' ? 'indexing…' : 'failed'
}
</script>

<template>
  <div v-if="sortedRepos.length === 0" class="empty">
    No repositories indexed yet. Submit one above.
  </div>
  <table v-else class="table">
    <thead>
      <tr>
        <th>Source</th>
        <th>Status</th>
        <th>Chunks</th>
        <th>Indexed at</th>
        <th>Provider · Model</th>
        <th class="actions-col">Actions</th>
      </tr>
    </thead>
    <tbody>
      <tr v-for="r in sortedRepos" :key="r.repo_id">
        <td><code>{{ r.source }}</code></td>
        <td>
          <span class="pill" :data-status="r.status">{{ statusLabel(r.status) }}</span>
          <span v-if="r.status === 'failed' && r.last_error" class="error-snippet" :title="r.last_error">
            (see error)
          </span>
        </td>
        <td>{{ r.chunk_count }}</td>
        <td>{{ formatTimestamp(r.indexed_at) }}</td>
        <td>{{ r.embedding_provider || '—' }} · {{ r.embedding_model || '—' }}</td>
        <td class="actions-col">
          <button class="action" :disabled="r.status === 'indexing'" @click="$emit('reindex', r)">
            Re-index
          </button>
          <button class="action danger" :disabled="r.status === 'indexing'" @click="$emit('delete', r.repo_id)">
            Delete
          </button>
        </td>
      </tr>
    </tbody>
  </table>
</template>

<style scoped>
.empty {
  margin: 0.6rem 0;
  padding: 0.7rem 0.85rem;
  background: #f8fafc;
  border: 1px dashed #cbd5e1;
  border-radius: 0.5rem;
  color: #64748b;
  font-size: 0.9rem;
}
.table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.88rem;
  margin-top: 0.6rem;
}
.table th,
.table td {
  text-align: left;
  padding: 0.45rem 0.55rem;
  border-bottom: 1px solid #e2e8f0;
  vertical-align: middle;
}
.table th {
  color: #475569;
  font-weight: 600;
  font-size: 0.78rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
code {
  font-family: ui-monospace, Menlo, monospace;
  font-size: 0.8rem;
}
.pill {
  display: inline-block;
  padding: 0.1rem 0.5rem;
  border-radius: 9999px;
  font-size: 0.75rem;
  font-weight: 600;
}
.pill[data-status='ready'] {
  background: #ecfdf5;
  color: #065f46;
}
.pill[data-status='indexing'] {
  background: #fef3c7;
  color: #92400e;
}
.pill[data-status='failed'] {
  background: #fef2f2;
  color: #991b1b;
}
.error-snippet {
  margin-left: 0.35rem;
  color: #b91c1c;
  cursor: help;
  font-size: 0.75rem;
}
.actions-col {
  text-align: right;
  white-space: nowrap;
}
.action {
  background: #2563eb;
  color: #ffffff;
  border: 0;
  border-radius: 0.35rem;
  padding: 0.25rem 0.65rem;
  margin-left: 0.3rem;
  font-size: 0.78rem;
  cursor: pointer;
}
.action.danger {
  background: #b91c1c;
}
.action:disabled {
  background: #cbd5e1;
  color: #64748b;
  cursor: not-allowed;
}
</style>
