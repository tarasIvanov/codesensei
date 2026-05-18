<script setup lang="ts">
import { computed } from 'vue'

import Tooltip from './Tooltip.vue'

const props = defineProps<{
  state: 'ok' | 'degraded' | 'error'
  label: string
  error?: string | null
}>()

const dotColor = computed(() => {
  switch (props.state) {
    case 'ok':
      return 'var(--color-success-fg)'
    case 'degraded':
      return 'var(--color-warning-fg)'
    case 'error':
    default:
      return 'var(--color-danger-fg)'
  }
})

const tooltipText = computed(() => {
  const parts = [props.label, props.state.toUpperCase()]
  if (props.error) parts.push(props.error)
  return parts.join(' · ')
})
</script>

<template>
  <Tooltip :text="tooltipText">
    <span
      class="focus-ring inline-flex items-center gap-2 cursor-default"
      tabindex="0"
      :aria-label="`${label}: ${state}`"
    >
      <span
        class="inline-block"
        :style="{
          width: '10px',
          height: '10px',
          borderRadius: '50%',
          backgroundColor: dotColor,
        }"
        aria-hidden="true"
      />
      <span class="text-sm" :style="{ color: 'var(--color-text)' }">{{ label }}</span>
    </span>
  </Tooltip>
</template>
