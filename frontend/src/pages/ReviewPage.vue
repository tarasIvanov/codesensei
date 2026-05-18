<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import Button from '../components/primitives/Button.vue'
import Card from '../components/primitives/Card.vue'
import Skeleton from '../components/primitives/Skeleton.vue'
import ContextFilesPanel from '../components/ContextFilesPanel.vue'
import FindingsList from '../components/findings/FindingsList.vue'
import type { Finding } from '../components/findings/FindingRow.vue'
import PostToGitHubPanel from '../components/PostToGitHubPanel.vue'
import { useToast } from '../composables/useToast'
import { ReviewApiError, runReview, type ReviewResult } from '../api/review'
import { listRepos, type RepoEntry } from '../api/repos'

const toast = useToast()

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
    toast.push({ category: 'error', message: errorMessage.value })
  } finally {
    isLoading.value = false
  }
}

const findings = computed<Finding[]>(
  () => (result.value?.findings ?? []) as Finding[],
)

const hasNoFindings = computed(
  () => result.value !== null && findings.value.length === 0,
)

const verdictTone = computed(() => {
  if (!result.value) return null
  switch (result.value.verdict) {
    case 'approve':
      return { label: 'Approved', icon: '✓', color: 'var(--color-success-fg)' }
    case 'request_changes':
      return { label: 'Request changes', icon: '!', color: 'var(--color-danger-fg)' }
    case 'comment':
    default:
      return { label: 'Comment', icon: '○', color: 'var(--color-info-fg)' }
  }
})
</script>

<template>
  <Card title="Review a pull request" subtitle="Paste a GitHub PR URL. The configured LLM provider returns structured findings. Optionally pick an indexed repository — its top-K semantically nearest chunks will be added as context.">
    <div class="flex flex-col gap-3">
      <div v-if="readyRepos.length > 0" class="flex items-center gap-2">
        <label
          for="repo-select"
          class="text-sm text-muted whitespace-nowrap"
        >Use context from repository:</label>
        <select
          id="repo-select"
          v-model="selectedRepoId"
          class="focus-ring flex-1 px-2 py-1.5 text-sm font-mono"
          :style="{
            backgroundColor: 'var(--color-bg-elevated)',
            border: '1px solid var(--color-border)',
            borderRadius: 'var(--radius-sm)',
            color: 'var(--color-text)',
          }"
        >
          <option value="">(none)</option>
          <option v-for="r in readyRepos" :key="r.repo_id" :value="r.repo_id">
            {{ r.source }} · {{ r.chunk_count }} chunks
          </option>
        </select>
      </div>
      <p v-else-if="reposLoaded" class="text-sm text-muted m-0">
        Tip: index a repository on the
        <RouterLink to="/repos" class="underline">Repositories</RouterLink>
        page to enable RAG context for reviews.
      </p>

      <input
        v-model="prUrl"
        class="focus-ring w-full px-3 py-2 text-sm font-mono"
        type="text"
        spellcheck="false"
        placeholder="https://github.com/owner/repo/pull/123"
        :style="{
          backgroundColor: 'var(--color-bg-elevated)',
          border: '1px solid var(--color-border)',
          borderRadius: 'var(--radius-sm)',
          color: 'var(--color-text)',
        }"
        @keydown.enter="submit"
      />

      <div class="flex items-center gap-3">
        <Button :loading="isLoading" :disabled="!canSubmit" @click="submit">
          {{ isLoading ? 'Reviewing…' : 'Review' }}
        </Button>
        <span v-if="result" class="text-xs text-muted font-mono">
          provider <strong :style="{ color: 'var(--color-text)' }">{{ result.provider }}</strong>
          · {{ result.elapsed_ms }} ms
        </span>
      </div>

      <div v-if="errorMessage && !isLoading" class="flex items-center gap-3 mt-1">
        <span
          class="text-sm"
          :style="{ color: 'var(--color-danger-fg)' }"
        >{{ errorMessage }}</span>
        <Button v-if="errorRetryable" variant="secondary" size="sm" @click="submit">
          Try again
        </Button>
      </div>
    </div>
  </Card>

  <Card v-if="isLoading" title="Findings" subtitle="Generating review…">
    <div class="flex flex-col gap-4" aria-label="Loading findings">
      <div>
        <Skeleton :lines="1" class="mb-2" />
        <Skeleton :lines="3" />
      </div>
      <div>
        <Skeleton :lines="1" class="mb-2" />
        <Skeleton :lines="2" />
      </div>
    </div>
  </Card>

  <ContextFilesPanel
    v-if="result && result.context_files !== undefined && result.context_files !== null"
    :files="result.context_files"
  />

  <Card v-if="hasNoFindings && verdictTone" flush>
    <div class="flex flex-col items-center text-center px-6 py-10">
      <span
        class="text-3xl mb-2"
        aria-hidden="true"
        :style="{ color: verdictTone.color }"
      >{{ verdictTone.icon }}</span>
      <p
        class="m-0 text-base font-semibold"
        :style="{ color: 'var(--color-text)' }"
      >No findings</p>
      <p class="m-0 mt-1 text-sm text-muted">
        Verdict: <strong :style="{ color: verdictTone.color }">{{ verdictTone.label }}</strong>
      </p>
    </div>
  </Card>

  <FindingsList v-if="result && findings.length > 0" :findings="findings" />

  <PostToGitHubPanel
    v-if="result && prUrl.trim()"
    :review-result="result"
    :pr-url="prUrl.trim()"
  />
</template>
