<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'

import Button from './primitives/Button.vue'
import Card from './primitives/Card.vue'
import { useToast } from '../composables/useToast'
import {
  postReview,
  PostReviewError,
  type GitHubEvent,
  type PostedReviewReceipt,
} from '../api/posting'
import type { ReviewResult, Verdict } from '../api/review'

const props = defineProps<{ reviewResult: ReviewResult; prUrl: string }>()

const toast = useToast()

const VERDICT_TO_EVENT: Record<Verdict, GitHubEvent> = {
  approve: 'APPROVE',
  request_changes: 'REQUEST_CHANGES',
  comment: 'COMMENT',
}

const EVENT_LABEL: Record<GitHubEvent, string> = {
  COMMENT: 'Comment',
  REQUEST_CHANGES: 'Request changes',
  APPROVE: 'Approve',
}

const event = ref<GitHubEvent>(VERDICT_TO_EVENT[props.reviewResult.verdict])
const inFlight = ref(false)
const posted = ref<PostedReviewReceipt | null>(null)
const error = ref<PostReviewError | null>(null)
const retryCountdown = ref(0)
let countdownTimer: ReturnType<typeof setInterval> | null = null

function stopCountdown() {
  if (countdownTimer !== null) {
    clearInterval(countdownTimer)
    countdownTimer = null
  }
}

function startCountdown(seconds: number) {
  stopCountdown()
  retryCountdown.value = seconds
  countdownTimer = setInterval(() => {
    if (retryCountdown.value > 0) retryCountdown.value -= 1
    if (retryCountdown.value <= 0) stopCountdown()
  }, 1000)
}

watch(
  () => props.reviewResult,
  (next) => {
    posted.value = null
    error.value = null
    inFlight.value = false
    stopCountdown()
    retryCountdown.value = 0
    event.value = VERDICT_TO_EVENT[next.verdict]
  },
)

onUnmounted(stopCountdown)

const retryDisabled = computed(
  () => error.value?.category === 'github_rate_limited' && retryCountdown.value > 0,
)

async function submit() {
  if (inFlight.value || posted.value) return
  inFlight.value = true
  error.value = null
  stopCountdown()
  retryCountdown.value = 0
  try {
    posted.value = await postReview({
      review_result: props.reviewResult,
      pr_url: props.prUrl,
      event: event.value,
    })
    const receipt = posted.value
    toast.push({
      category: 'success',
      message: `Review posted to GitHub (${receipt.comment_count} inline comments).`,
      action: {
        label: 'Open on GitHub',
        onClick: () => window.open(receipt.html_url, '_blank', 'noopener'),
      },
    })
  } catch (err) {
    if (err instanceof PostReviewError) {
      error.value = err
      if (err.category === 'github_rate_limited' && err.retryAfterSeconds) {
        startCountdown(err.retryAfterSeconds)
      }
      toast.push({
        category: err.category === 'github_rate_limited' ? 'info' : 'error',
        message: err.message,
        action: err.retryable
          ? { label: 'Retry', onClick: () => void submit() }
          : undefined,
      })
    } else {
      error.value = new PostReviewError(
        'internal',
        (err as Error).message || 'Unexpected error',
        false,
      )
      toast.push({ category: 'error', message: error.value.message })
    }
  } finally {
    inFlight.value = false
  }
}
</script>

<template>
  <Card title="Post to GitHub" subtitle="Publish this review back to the PR as a native GitHub review.">
    <template v-if="!posted">
      <div class="flex flex-col gap-3">
        <fieldset
          class="m-0 p-0 border-0 flex flex-wrap gap-3"
          :disabled="inFlight"
        >
          <legend class="sr-only">Review action</legend>
          <label
            v-for="opt in (['COMMENT', 'REQUEST_CHANGES', 'APPROVE'] as GitHubEvent[])"
            :key="opt"
            class="flex items-center gap-2 text-sm cursor-pointer"
          >
            <input
              type="radio"
              :value="opt"
              v-model="event"
              class="focus-ring"
            />
            <span :style="{ color: 'var(--color-text)' }">{{ EVENT_LABEL[opt] }}</span>
          </label>
        </fieldset>
        <div>
          <Button :loading="inFlight" @click="submit">Post to GitHub</Button>
        </div>
      </div>
    </template>

    <div v-if="posted" class="flex flex-col gap-1">
      <p
        class="m-0 font-semibold"
        :style="{ color: 'var(--color-success-fg)' }"
      >
        Posted ✓ —
        <a
          :href="posted.html_url"
          target="_blank"
          rel="noopener"
          class="underline"
        >View on GitHub</a>
      </p>
      <p class="m-0 text-xs text-muted">
        Inline comments attached: {{ posted.comment_count }}
      </p>
    </div>

    <div
      v-if="error && !posted"
      class="mt-3 px-3 py-2 text-sm"
      :style="{
        backgroundColor: 'var(--color-danger-bg)',
        color: 'var(--color-danger-fg)',
        borderRadius: 'var(--radius-sm)',
      }"
      role="alert"
    >
      <p class="m-0">{{ error.message }}</p>
      <p
        v-if="error.category === 'github_rate_limited'"
        class="m-0 mt-1"
        aria-live="polite"
      >
        Retry available in {{ retryCountdown }}s.
      </p>
      <p v-if="error.category === 'settings_locked'" class="m-0 mt-1">
        <RouterLink to="/settings" class="underline font-semibold">
          Go to Settings →
        </RouterLink>
      </p>
      <div v-if="error.retryable" class="mt-2">
        <Button
          variant="secondary"
          size="sm"
          :disabled="retryDisabled"
          @click="submit"
        >Retry</Button>
      </div>
    </div>
  </Card>
</template>
