<script setup lang="ts">
import CodeContextSnippet from './CodeContextSnippet.vue'
import SeverityPill, { type Severity } from './SeverityPill.vue'

export interface Finding {
  file: string
  line: number | null
  severity: Severity
  message: string
  suggestion?: string | null
}

defineProps<{ finding: Finding; patch?: string | null }>()
</script>

<template>
  <article
    class="px-4 py-3"
    :style="{
      backgroundColor: 'var(--color-bg-card)',
      borderTop: '1px solid var(--color-border)',
    }"
  >
    <header class="flex items-center gap-2 mb-1">
      <SeverityPill :severity="finding.severity" />
      <span class="text-xs font-mono text-muted">
        {{ finding.line !== null ? `line ${finding.line}` : 'file-level' }}
      </span>
    </header>
    <p class="m-0 text-sm leading-relaxed break-words" :style="{ color: 'var(--color-text)' }">
      {{ finding.message }}
    </p>
    <pre
      v-if="finding.suggestion"
      class="mt-2 p-2 text-xs font-mono whitespace-pre-wrap break-words overflow-x-auto"
      :style="{
        backgroundColor: 'var(--color-neutral-900)',
        color: 'var(--color-neutral-50)',
        borderRadius: 'var(--radius-sm)',
      }"
    >{{ finding.suggestion }}</pre>
    <CodeContextSnippet
      v-if="patch && finding.line !== null"
      :patch="patch"
      :target-line="finding.line"
    />
  </article>
</template>
