<script setup lang="ts">
import { computed, ref } from 'vue'

import Button from './primitives/Button.vue'
import { useToast } from '../composables/useToast'
import { createIndex, RepoApiError, type CreateIndexResult } from '../api/repos'

const toast = useToast()
const source = ref('')
const defaultBranch = ref('')
const submitting = ref(false)

const emit = defineEmits<{
  (e: 'submitted', result: CreateIndexResult): void
}>()

const canSubmit = computed<boolean>(() => !submitting.value && source.value.trim().length > 0)

async function submit(): Promise<void> {
  if (!canSubmit.value) return
  submitting.value = true
  try {
    const result = await createIndex({
      source: source.value.trim(),
      default_branch: defaultBranch.value.trim() || null,
    })
    emit('submitted', result)
    source.value = ''
    defaultBranch.value = ''
    toast.push({
      category: 'success',
      message:
        result.mode === 'sync'
          ? `Indexed ${result.chunk_count ?? 0} chunks.`
          : 'Indexing started in the background.',
    })
  } catch (err) {
    const message =
      err instanceof RepoApiError ? err.message : (err as Error).message || 'Unknown error.'
    toast.push({ category: 'error', message })
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <form class="flex flex-col gap-3" @submit.prevent="submit">
    <label class="flex flex-col gap-1 text-sm">
      <span class="text-xs font-semibold uppercase tracking-wide text-muted">Source</span>
      <input
        v-model="source"
        type="text"
        spellcheck="false"
        placeholder="https://github.com/owner/repo  or  /absolute/local/path"
        class="focus-ring px-2 py-1.5 text-sm font-mono"
        :style="{
          backgroundColor: 'var(--color-bg-elevated)',
          border: '1px solid var(--color-border)',
          borderRadius: 'var(--radius-sm)',
          color: 'var(--color-text)',
        }"
      />
    </label>
    <label class="flex flex-col gap-1 text-sm">
      <span class="text-xs font-semibold uppercase tracking-wide text-muted">
        Default branch (optional)
      </span>
      <input
        v-model="defaultBranch"
        type="text"
        spellcheck="false"
        placeholder="main"
        class="focus-ring px-2 py-1.5 text-sm font-mono"
        :style="{
          backgroundColor: 'var(--color-bg-elevated)',
          border: '1px solid var(--color-border)',
          borderRadius: 'var(--radius-sm)',
          color: 'var(--color-text)',
        }"
      />
    </label>
    <div>
      <Button :loading="submitting" :disabled="!canSubmit" type="submit">Index now</Button>
    </div>
  </form>
</template>
