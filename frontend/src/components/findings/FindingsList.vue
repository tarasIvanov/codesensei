<script setup lang="ts">
import { computed } from 'vue'

import Badge from '../primitives/Badge.vue'
import Collapsible from '../primitives/Collapsible.vue'
import FindingRow, { type Finding } from './FindingRow.vue'
import SeverityPill, { type Severity } from './SeverityPill.vue'

const props = withDefaults(
  defineProps<{
    findings: Finding[]
    patches?: Record<string, string> | null
    dismissed?: number[]
    dismissible?: boolean
  }>(),
  { dismissed: () => [], dismissible: false },
)

const emit = defineEmits<{
  (e: 'dismiss', index: number): void
  (e: 'restore', index: number): void
}>()

const dismissedSet = computed(() => new Set(props.dismissed))

const SEVERITY_RANK: Record<Severity, number> = {
  blocker: 0,
  major: 1,
  minor: 2,
  nit: 3,
}

interface IndexedFinding {
  finding: Finding
  index: number
}

interface FileGroup {
  file: string | null
  entries: IndexedFinding[]
  worstSeverity: Severity
  patch: string | null
}

const groups = computed<FileGroup[]>(() => {
  const order: string[] = []
  const buckets = new Map<string, IndexedFinding[]>()
  const sentinel: IndexedFinding[] = []
  props.findings.forEach((f, index) => {
    const entry: IndexedFinding = { finding: f, index }
    if (f.file && f.file.length > 0) {
      if (!buckets.has(f.file)) {
        buckets.set(f.file, [])
        order.push(f.file)
      }
      buckets.get(f.file)!.push(entry)
    } else {
      sentinel.push(entry)
    }
  })
  const out: FileGroup[] = order.map((file) => {
    const entries = [...(buckets.get(file) ?? [])].sort((a, b) => {
      const r = SEVERITY_RANK[a.finding.severity] - SEVERITY_RANK[b.finding.severity]
      if (r !== 0) return r
      const la = a.finding.line ?? Number.MAX_SAFE_INTEGER
      const lb = b.finding.line ?? Number.MAX_SAFE_INTEGER
      return la - lb
    })
    const worst = entries.reduce<Severity>(
      (acc, cur) => (SEVERITY_RANK[cur.finding.severity] < SEVERITY_RANK[acc] ? cur.finding.severity : acc),
      'nit',
    )
    return {
      file,
      entries,
      worstSeverity: worst,
      patch: props.patches?.[file] ?? null,
    }
  })
  if (sentinel.length > 0) {
    const worst = sentinel.reduce<Severity>(
      (acc, cur) => (SEVERITY_RANK[cur.finding.severity] < SEVERITY_RANK[acc] ? cur.finding.severity : acc),
      'nit',
    )
    out.push({
      file: null,
      entries: sentinel,
      worstSeverity: worst,
      patch: null,
    })
  }
  return out
})

const totalFindings = computed(() => props.findings.length)
const dismissedCount = computed(() => dismissedSet.value.size)
const keptCount = computed(() => totalFindings.value - dismissedCount.value)
</script>

<template>
  <div v-if="groups.length > 0" class="flex flex-col gap-4">
    <div
      v-if="dismissible && totalFindings > 0"
      class="flex items-center gap-3 text-xs"
      :style="{ color: 'var(--color-text-muted)' }"
    >
      <span>
        Posting <strong :style="{ color: 'var(--color-text)' }">{{ keptCount }}</strong>
        of {{ totalFindings }} findings
        <span v-if="dismissedCount > 0">· {{ dismissedCount }} dismissed</span>
      </span>
    </div>
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
            <Badge>{{ g.entries.length }}</Badge>
          </div>
          <SeverityPill :severity="g.worstSeverity" />
        </div>
      </template>
      <template #body>
        <div
          class="surface-card"
          :style="{ borderTop: 'none', borderRadius: '0 0 var(--radius-md) var(--radius-md)' }"
        >
          <FindingRow
            v-for="entry in g.entries"
            :key="`${g.file ?? 'none'}-${entry.index}`"
            :finding="entry.finding"
            :patch="g.patch"
            :dismissible="dismissible"
            :dismissed="dismissedSet.has(entry.index)"
            @dismiss="emit('dismiss', entry.index)"
            @restore="emit('restore', entry.index)"
          />
        </div>
      </template>
    </Collapsible>
  </div>
</template>
