<script setup lang="ts">
import { computed } from 'vue'

import { usePatchContext, type SnippetLine } from '../../composables/usePatchContext'

const props = withDefaults(
  defineProps<{ patch: string; targetLine: number; context?: number }>(),
  { context: 3 },
)

const snippet = computed(() => usePatchContext(props.patch, props.targetLine, props.context))

function gutter(line: SnippetLine): string {
  if (line.line === null) return ' '
  return String(line.line)
}

function prefix(line: SnippetLine): string {
  switch (line.side) {
    case 'add':
      return '+'
    case 'remove':
      return '-'
    default:
      return ' '
  }
}

function bgFor(line: SnippetLine): string {
  if (line.is_target) return 'var(--color-warning-bg)'
  if (line.side === 'add') return 'var(--color-success-bg)'
  if (line.side === 'remove') return 'var(--color-danger-bg)'
  return 'transparent'
}
</script>

<template>
  <div
    v-if="snippet"
    class="mt-2 font-mono text-xs overflow-x-auto"
    :style="{
      backgroundColor: 'var(--color-bg-elevated)',
      border: '1px solid var(--color-border)',
      borderRadius: 'var(--radius-sm)',
    }"
    role="region"
    aria-label="Code context"
  >
    <pre
      class="m-0 p-0 whitespace-pre"
    ><span
        v-for="(l, i) in snippet.lines"
        :key="i"
        class="block px-2 py-0.5"
        :style="{ backgroundColor: bgFor(l), color: l.is_target ? 'var(--color-warning-fg)' : 'var(--color-text)' }"
      ><span
          class="inline-block w-10 select-none text-right pr-2"
          :style="{ color: 'var(--color-text-muted)' }"
        >{{ gutter(l) }}</span><span class="inline-block w-3 select-none">{{ prefix(l) }}</span>{{ l.text }}</span></pre>
  </div>
</template>
