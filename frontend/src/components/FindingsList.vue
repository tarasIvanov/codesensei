<script setup lang="ts">
import { computed } from 'vue'

import SeverityBadge from './SeverityBadge.vue'

export interface Finding {
  file: string
  line: number | null
  severity: 'blocker' | 'major' | 'minor' | 'nit'
  message: string
  suggestion?: string | null
}

const props = defineProps<{
  findings: Finding[]
  verdict: 'approve' | 'request_changes' | 'comment'
}>()

const grouped = computed(() => {
  const map = new Map<string, Finding[]>()
  for (const f of props.findings) {
    if (!map.has(f.file)) map.set(f.file, [])
    map.get(f.file)!.push(f)
  }
  return [...map.entries()].map(([file, items]) => ({ file, items }))
})
</script>

<template>
  <div class="findings">
    <p v-if="findings.length === 0" class="empty">
      <strong>No issues found.</strong> The reviewer marked this diff as
      <code>{{ verdict }}</code>.
    </p>
    <div v-for="group in grouped" :key="group.file" class="file-group">
      <h3>{{ group.file }}</h3>
      <article v-for="(f, idx) in group.items" :key="idx" class="finding">
        <header>
          <SeverityBadge :severity="f.severity" />
          <span v-if="f.line !== null" class="line">line {{ f.line }}</span>
          <span v-else class="line">file-level</span>
        </header>
        <p class="message">{{ f.message }}</p>
        <pre v-if="f.suggestion" class="suggestion"><code>{{ f.suggestion }}</code></pre>
      </article>
    </div>
  </div>
</template>

<style scoped>
.findings {
  margin-top: 1.5rem;
}
.empty {
  padding: 1rem;
  background: #f0fdf4;
  border: 1px solid #bbf7d0;
  border-radius: 0.5rem;
  color: #166534;
}
.empty code {
  background: #dcfce7;
  padding: 0.05rem 0.3rem;
  border-radius: 0.25rem;
}
.file-group {
  margin-bottom: 1.25rem;
}
.file-group h3 {
  margin: 0 0 0.5rem;
  font-family: ui-monospace, Menlo, monospace;
  font-size: 0.95rem;
  color: #1f2937;
  border-bottom: 1px solid #e5e7eb;
  padding-bottom: 0.25rem;
}
.finding {
  background: #f9fafb;
  border: 1px solid #e5e7eb;
  border-radius: 0.5rem;
  padding: 0.6rem 0.85rem;
  margin-bottom: 0.5rem;
}
.finding header {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  margin-bottom: 0.35rem;
}
.line {
  color: #475569;
  font-family: ui-monospace, Menlo, monospace;
  font-size: 0.75rem;
}
.message {
  margin: 0;
  font-size: 0.92rem;
  line-height: 1.5;
}
.suggestion {
  margin: 0.5rem 0 0;
  padding: 0.5rem 0.75rem;
  background: #0f172a;
  color: #f8fafc;
  border-radius: 0.4rem;
  overflow-x: auto;
  font-size: 0.85rem;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
