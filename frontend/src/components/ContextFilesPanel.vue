<script setup lang="ts">
import { computed, ref } from 'vue'

const props = defineProps<{ files: string[] }>()

const isOpen = ref(true)

const hasFiles = computed<boolean>(() => props.files.length > 0)
</script>

<template>
  <details :open="isOpen" class="panel" @toggle="isOpen = ($event.target as HTMLDetailsElement).open">
    <summary>
      Files that contributed retrieved context
      <span class="badge">{{ files.length }}</span>
    </summary>
    <ul v-if="hasFiles" class="files">
      <li v-for="f in files" :key="f">
        <code>{{ f }}</code>
      </li>
    </ul>
    <p v-else class="empty">
      Retrieval ran but found no chunks above the similarity floor — the review used the diff only.
    </p>
  </details>
</template>

<style scoped>
.panel {
  margin: 0.6rem 0 0.4rem;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 0.5rem;
  padding: 0.5rem 0.75rem;
  font-size: 0.88rem;
  color: #0f172a;
}
summary {
  cursor: pointer;
  font-weight: 600;
  list-style: revert;
}
.badge {
  margin-left: 0.4rem;
  display: inline-block;
  background: #1d4ed8;
  color: #fff;
  border-radius: 9999px;
  padding: 0 0.5rem;
  font-size: 0.7rem;
  vertical-align: middle;
}
.files {
  margin: 0.4rem 0 0;
  padding-left: 1.1rem;
}
.files li {
  margin: 0.15rem 0;
}
.empty {
  margin: 0.4rem 0 0;
  color: #64748b;
}
code {
  font-family: ui-monospace, Menlo, monospace;
  font-size: 0.82rem;
}
</style>
