<script setup lang="ts">
import { computed, ref } from 'vue'

import FindingsList, { type Finding } from '../components/FindingsList.vue'
import {
  ReviewApiError,
  runReview,
  type ReviewBody,
  type ReviewResult,
} from '../api/review'

type Mode = 'diff' | 'pr_url'

const mode = ref<Mode>('diff')
const diff = ref('')
const prUrl = ref('')
const isLoading = ref(false)
const result = ref<ReviewResult | null>(null)
const errorMessage = ref('')
const errorRetryable = ref(false)

const canSubmit = computed<boolean>(() => {
  if (isLoading.value) return false
  if (mode.value === 'diff') return diff.value.trim().length > 0
  return prUrl.value.trim().length > 0
})

async function submit(): Promise<void> {
  if (!canSubmit.value) return
  isLoading.value = true
  result.value = null
  errorMessage.value = ''
  errorRetryable.value = false
  try {
    const body: ReviewBody =
      mode.value === 'diff' ? { diff: diff.value } : { pr_url: prUrl.value.trim() }
    result.value = await runReview(body)
  } catch (err) {
    if (err instanceof ReviewApiError) {
      errorMessage.value = err.message
      errorRetryable.value = err.retryable
    } else {
      errorMessage.value = (err as Error).message || 'Unknown error.'
    }
  } finally {
    isLoading.value = false
  }
}

const findings = computed<Finding[]>(() => result.value?.findings ?? [])
</script>

<template>
  <section>
    <h1>Review a pull request</h1>
    <p class="subtitle">
      Paste a unified diff or a GitHub PR URL. The configured LLM provider returns
      structured findings.
    </p>

    <div class="mode-toggle">
      <button
        type="button"
        :class="{ active: mode === 'diff' }"
        @click="mode = 'diff'"
      >
        Paste diff
      </button>
      <button
        type="button"
        :class="{ active: mode === 'pr_url' }"
        @click="mode = 'pr_url'"
      >
        PR URL
      </button>
    </div>

    <textarea
      v-if="mode === 'diff'"
      v-model="diff"
      class="diff-input"
      rows="14"
      spellcheck="false"
      placeholder="diff --git a/... b/..."
    ></textarea>

    <input
      v-else
      v-model="prUrl"
      class="url-input"
      type="text"
      spellcheck="false"
      placeholder="https://github.com/owner/repo/pull/123"
    />

    <div class="actions">
      <button class="submit" :disabled="!canSubmit" @click="submit">
        {{ isLoading ? 'Reviewing…' : 'Review' }}
      </button>
      <span v-if="result" class="meta">
        provider <strong>{{ result.provider }}</strong> · {{ result.elapsed_ms }} ms
      </span>
    </div>

    <p v-if="errorMessage" class="error">
      {{ errorMessage }}
      <button v-if="errorRetryable" class="retry" @click="submit">Try again</button>
    </p>

    <FindingsList
      v-if="result"
      :findings="findings"
      :verdict="result.verdict"
    />
  </section>
</template>

<style scoped>
section {
  font-family: system-ui, -apple-system, Segoe UI, sans-serif;
  color: #0f172a;
}
h1 {
  margin: 0 0 0.25rem;
  font-size: 1.5rem;
}
.subtitle {
  color: #64748b;
  margin: 0 0 1rem;
}
.mode-toggle {
  display: flex;
  gap: 0.5rem;
  margin-bottom: 0.75rem;
}
.mode-toggle button {
  font-family: ui-monospace, Menlo, monospace;
  font-size: 0.8rem;
  background: #f3f4f6;
  border: 1px solid #d1d5db;
  border-radius: 0.4rem;
  padding: 0.3rem 0.7rem;
  cursor: pointer;
}
.mode-toggle button.active {
  background: #0f172a;
  color: #f8fafc;
  border-color: #0f172a;
}
.diff-input {
  width: 100%;
  font-family: ui-monospace, Menlo, monospace;
  font-size: 0.85rem;
  padding: 0.75rem;
  border: 1px solid #d1d5db;
  border-radius: 0.5rem;
  box-sizing: border-box;
  resize: vertical;
  background: #f9fafb;
}
.url-input {
  width: 100%;
  font-family: ui-monospace, Menlo, monospace;
  font-size: 0.9rem;
  padding: 0.65rem 0.75rem;
  border: 1px solid #d1d5db;
  border-radius: 0.5rem;
  box-sizing: border-box;
  background: #f9fafb;
}
.actions {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-top: 0.75rem;
}
.submit {
  background: #2563eb;
  color: #fff;
  border: 0;
  border-radius: 0.4rem;
  padding: 0.5rem 1.1rem;
  font-size: 0.95rem;
  font-weight: 600;
  cursor: pointer;
}
.submit:disabled {
  background: #94a3b8;
  cursor: not-allowed;
}
.meta {
  color: #64748b;
  font-family: ui-monospace, Menlo, monospace;
  font-size: 0.78rem;
}
.error {
  margin-top: 0.9rem;
  padding: 0.6rem 0.85rem;
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: 0.4rem;
  color: #991b1b;
  font-size: 0.9rem;
}
.retry {
  margin-left: 0.6rem;
  background: #991b1b;
  color: #fff;
  border: 0;
  border-radius: 0.3rem;
  padding: 0.2rem 0.6rem;
  font-size: 0.8rem;
  cursor: pointer;
}
</style>
