<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink, RouterView } from 'vue-router'

import Button from './primitives/Button.vue'
import ToastHost from './primitives/ToastHost.vue'
import { useTheme } from '../composables/useTheme'

const theme = useTheme()

const NAV = [
  { to: '/status', label: 'Status' },
  { to: '/review', label: 'Review' },
  { to: '/repos', label: 'Repos' },
  { to: '/history', label: 'History' },
  { to: '/settings', label: 'Settings' },
]

const themeLabel = computed(() => {
  switch (theme.choice.value) {
    case 'light':
      return 'Light theme'
    case 'dark':
      return 'Dark theme'
    case 'system':
    default:
      return 'Follow system theme'
  }
})
</script>

<template>
  <div class="min-h-screen flex flex-col" :style="{ backgroundColor: 'var(--color-bg-page)' }">
    <header
      class="sticky top-0 z-40 border-b"
      :style="{
        backgroundColor: 'var(--color-bg-card)',
        borderColor: 'var(--color-border)',
      }"
    >
      <div class="max-w-5xl mx-auto px-6 py-3 flex items-center gap-6">
        <RouterLink
          to="/"
          class="focus-ring font-semibold text-lg tracking-tight"
          :style="{ color: 'var(--color-text)' }"
        >
          CodeSensei
        </RouterLink>
        <nav class="flex items-center gap-1 flex-1">
          <RouterLink
            v-for="link in NAV"
            :key="link.to"
            :to="link.to"
            class="focus-ring px-3 py-1.5 text-sm transition-colors duration-150"
            :style="{ borderRadius: 'var(--radius-sm)' }"
            active-class="app-nav-active"
          >
            {{ link.label }}
          </RouterLink>
        </nav>
        <Button
          variant="ghost"
          size="sm"
          :aria-label="themeLabel"
          @click="theme.cycle()"
        >
          <span class="text-base" aria-hidden="true">
            <template v-if="theme.choice.value === 'light'">☀</template>
            <template v-else-if="theme.choice.value === 'dark'">☾</template>
            <template v-else>◐</template>
          </span>
          <span class="hidden sm:inline text-xs">
            {{
              theme.choice.value === 'system'
                ? 'System'
                : theme.choice.value === 'light'
                  ? 'Light'
                  : 'Dark'
            }}
          </span>
        </Button>
      </div>
    </header>
    <main class="flex-1 max-w-5xl w-full mx-auto px-6 py-6 flex flex-col gap-6">
      <RouterView />
    </main>
    <ToastHost />
  </div>
</template>

<style scoped>
.app-nav-active {
  background-color: var(--color-brand-50);
  color: var(--color-brand-700);
  font-weight: 600;
}
:global(html[data-theme='dark']) .app-nav-active {
  background-color: var(--color-brand-900);
  color: var(--color-brand-100);
}
</style>
