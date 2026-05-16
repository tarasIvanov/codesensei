<script setup lang="ts">
type Severity = 'blocker' | 'major' | 'minor' | 'nit'

const props = defineProps<{ severity: Severity }>()

const PALETTE: Record<Severity, string> = {
  blocker: '#dc2626',
  major: '#ea580c',
  minor: '#ca8a04',
  nit: '#6b7280',
}
</script>

<template>
  <span class="badge" :style="{ background: PALETTE[props.severity] }">
    {{ props.severity }}
  </span>
</template>

<style scoped>
.badge {
  display: inline-block;
  padding: 0.1rem 0.5rem;
  border-radius: 999px;
  color: #fff;
  font-size: 0.7rem;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  font-family: ui-monospace, Menlo, monospace;
}
</style>
