<script setup lang="ts">
withDefaults(
  defineProps<{
    text: string
    placement?: 'top' | 'bottom'
    multiline?: boolean
  }>(),
  { placement: 'top', multiline: false },
)
</script>

<template>
  <span class="tooltip-wrap relative inline-flex">
    <slot />
    <span
      class="tooltip-pop pointer-events-none absolute z-50 px-2 py-1 text-xs opacity-0 transition-opacity duration-150"
      :class="[
        placement === 'top' ? 'bottom-full mb-1.5' : 'top-full mt-1.5',
        multiline ? 'whitespace-normal leading-snug' : 'whitespace-nowrap',
      ]"
      :style="{
        backgroundColor: 'var(--color-neutral-800)',
        color: 'var(--color-neutral-50)',
        borderRadius: 'var(--radius-sm)',
        boxShadow: 'var(--shadow-md)',
        left: '50%',
        transform: 'translateX(-50%)',
        maxWidth: multiline ? '20rem' : undefined,
        width: multiline ? 'max-content' : undefined,
      }"
      role="tooltip"
    >
      {{ text }}
    </span>
  </span>
</template>

<style scoped>
.tooltip-wrap:hover .tooltip-pop,
.tooltip-wrap:focus-within .tooltip-pop {
  opacity: 1;
}
</style>
