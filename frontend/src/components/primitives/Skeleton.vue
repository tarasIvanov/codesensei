<script setup lang="ts">
withDefaults(defineProps<{ lines?: number }>(), { lines: 1 })
</script>

<template>
  <div class="flex flex-col gap-2" aria-hidden="true">
    <span
      v-for="i in lines"
      :key="i"
      class="block h-3 animate-pulse"
      :style="{
        backgroundColor: 'var(--color-neutral-200)',
        borderRadius: 'var(--radius-sm)',
        width: i === lines && lines > 1 ? '60%' : '100%',
      }"
    />
  </div>
</template>
