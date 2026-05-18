<script setup lang="ts">
import { computed, onBeforeUnmount, watch } from 'vue'

import { useToast, type Toast } from '../../composables/useToast'

const { items, dismiss } = useToast()

const AUTO_DISMISS_MS = 5000
const timers = new Map<number, ReturnType<typeof setTimeout>>()

function startTimer(toast: Toast): void {
  if (toast.category === 'error') return
  if (timers.has(toast.id)) return
  const handle = setTimeout(() => {
    timers.delete(toast.id)
    dismiss(toast.id)
  }, AUTO_DISMISS_MS)
  timers.set(toast.id, handle)
}

function clearTimer(id: number): void {
  const handle = timers.get(id)
  if (handle) {
    clearTimeout(handle)
    timers.delete(id)
  }
}

watch(
  items,
  (next) => {
    const live = new Set(next.map((t) => t.id))
    for (const id of [...timers.keys()]) {
      if (!live.has(id)) clearTimer(id)
    }
    for (const t of next) {
      startTimer(t)
    }
  },
  { immediate: true, deep: true },
)

onBeforeUnmount(() => {
  for (const id of [...timers.keys()]) clearTimer(id)
})

const reversed = computed(() => [...items.value])

function paletteFor(category: Toast['category']): { bg: string; fg: string; border: string } {
  switch (category) {
    case 'success':
      return {
        bg: 'var(--color-bg-card)',
        fg: 'var(--color-text)',
        border: 'var(--color-success-fg)',
      }
    case 'error':
      return {
        bg: 'var(--color-bg-card)',
        fg: 'var(--color-text)',
        border: 'var(--color-danger-fg)',
      }
    case 'info':
    default:
      return {
        bg: 'var(--color-bg-card)',
        fg: 'var(--color-text)',
        border: 'var(--color-info-fg)',
      }
  }
}
</script>

<template>
  <div
    class="fixed bottom-6 right-6 z-50 flex flex-col gap-2 max-w-sm pointer-events-none"
    aria-live="polite"
  >
    <TransitionGroup name="toast">
      <div
        v-for="t in reversed"
        :key="t.id"
        :role="t.category === 'error' ? 'alert' : 'status'"
        class="pointer-events-auto flex items-start gap-3 p-3 shadow-md"
        :style="{
          backgroundColor: paletteFor(t.category).bg,
          color: paletteFor(t.category).fg,
          borderLeft: `3px solid ${paletteFor(t.category).border}`,
          borderRadius: 'var(--radius-md)',
          boxShadow: 'var(--shadow-md)',
        }"
      >
        <div class="flex-1 text-sm leading-snug">
          {{ t.message }}
          <button
            v-if="t.action"
            type="button"
            class="block mt-1 text-sm underline focus-ring"
            :style="{ color: paletteFor(t.category).border }"
            @click="t.action.onClick()"
          >
            {{ t.action.label }}
          </button>
        </div>
        <button
          type="button"
          class="focus-ring p-1 text-lg leading-none cursor-pointer"
          aria-label="Dismiss"
          :style="{ color: 'var(--color-text-muted)' }"
          @click="dismiss(t.id)"
        >
          ×
        </button>
      </div>
    </TransitionGroup>
  </div>
</template>

<style scoped>
.toast-enter-active,
.toast-leave-active {
  transition:
    opacity 200ms ease,
    transform 200ms ease;
}
.toast-enter-from,
.toast-leave-to {
  opacity: 0;
  transform: translateX(20px);
}
</style>
