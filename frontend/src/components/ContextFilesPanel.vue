<script setup lang="ts">
import { computed } from 'vue'

import Badge from './primitives/Badge.vue'
import Collapsible from './primitives/Collapsible.vue'

const props = defineProps<{ files: string[] }>()

const hasFiles = computed<boolean>(() => props.files.length > 0)
</script>

<template>
  <Collapsible :default-open="true">
    <template #header="{ open }">
      <div
        class="flex items-center justify-between gap-3 px-4 py-3 surface-card"
        :style="{ borderRadius: open ? 'var(--radius-md) var(--radius-md) 0 0' : 'var(--radius-md)' }"
      >
        <div class="flex items-center gap-2">
          <span
            class="text-xs text-muted"
            aria-hidden="true"
          >{{ open ? '▾' : '▸' }}</span>
          <span
            class="text-sm font-semibold"
            :style="{ color: 'var(--color-text)' }"
          >Files that contributed retrieved context</span>
        </div>
        <Badge tone="info">{{ files.length }}</Badge>
      </div>
    </template>
    <template #body>
      <div
        class="surface-card px-4 py-3 text-sm"
        :style="{
          borderTop: 'none',
          borderRadius: '0 0 var(--radius-md) var(--radius-md)',
        }"
      >
        <ul v-if="hasFiles" class="m-0 pl-5 list-disc">
          <li
            v-for="f in files"
            :key="f"
            class="my-1"
          >
            <code class="font-mono text-xs" :style="{ color: 'var(--color-text)' }">{{ f }}</code>
          </li>
        </ul>
        <p v-else class="m-0 text-sm text-muted">
          Retrieval ran but found no chunks above the similarity floor — the review used the diff only.
        </p>
      </div>
    </template>
  </Collapsible>
</template>
