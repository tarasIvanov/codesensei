<script setup lang="ts">
import { computed } from 'vue'

type Tone = 'neutral' | 'success' | 'warning' | 'danger' | 'info'

const props = withDefaults(defineProps<{ tone?: Tone }>(), { tone: 'neutral' })

const palette = computed<{ bg: string; fg: string }>(() => {
  switch (props.tone) {
    case 'success':
      return { bg: 'var(--color-success-bg)', fg: 'var(--color-success-fg)' }
    case 'warning':
      return { bg: 'var(--color-warning-bg)', fg: 'var(--color-warning-fg)' }
    case 'danger':
      return { bg: 'var(--color-danger-bg)', fg: 'var(--color-danger-fg)' }
    case 'info':
      return { bg: 'var(--color-info-bg)', fg: 'var(--color-info-fg)' }
    case 'neutral':
    default:
      return { bg: 'var(--color-neutral-100)', fg: 'var(--color-neutral-700)' }
  }
})
</script>

<template>
  <span
    class="inline-flex items-center px-2 py-0.5 text-xs font-medium"
    :style="{
      backgroundColor: palette.bg,
      color: palette.fg,
      borderRadius: 'var(--radius-sm)',
    }"
  >
    <slot />
  </span>
</template>
