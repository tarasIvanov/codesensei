<script setup lang="ts">
import { computed } from 'vue'
import Badge from '../primitives/Badge.vue'
import Collapsible from '../primitives/Collapsible.vue'
import CodeContextSnippet from './CodeContextSnippet.vue'
import SeverityPill, { type Severity } from './SeverityPill.vue'

export interface TemporalEntry {
  commit_sha: string
  short_sha: string
  author_email: string
  author_date: string
  subject: string
  hunk_lines_changed: number
}

export interface Finding {
  file: string
  line: number | null
  severity: Severity
  message: string
  suggestion?: string | null
  temporal_context?: TemporalEntry[] | null
}

const props = withDefaults(
  defineProps<{
    finding: Finding
    patch?: string | null
    dismissed?: boolean
    dismissible?: boolean
  }>(),
  { dismissed: false, dismissible: false },
)

const emit = defineEmits<{
  (e: 'dismiss'): void
  (e: 'restore'): void
}>()

const historyEntries = computed<TemporalEntry[]>(() => props.finding.temporal_context ?? [])
const hasHistory = computed(() => historyEntries.value.length > 0)
const showVolatilityBadge = computed(() => historyEntries.value.length >= 3)

function formatDate(iso: string): string {
  return iso.slice(0, 10)
}

function formatAuthor(email: string): string {
  const at = email.indexOf('@')
  return at > 0 ? email.slice(0, at) : email
}

function truncateSubject(subject: string): string {
  if (subject.length <= 80) return subject
  return subject.slice(0, 79) + '…'
}
</script>

<template>
  <article
    class="px-4 py-3"
    :style="{
      backgroundColor: 'var(--color-bg-card)',
      borderTop: '1px solid var(--color-border)',
      opacity: dismissed ? 0.55 : 1,
    }"
  >
    <header class="flex items-center gap-2 mb-1">
      <SeverityPill :severity="finding.severity" />
      <Badge v-if="showVolatilityBadge" tone="info">
        {{ historyEntries.length }} changes
      </Badge>
      <Badge v-if="dismissed" tone="neutral">dismissed</Badge>
      <span class="text-xs font-mono text-muted">
        {{ finding.line !== null ? `line ${finding.line}` : 'file-level' }}
      </span>
      <button
        v-if="dismissible"
        type="button"
        class="focus-ring ml-auto text-xs px-2 py-0.5 cursor-pointer"
        :style="{
          border: '1px solid var(--color-border)',
          borderRadius: 'var(--radius-sm)',
          backgroundColor: 'var(--color-bg-elevated)',
          color: 'var(--color-text-muted)',
        }"
        @click="dismissed ? emit('restore') : emit('dismiss')"
      >{{ dismissed ? 'Restore' : 'Dismiss' }}</button>
    </header>
    <p
      class="m-0 text-sm leading-relaxed break-words"
      :style="{
        color: 'var(--color-text)',
        textDecoration: dismissed ? 'line-through' : 'none',
      }"
    >
      {{ finding.message }}
    </p>
    <div v-if="finding.suggestion" class="mt-2">
      <div
        class="text-[10px] font-semibold uppercase tracking-wide mb-1"
        :style="{ color: 'var(--color-text-muted)' }"
      >Suggested fix</div>
      <pre
        class="m-0 p-2 text-xs font-mono whitespace-pre-wrap break-words overflow-x-auto"
        :style="{
          backgroundColor: 'var(--color-neutral-900)',
          color: 'var(--color-neutral-50)',
          borderRadius: 'var(--radius-sm)',
        }"
      >{{ finding.suggestion }}</pre>
    </div>
    <CodeContextSnippet
      v-if="patch && finding.line !== null"
      :patch="patch"
      :target-line="finding.line"
    />
    <div v-if="hasHistory" class="mt-3">
      <Collapsible :default-open="false">
        <template #header="{ open }">
          <span
            class="inline-flex items-center gap-1 text-xs font-medium"
            :style="{ color: 'var(--color-text-muted)' }"
          >
            <span :style="{ transform: open ? 'rotate(90deg)' : 'rotate(0deg)', display: 'inline-block', transition: 'transform 150ms ease' }">▸</span>
            History ({{ historyEntries.length }} {{ historyEntries.length === 1 ? 'change' : 'changes' }})
          </span>
        </template>
        <template #body>
          <table
            class="w-full text-xs mt-2"
            :style="{ borderCollapse: 'collapse' }"
          >
            <thead>
              <tr :style="{ color: 'var(--color-text-muted)' }">
                <th class="text-left font-medium pb-1 pr-3">SHA</th>
                <th class="text-left font-medium pb-1 pr-3">Date</th>
                <th class="text-left font-medium pb-1 pr-3">Author</th>
                <th class="text-left font-medium pb-1">Subject</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="entry in historyEntries"
                :key="entry.commit_sha"
                :style="{ borderTop: '1px solid var(--color-border)' }"
              >
                <td class="font-mono py-1 pr-3 text-muted">{{ entry.short_sha }}</td>
                <td class="py-1 pr-3">{{ formatDate(entry.author_date) }}</td>
                <td class="py-1 pr-3">{{ formatAuthor(entry.author_email) }}</td>
                <td class="py-1 break-words">{{ truncateSubject(entry.subject) }}</td>
              </tr>
            </tbody>
          </table>
        </template>
      </Collapsible>
    </div>
  </article>
</template>
