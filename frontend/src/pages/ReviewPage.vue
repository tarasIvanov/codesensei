<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import Button from '../components/primitives/Button.vue'
import Card from '../components/primitives/Card.vue'
import Skeleton from '../components/primitives/Skeleton.vue'
import ContextFilesPanel from '../components/ContextFilesPanel.vue'
import FindingsList from '../components/findings/FindingsList.vue'
import type { Finding } from '../components/findings/FindingRow.vue'
import PostToGitHubPanel from '../components/PostToGitHubPanel.vue'
import { useToast } from '../composables/useToast'
import {
  pushToRecentList,
  readList,
  usePersistedRef,
} from '../composables/usePersistedRef'
import { ReviewApiError, runReview, type ReviewResult } from '../api/review'
import { listRepos, type RepoEntry } from '../api/repos'

const toast = useToast()
const route = useRoute()
const router = useRouter()

const PR_URL_KEY = 'codesensei.review.prUrl'
const RESULT_KEY = 'codesensei.review.result'
const RECENT_PR_KEY = 'codesensei.review.recentPrs'
const MANUAL_REPO_KEY = 'codesensei.review.manualRepoId'
const DISMISSED_KEY = 'codesensei.review.dismissed'

const prUrl = usePersistedRef<string>(PR_URL_KEY, '')
const result = usePersistedRef<ReviewResult | null>(RESULT_KEY, null)
const manualRepoOverride = usePersistedRef<string | null>(MANUAL_REPO_KEY, null)
const dismissedFindings = usePersistedRef<number[]>(DISMISSED_KEY, [])

const isLoading = ref(false)
const errorMessage = ref('')
const errorRetryable = ref(false)

const repos = ref<RepoEntry[]>([])
const reposLoaded = ref(false)
const recentPrs = ref<string[]>(readList<string>(RECENT_PR_KEY))
const showRepoPicker = ref(false)

const readyRepos = computed<RepoEntry[]>(() =>
  repos.value.filter((r) => r.status === 'ready'),
)

const canSubmit = computed<boolean>(
  () => !isLoading.value && prUrl.value.trim().length > 0,
)

function parsePrOwnerRepo(url: string): { owner: string; repo: string } | null {
  const m = url
    .trim()
    .match(/github\.com[:/]([^/]+)\/([^/]+?)(?:\.git)?\/pull\/\d+/i)
  if (!m) return null
  return { owner: m[1], repo: m[2] }
}

function repoSourceMatchesPr(source: string, owner: string, repo: string): boolean {
  const target = `${owner}/${repo}`.toLowerCase()
  const normalised = source.replace(/\.git$/i, '').toLowerCase()
  return normalised.endsWith(`/${target}`) || normalised === target
}

const autoDetectedRepoId = computed<string | null>(() => {
  const parsed = parsePrOwnerRepo(prUrl.value)
  if (!parsed) return null
  const hit = readyRepos.value.find((r) =>
    repoSourceMatchesPr(r.source, parsed.owner, parsed.repo),
  )
  return hit?.repo_id ?? null
})

const effectiveRepoId = computed<string | null>(() => {
  if (manualRepoOverride.value !== null) return manualRepoOverride.value || null
  return autoDetectedRepoId.value
})

const effectiveRepo = computed<RepoEntry | null>(() => {
  if (!effectiveRepoId.value) return null
  return readyRepos.value.find((r) => r.repo_id === effectiveRepoId.value) ?? null
})

async function refreshRepos(): Promise<void> {
  try {
    repos.value = await listRepos()
  } catch {
    repos.value = []
  } finally {
    reposLoaded.value = true
  }
}

onMounted(async () => {
  await refreshRepos()
  if (route.query.autorun === '1' && prUrl.value.trim().length > 0) {
    router.replace({ path: '/review', query: {} })
    void submit()
  }
})

watch(prUrl, (v) => {
  if (manualRepoOverride.value !== null) {
    const parsed = parsePrOwnerRepo(v)
    if (!parsed) manualRepoOverride.value = null
  }
})

async function submit(): Promise<void> {
  if (!canSubmit.value) return
  const trimmed = prUrl.value.trim()
  isLoading.value = true
  result.value = null
  dismissedFindings.value = []
  errorMessage.value = ''
  errorRetryable.value = false
  try {
    result.value = await runReview({
      pr_url: trimmed,
      repo_id: effectiveRepoId.value,
    })
    recentPrs.value = pushToRecentList<string>(RECENT_PR_KEY, trimmed, 10)
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

function clearResult(): void {
  result.value = null
  dismissedFindings.value = []
  errorMessage.value = ''
  errorRetryable.value = false
}

function onDismiss(index: number): void {
  if (!dismissedFindings.value.includes(index)) {
    dismissedFindings.value = [...dismissedFindings.value, index]
  }
}

function onRestore(index: number): void {
  dismissedFindings.value = dismissedFindings.value.filter((i) => i !== index)
}

const keptResult = computed<ReviewResult | null>(() => {
  if (!result.value) return null
  if (dismissedFindings.value.length === 0) return result.value
  const dismissed = new Set(dismissedFindings.value)
  return {
    ...result.value,
    findings: (result.value.findings ?? []).filter((_, i) => !dismissed.has(i)),
  }
})

function clearPr(): void {
  prUrl.value = ''
  clearResult()
  manualRepoOverride.value = null
}

function pickRecent(url: string): void {
  prUrl.value = url
}

function resetManualRepo(): void {
  manualRepoOverride.value = null
  showRepoPicker.value = false
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
  <Card
    title="Review a pull request"
    subtitle="Paste a GitHub PR URL. The configured LLM provider returns structured findings. If an indexed repository matches the PR, RAG context is added automatically."
  >
    <div class="flex flex-col gap-3">
      <div class="flex flex-col gap-1">
        <label
          for="pr-url"
          class="text-xs font-semibold uppercase tracking-wide"
          :style="{ color: 'var(--color-text-muted)' }"
        >Pull request URL</label>
        <div class="flex items-stretch gap-2">
          <input
            id="pr-url"
            v-model="prUrl"
            class="focus-ring flex-1 px-3 py-2 text-sm font-mono"
            type="text"
            list="recent-pr-urls"
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
          <datalist id="recent-pr-urls">
            <option v-for="url in recentPrs" :key="url" :value="url" />
          </datalist>
          <Button
            v-if="prUrl"
            variant="ghost"
            size="sm"
            type="button"
            aria-label="Clear PR URL"
            @click="clearPr"
          >Clear</Button>
        </div>
        <div
          v-if="recentPrs.length > 0"
          class="flex flex-wrap items-center gap-1 mt-1 text-xs"
          :style="{ color: 'var(--color-text-muted)' }"
        >
          <span>Recent:</span>
          <button
            v-for="url in recentPrs.slice(0, 5)"
            :key="url"
            type="button"
            class="focus-ring px-1.5 py-0.5 font-mono underline-offset-2 hover:underline"
            :style="{ color: 'var(--color-brand-700)' }"
            @click="pickRecent(url)"
          >{{ url.replace(/^https?:\/\/(www\.)?github\.com\//, '') }}</button>
        </div>
      </div>

      <div
        v-if="effectiveRepo"
        class="text-xs flex flex-wrap items-center gap-2"
        :style="{ color: 'var(--color-text-muted)' }"
      >
        <span
          v-if="manualRepoOverride === null"
          :style="{ color: 'var(--color-success-fg)' }"
        >Auto-detected RAG context:</span>
        <span v-else>Manual RAG context:</span>
        <code
          class="font-mono"
          :style="{ color: 'var(--color-text)' }"
        >{{ effectiveRepo.source }}</code>
        <span>· {{ effectiveRepo.chunk_count }} chunks</span>
        <button
          type="button"
          class="focus-ring underline-offset-2 hover:underline"
          :style="{ color: 'var(--color-brand-700)' }"
          @click="showRepoPicker = !showRepoPicker"
        >Change</button>
      </div>
      <div
        v-else-if="prUrl && parsePrOwnerRepo(prUrl) && reposLoaded && readyRepos.length > 0"
        class="text-xs flex flex-wrap items-center gap-2"
        :style="{ color: 'var(--color-text-muted)' }"
      >
        <span>No indexed repository matches this PR.</span>
        <button
          type="button"
          class="focus-ring underline-offset-2 hover:underline"
          :style="{ color: 'var(--color-brand-700)' }"
          @click="showRepoPicker = !showRepoPicker"
        >Pick manually</button>
      </div>
      <p
        v-else-if="reposLoaded && readyRepos.length === 0"
        class="text-xs m-0"
        :style="{ color: 'var(--color-text-muted)' }"
      >
        Tip: index a repository on the
        <RouterLink to="/repos" class="underline">Repositories</RouterLink>
        page to enable RAG context for reviews.
      </p>

      <div v-if="showRepoPicker" class="flex items-center gap-2">
        <select
          v-model="manualRepoOverride"
          class="focus-ring flex-1 px-2 py-1.5 text-sm font-mono"
          :style="{
            backgroundColor: 'var(--color-bg-elevated)',
            border: '1px solid var(--color-border)',
            borderRadius: 'var(--radius-sm)',
            color: 'var(--color-text)',
          }"
        >
          <option :value="null">(auto-detect)</option>
          <option :value="''">(none — no RAG context)</option>
          <option v-for="r in readyRepos" :key="r.repo_id" :value="r.repo_id">
            {{ r.source }} · {{ r.chunk_count }} chunks
          </option>
        </select>
        <Button variant="ghost" size="sm" type="button" @click="resetManualRepo">
          Reset
        </Button>
      </div>

      <div class="flex items-center gap-3">
        <Button :loading="isLoading" :disabled="!canSubmit" @click="submit">
          {{ isLoading ? 'Reviewing…' : 'Review' }}
        </Button>
        <Button
          v-if="result"
          variant="ghost"
          size="sm"
          type="button"
          @click="clearResult"
        >Clear result</Button>
        <span
          v-if="result"
          class="text-xs font-mono"
          :style="{ color: 'var(--color-text-muted)' }"
        >
          provider
          <strong :style="{ color: 'var(--color-text)' }">{{ result.provider }}</strong>
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
      <p
        class="m-0 mt-1 text-sm"
        :style="{ color: 'var(--color-text-muted)' }"
      >
        Verdict: <strong :style="{ color: verdictTone.color }">{{ verdictTone.label }}</strong>
      </p>
    </div>
  </Card>

  <FindingsList
    v-if="result && findings.length > 0"
    :findings="findings"
    :dismissed="dismissedFindings"
    dismissible
    @dismiss="onDismiss"
    @restore="onRestore"
  />

  <PostToGitHubPanel
    v-if="keptResult && prUrl.trim()"
    :review-result="keptResult"
    :pr-url="prUrl.trim()"
  />
</template>
