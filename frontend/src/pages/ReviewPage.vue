<script setup lang="ts">
import { computed, ref } from 'vue'

import FindingsList, { type Finding } from '../components/FindingsList.vue'
import { ReviewApiError, runReview, type ReviewResult } from '../api/review'

const prUrl = ref('')
const isLoading = ref(false)
const result = ref<ReviewResult | null>(null)
const errorMessage = ref('')
const errorRetryable = ref(false)

const canSubmit = computed<boolean>(
  () => !isLoading.value && prUrl.value.trim().length > 0,
)

async function submit(): Promise<void> {
  if (!canSubmit.value) return
  isLoading.value = true
  result.value = null
  errorMessage.value = ''
  errorRetryable.value = false
  try {
    result.value = await runReview({ pr_url: prUrl.value.trim() })
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
      Paste a GitHub PR URL. The configured LLM provider returns structured findings.
    </p>

    <input
      v-model="prUrl"
      class="url-input"
      type="text"
      spellcheck="false"
      placeholder="https://github.com/owner/repo/pull/123"
      @keydown.enter="submit"
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
