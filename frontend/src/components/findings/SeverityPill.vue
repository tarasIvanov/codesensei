<script setup lang="ts">
import { computed } from 'vue'

export type Severity = 'blocker' | 'major' | 'minor' | 'nit'

const props = defineProps<{ severity: Severity }>()

const palette = computed(() => ({
  bg: `var(--color-severity-${props.severity}-bg)`,
  fg: `var(--color-severity-${props.severity}-fg)`,
}))
</script>

<template>
  <span
    class="inline-flex items-center px-2 py-0.5 text-xs font-medium uppercase tracking-wide rounded-full"
    :style="{ backgroundColor: palette.bg, color: palette.fg }"
  >
    {{ severity }}
  </span>
</template>
