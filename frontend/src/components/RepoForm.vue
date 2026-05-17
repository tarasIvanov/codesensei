<script setup lang="ts">
import { computed, ref } from 'vue'

import { createIndex, RepoApiError, type CreateIndexResult } from '../api/repos'

const source = ref('')
const defaultBranch = ref('')
const submitting = ref(false)
const errorMessage = ref('')

const emit = defineEmits<{
  (e: 'submitted', result: CreateIndexResult): void
}>()

const canSubmit = computed<boolean>(() => !submitting.value && source.value.trim().length > 0)

async function submit(): Promise<void> {
  if (!canSubmit.value) return
  submitting.value = true
  errorMessage.value = ''
  try {
    const result = await createIndex({
      source: source.value.trim(),
      default_branch: defaultBranch.value.trim() || null,
    })
    emit('submitted', result)
    source.value = ''
    defaultBranch.value = ''
  } catch (err) {
    if (err instanceof RepoApiError) {
      errorMessage.value = err.message
    } else {
      errorMessage.value = (err as Error).message || 'Unknown error.'
    }
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <form class="form" @submit.prevent="submit">
    <label class="row">
      <span class="label">Source</span>
      <input
        v-model="source"
        type="text"
        spellcheck="false"
        placeholder="https://github.com/owner/repo  or  /absolute/local/path"
      />
    </label>
    <label class="row">
      <span class="label">Default branch (optional)</span>
      <input v-model="defaultBranch" type="text" spellcheck="false" placeholder="main" />
    </label>
    <div class="actions">
      <button type="submit" :disabled="!canSubmit">
        {{ submitting ? 'Submitting…' : 'Index now' }}
      </button>
    </div>
    <p v-if="errorMessage" class="error">{{ errorMessage }}</p>
  </form>
</template>

<style scoped>
.form {
  display: flex;
  flex-direction: column;
  gap: 0.55rem;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 0.5rem;
  padding: 0.85rem;
}
.row {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}
.label {
  font-size: 0.78rem;
  font-weight: 600;
  color: #475569;
}
input[type='text'] {
  font-family: ui-monospace, Menlo, monospace;
  font-size: 0.85rem;
  padding: 0.45rem 0.6rem;
  border: 1px solid #d1d5db;
  border-radius: 0.4rem;
  background: #ffffff;
}
.actions {
  display: flex;
  justify-content: flex-end;
}
button {
  background: #2563eb;
  color: #ffffff;
  border: 0;
  border-radius: 0.4rem;
  padding: 0.45rem 1rem;
  font-size: 0.9rem;
  font-weight: 600;
  cursor: pointer;
}
button:disabled {
  background: #94a3b8;
  cursor: not-allowed;
}
.error {
  margin: 0.3rem 0 0;
  padding: 0.45rem 0.6rem;
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: 0.4rem;
  color: #991b1b;
  font-size: 0.85rem;
}
</style>
