<script setup lang="ts">
import Tooltip from './Tooltip.vue'

defineProps<{ text: string }>()
</script>

<template>
  <Tooltip :text="text" multiline>
    <button
      type="button"
      class="focus-ring inline-flex items-center justify-center text-[11px] font-serif italic cursor-help select-none"
      tabindex="0"
      aria-label="Field hint"
      :style="{
        width: '1rem',
        height: '1rem',
        borderRadius: '9999px',
        backgroundColor: 'var(--color-bg-elevated)',
        color: 'var(--color-text-muted)',
        border: '1px solid var(--color-border)',
        lineHeight: '1',
        fontWeight: '600',
      }"
    >i</button>
  </Tooltip>
</template>
