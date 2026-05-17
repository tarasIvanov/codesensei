<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'

import {
  postReview,
  PostReviewError,
  type GitHubEvent,
  type PostedReviewReceipt,
} from '../api/posting'
import type { ReviewResult, Verdict } from '../api/review'

const props = defineProps<{ reviewResult: ReviewResult; prUrl: string }>()

const VERDICT_TO_EVENT: Record<Verdict, GitHubEvent> = {
  approve: 'APPROVE',
  request_changes: 'REQUEST_CHANGES',
  comment: 'COMMENT',
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
    if (retryCountdown.value > 0) {
      retryCountdown.value -= 1
    }
    if (retryCountdown.value <= 0) {
      stopCountdown()
    }
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
  } catch (err) {
    if (err instanceof PostReviewError) {
      error.value = err
      if (err.category === 'github_rate_limited' && err.retryAfterSeconds) {
        startCountdown(err.retryAfterSeconds)
      }
    } else {
      error.value = new PostReviewError(
        'internal',
        (err as Error).message || 'Unexpected error',
        false,
      )
    }
  } finally {
    inFlight.value = false
  }
}
</script>

<template>
  <section class="panel" aria-label="Post review to GitHub">
    <h2 class="title">Post to GitHub</h2>

    <template v-if="!posted">
      <fieldset class="events" :disabled="inFlight">
        <legend class="legend">Review action</legend>
        <label
          v-for="opt in (['COMMENT','REQUEST_CHANGES','APPROVE'] as GitHubEvent[])"
          :key="opt"
          class="event-option"
        >
          <input type="radio" :value="opt" v-model="event" />
          <span>{{ opt === 'COMMENT' ? 'Comment' : opt === 'REQUEST_CHANGES' ? 'Request changes' : 'Approve' }}</span>
        </label>
      </fieldset>

      <button
        class="submit"
        :disabled="inFlight"
        :aria-busy="inFlight ? 'true' : 'false'"
        @click="submit"
      >
        {{ inFlight ? 'Posting…' : 'Post to GitHub' }}
      </button>
    </template>

    <div v-if="posted" class="posted">
      <p class="success">
        Posted ✓ —
        <a :href="posted.html_url" target="_blank" rel="noopener">View on GitHub</a>
      </p>
      <p class="meta">Inline comments attached: {{ posted.comment_count }}</p>
    </div>

    <div v-if="error" class="banner" role="alert">
      <p class="banner-msg">{{ error.message }}</p>
      <p v-if="error.category === 'github_rate_limited'" class="banner-msg" aria-live="polite">
        Retry available in {{ retryCountdown }}s.
      </p>
      <p v-if="error.category === 'settings_locked'" class="banner-msg">
        <RouterLink to="/settings" class="settings-link">Go to Settings →</RouterLink>
      </p>
      <button
        v-if="error.retryable"
        class="retry"
        :disabled="retryDisabled"
        @click="submit"
      >
        Retry
      </button>
    </div>
  </section>
</template>

<style scoped>
.panel {
  margin-top: 1rem;
  padding: 0.85rem 1rem;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 0.5rem;
  font-family: system-ui, -apple-system, Segoe UI, sans-serif;
}
.title {
  margin: 0 0 0.5rem;
  font-size: 1rem;
  color: #0f172a;
}
.events {
  border: 0;
  padding: 0;
  margin: 0 0 0.5rem;
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
}
.legend {
  font-size: 0.75rem;
  color: #475569;
  margin-bottom: 0.35rem;
}
.event-option {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  font-size: 0.85rem;
  color: #0f172a;
}
.submit {
  background: #16a34a;
  color: #fff;
  border: 0;
  border-radius: 0.4rem;
  padding: 0.4rem 0.95rem;
  font-size: 0.9rem;
  font-weight: 600;
  cursor: pointer;
}
.submit:disabled {
  background: #94a3b8;
  cursor: not-allowed;
}
.posted {
  margin-top: 0.25rem;
}
.success {
  color: #15803d;
  font-weight: 600;
  margin: 0;
}
.success a {
  color: #15803d;
}
.meta {
  color: #475569;
  font-size: 0.8rem;
  margin: 0.25rem 0 0;
}
.banner {
  margin-top: 0.6rem;
  padding: 0.55rem 0.75rem;
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: 0.4rem;
  color: #991b1b;
  font-size: 0.85rem;
}
.banner-msg {
  margin: 0 0 0.25rem;
}
.settings-link {
  color: #991b1b;
  font-weight: 600;
  text-decoration: underline;
}
.retry {
  margin-top: 0.25rem;
  background: #991b1b;
  color: #fff;
  border: 0;
  border-radius: 0.3rem;
  padding: 0.2rem 0.7rem;
  font-size: 0.8rem;
  cursor: pointer;
}
.retry:disabled {
  background: #94a3b8;
  cursor: not-allowed;
}
</style>
