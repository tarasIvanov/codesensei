<script setup lang="ts">
withDefaults(
  defineProps<{
    padded?: boolean
    flush?: boolean
    title?: string
    subtitle?: string
  }>(),
  { padded: true, flush: false },
)
</script>

<template>
  <section
    class="surface-card"
    :style="{
      backgroundColor: 'var(--color-bg-card)',
      borderColor: 'var(--color-border)',
      borderRadius: 'var(--radius-md)',
    }"
  >
    <header
      v-if="$slots.header || title || subtitle"
      class="px-6 py-4 border-b"
      :style="{ borderColor: 'var(--color-border)' }"
    >
      <slot name="header">
        <h2 v-if="title" class="text-lg font-semibold m-0" :style="{ color: 'var(--color-text)' }">
          {{ title }}
        </h2>
        <p v-if="subtitle" class="text-sm m-0 mt-1 text-muted">{{ subtitle }}</p>
      </slot>
    </header>
    <div :class="flush ? 'p-0' : padded ? 'p-6' : ''">
      <slot />
    </div>
    <footer
      v-if="$slots.footer"
      class="px-6 py-3 border-t"
      :style="{ borderColor: 'var(--color-border)' }"
    >
      <slot name="footer" />
    </footer>
  </section>
</template>
