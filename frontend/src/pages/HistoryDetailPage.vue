<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import Badge from '../components/primitives/Badge.vue'
import Button from '../components/primitives/Button.vue'
import Card from '../components/primitives/Card.vue'
import Skeleton from '../components/primitives/Skeleton.vue'
import FindingsList from '../components/findings/FindingsList.vue'
import PostToGitHubPanel from '../components/PostToGitHubPanel.vue'
import { useToast } from '../composables/useToast'
import {
  deleteReview,
  getReview,
  type ReviewRunDetail,
} from '../api/reviews'
import type { ReviewResult } from '../api/review'

const props = defineProps<{ runId: string }>()

const router = useRouter()
const toast = useToast()

const run = ref<ReviewRunDetail | null>(null)
const isLoading = ref(true)
const notFound = ref(false)
const isRerunning = ref(false)
const isDeleting = ref(false)

const VERDICT_TONE: Record<string, 'success' | 'danger' | 'info'> = {
  approve: 'success',
  request_changes: 'danger',
  comment: 'info',
}

const reviewResult = computed<ReviewResult | null>(() => {
  if (!run.value) return null
  return {
    verdict: run.value.verdict,
    findings: run.value.findings,
    provider: run.value.provider,
    elapsed_ms: run.value.elapsed_ms,
    context_files: run.value.context_files ?? null,
  }
})

async function load() {
  isLoading.value = true
  notFound.value = false
  try {
    run.value = await getReview(props.runId)
  } catch (err) {
    if (err && typeof err === 'object' && 'category' in err && (err as { category: string }).category === 'invalid_input') {
      notFound.value = true
    } else {
      const message = err instanceof Error ? err.message : String(err)
      toast.push({ category: 'error', message: `Failed to load run: ${message}` })
    }
  } finally {
    isLoading.value = false
  }
}

async function onDelete() {
  if (!run.value || isDeleting.value) return
  isDeleting.value = true
  try {
    await deleteReview(run.value.id)
    toast.push({ category: 'success', message: 'Review run deleted.' })
    router.push('/history')
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err)
    toast.push({ category: 'error', message: `Failed to delete run: ${message}` })
  } finally {
    isDeleting.value = false
  }
}

function onRerun() {
  if (!run.value || isRerunning.value) return
  if (run.value.input_kind !== 'pr_url' || !run.value.pr_url) {
    toast.push({
      category: 'info',
      message: 'Diff-only runs cannot be re-played from history — open /review and paste the diff manually.',
    })
    return
  }
  isRerunning.value = true
  try {
    localStorage.setItem('codesensei.review.prUrl', JSON.stringify(run.value.pr_url))
    localStorage.removeItem('codesensei.review.result')
    localStorage.removeItem('codesensei.review.dismissed')
    router.push({ path: '/review', query: { autorun: '1' } })
  } finally {
    isRerunning.value = false
  }
}

function formatTimestamp(iso: string): string {
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}

function formatTokenLine(r: {
  prompt_tokens?: number | null
  completion_tokens?: number | null
  cost_usd?: number | null
}): string | null {
  const pt = r.prompt_tokens
  const ct = r.completion_tokens
  const cost = r.cost_usd
  const hasTokens = pt !== null && pt !== undefined && ct !== null && ct !== undefined
  if (!hasTokens) {
    if (pt === undefined && ct === undefined && cost == null) return null
    return 'tokens N/A'
  }
  const base = `${pt} in / ${ct} out tokens`
  if (cost === null || cost === undefined) return base
  return `${base} · ~$${cost.toFixed(4)}`
}

const runTokenLine = computed<string | null>(() =>
  run.value ? formatTokenLine(run.value) : null,
)

onMounted(load)
</script>

<template>
  <div class="flex flex-col gap-4">
    <div v-if="isLoading" class="space-y-3">
      <Skeleton class="h-24 w-full" />
      <Skeleton class="h-40 w-full" />
    </div>
    <Card
      v-else-if="notFound"
      title="Run not found"
      subtitle="The review run you're looking for does not exist or was deleted."
    >
      <div class="px-4 pb-4">
        <Button variant="secondary" @click="router.push('/history')">Back to history</Button>
      </div>
    </Card>
    <template v-else-if="run">
      <Card title="Review run" :subtitle="formatTimestamp(run.created_at)">
        <div class="px-4 pb-4 flex items-center gap-2 flex-wrap">
          <Badge :tone="VERDICT_TONE[run.verdict] ?? 'info'">{{ run.verdict }}</Badge>
          <Badge tone="neutral">{{ run.provider }}</Badge>
          <span class="text-xs font-mono" :style="{ color: 'var(--color-text-muted)' }">
            {{ run.elapsed_ms }} ms
          </span>
          <span
            v-if="runTokenLine"
            class="text-xs font-mono"
            :style="{ color: 'var(--color-text-muted)' }"
          >{{ runTokenLine }}</span>
          <span class="text-xs" :style="{ color: 'var(--color-text-muted)' }">
            {{ run.findings.length }} {{ run.findings.length === 1 ? 'finding' : 'findings' }}
          </span>
          <a
            v-if="run.pr_url"
            :href="run.pr_url"
            target="_blank"
            rel="noopener"
            class="text-xs font-mono underline focus-ring"
            :style="{ color: 'var(--color-brand-700)' }"
          >
            {{ run.pr_url }}
          </a>
          <div class="ml-auto flex gap-2">
            <Button variant="secondary" size="sm" :loading="isRerunning" @click="onRerun">Re-run</Button>
            <Button variant="danger" size="sm" :loading="isDeleting" @click="onDelete">Delete this run</Button>
          </div>
        </div>
      </Card>

      <FindingsList :findings="run.findings" />

      <PostToGitHubPanel
        v-if="run.input_kind === 'pr_url' && run.pr_url && reviewResult"
        :review-result="reviewResult"
        :pr-url="run.pr_url"
      />
    </template>
  </div>
</template>
