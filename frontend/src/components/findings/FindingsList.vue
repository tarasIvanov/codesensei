<script setup lang="ts">
import { computed } from 'vue'

import Badge from '../primitives/Badge.vue'
import Collapsible from '../primitives/Collapsible.vue'
import FindingRow, { type Finding } from './FindingRow.vue'
import SeverityPill, { type Severity } from './SeverityPill.vue'

const props = defineProps<{
  findings: Finding[]
  patches?: Record<string, string> | null
}>()

const SEVERITY_RANK: Record<Severity, number> = {
  blocker: 0,
  major: 1,
  minor: 2,
  nit: 3,
}

interface FileGroup {
  file: string | null
  findings: Finding[]
  worstSeverity: Severity
  patch: string | null
}

const groups = computed<FileGroup[]>(() => {
  const order: string[] = []
  const buckets = new Map<string, Finding[]>()
  const sentinel: Finding[] = []
  for (const f of props.findings) {
    if (f.file && f.file.length > 0) {
      if (!buckets.has(f.file)) {
        buckets.set(f.file, [])
        order.push(f.file)
      }
      buckets.get(f.file)!.push(f)
    } else {
      sentinel.push(f)
    }
  }
  const out: FileGroup[] = order.map((file) => {
    const findings = [...(buckets.get(file) ?? [])].sort((a, b) => {
      const r = SEVERITY_RANK[a.severity] - SEVERITY_RANK[b.severity]
      if (r !== 0) return r
      const la = a.line ?? Number.MAX_SAFE_INTEGER
      const lb = b.line ?? Number.MAX_SAFE_INTEGER
      return la - lb
    })
    const worst = findings.reduce<Severity>(
      (acc, cur) => (SEVERITY_RANK[cur.severity] < SEVERITY_RANK[acc] ? cur.severity : acc),
      'nit',
    )
    return {
      file,
      findings,
      worstSeverity: worst,
      patch: props.patches?.[file] ?? null,
    }
  })
  if (sentinel.length > 0) {
    const worst = sentinel.reduce<Severity>(
      (acc, cur) => (SEVERITY_RANK[cur.severity] < SEVERITY_RANK[acc] ? cur.severity : acc),
      'nit',
    )
    out.push({
      file: null,
      findings: sentinel,
      worstSeverity: worst,
      patch: null,
    })
  }
  return out
})
</script>

<template>
  <div v-if="groups.length > 0" class="flex flex-col gap-4">
    <Collapsible
      v-for="g in groups"
      :key="g.file ?? '__no_file__'"
      :default-open="true"
    >
      <template #header="{ open }">
        <div
          class="flex items-center justify-between px-4 py-3 surface-card"
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
            >{{ g.file ?? 'Findings without file location' }}</code>
            <Badge>{{ g.findings.length }}</Badge>
          </div>
          <SeverityPill :severity="g.worstSeverity" />
        </div>
      </template>
      <template #body>
        <div
          class="surface-card overflow-hidden"
          :style="{ borderTop: 'none', borderRadius: '0 0 var(--radius-md) var(--radius-md)' }"
        >
          <FindingRow
            v-for="(f, idx) in g.findings"
            :key="`${g.file ?? 'none'}-${idx}`"
            :finding="f"
            :patch="g.patch"
          />
        </div>
      </template>
    </Collapsible>
  </div>
</template>
