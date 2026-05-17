<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import FindingsList, { type Finding } from '../components/FindingsList.vue'
import ContextFilesPanel from '../components/ContextFilesPanel.vue'
import { ReviewApiError, runReview, type ReviewResult } from '../api/review'
import { listRepos, type RepoEntry } from '../api/repos'

const prUrl = ref('')
const isLoading = ref(false)
const result = ref<ReviewResult | null>(null)
const errorMessage = ref('')
const errorRetryable = ref(false)

const repos = ref<RepoEntry[]>([])
const selectedRepoId = ref<string>('')
const reposLoaded = ref(false)

const readyRepos = computed<RepoEntry[]>(() =>
  repos.value.filter((r) => r.status === 'ready'),
)

const canSubmit = computed<boolean>(
  () => !isLoading.value && prUrl.value.trim().length > 0,
)

async function refreshRepos(): Promise<void> {
  try {
    repos.value = await listRepos()
  } catch {
    repos.value = []
  } finally {
    reposLoaded.value = true
  }
}

onMounted(refreshRepos)

async function submit(): Promise<void> {
  if (!canSubmit.value) return
  isLoading.value = true
  result.value = null
  errorMessage.value = ''
  errorRetryable.value = false
  try {
    result.value = await runReview({
      pr_url: prUrl.value.trim(),
      repo_id: selectedRepoId.value || null,
    })
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
      Optionally pick an indexed repository — its top-K semantically nearest chunks will be added as context.
    </p>

    <div v-if="readyRepos.length > 0" class="context-row">
      <label for="repo-select" class="ctx-label">Use context from repository:</label>
      <select id="repo-select" v-model="selectedRepoId" class="repo-select">
        <option value="">(none)</option>
        <option v-for="r in readyRepos" :key="r.repo_id" :value="r.repo_id">
          {{ r.source }}  ·  {{ r.chunk_count }} chunks
        </option>
      </select>
    </div>
    <p v-else-if="reposLoaded" class="hint">
      Tip: index a repository on the <RouterLink to="/repos">Repositories</RouterLink> page to enable RAG context for reviews.
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

    <ContextFilesPanel
      v-if="result && result.context_files !== undefined && result.context_files !== null"
      :files="result.context_files"
    />

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
.context-row {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  margin-bottom: 0.6rem;
}
.ctx-label {
  font-size: 0.85rem;
  color: #475569;
}
.repo-select {
  flex: 1;
  font-family: ui-monospace, Menlo, monospace;
  font-size: 0.85rem;
  padding: 0.35rem 0.5rem;
  border-radius: 0.4rem;
  border: 1px solid #cbd5e1;
  background: #f9fafb;
}
.hint {
  color: #64748b;
  font-size: 0.85rem;
  margin: 0 0 0.6rem;
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
