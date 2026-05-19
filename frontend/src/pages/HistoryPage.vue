<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import Badge from '../components/primitives/Badge.vue'
import Card from '../components/primitives/Card.vue'
import Skeleton from '../components/primitives/Skeleton.vue'
import RunRow from '../components/history/RunRow.vue'
import { useToast } from '../composables/useToast'
import {
  listReviews,
  type ReviewRunSummary,
  type Verdict,
} from '../api/reviews'

const router = useRouter()
const route = useRoute()
const toast = useToast()

const runs = ref<ReviewRunSummary[]>([])
const isLoading = ref(true)
const loadError = ref<string | null>(null)

const VERDICT_FILTERS: Verdict[] = ['approve', 'request_changes', 'comment']
const activeFilter = ref<Verdict | null>(
  typeof route.query.verdict === 'string' && (VERDICT_FILTERS as string[]).includes(route.query.verdict)
    ? (route.query.verdict as Verdict)
    : null,
)

const filteredRuns = computed(() => {
  if (activeFilter.value === null) return runs.value
  return runs.value.filter((r) => r.verdict === activeFilter.value)
})

async function load() {
  isLoading.value = true
  loadError.value = null
  try {
    runs.value = await listReviews(50)
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Failed to load history.'
    loadError.value = message
    toast.push({ category: 'error', message: `Could not load review history: ${message}` })
  } finally {
    isLoading.value = false
  }
}

function openRun(runId: string) {
  router.push({ path: `/history/${runId}` })
}

function toggleFilter(verdict: Verdict) {
  if (activeFilter.value === verdict) {
    activeFilter.value = null
    router.replace({ query: {} })
  } else {
    activeFilter.value = verdict
    router.replace({ query: { verdict } })
  }
}

const VERDICT_LABEL: Record<Verdict, string> = {
  approve: 'approve',
  request_changes: 'request changes',
  comment: 'comment',
}

const VERDICT_TONE: Record<Verdict, 'success' | 'danger' | 'info'> = {
  approve: 'success',
  request_changes: 'danger',
  comment: 'info',
}

onMounted(load)

watch(
  () => route.query.verdict,
  (v) => {
    if (typeof v === 'string' && (VERDICT_FILTERS as string[]).includes(v)) {
      activeFilter.value = v as Verdict
    } else {
      activeFilter.value = null
    }
  },
)
</script>

<template>
  <Card
    title="Review history"
    subtitle="Most-recent 50 review runs. Click any row to reopen it without spending a fresh LLM call."
  >
    <div class="flex items-center gap-2 flex-wrap mb-3 px-4 pt-3">
      <span class="text-xs" :style="{ color: 'var(--color-text-muted)' }">Filter:</span>
      <button
        v-for="v in VERDICT_FILTERS"
        :key="v"
        type="button"
        class="focus-ring cursor-pointer"
        :aria-pressed="activeFilter === v"
        @click="toggleFilter(v)"
      >
        <Badge :tone="activeFilter === null || activeFilter === v ? VERDICT_TONE[v] : 'neutral'">
          {{ VERDICT_LABEL[v] }}
        </Badge>
      </button>
      <span
        v-if="activeFilter !== null"
        class="text-xs"
        :style="{ color: 'var(--color-text-muted)' }"
      >
        showing {{ filteredRuns.length }} of {{ runs.length }}
      </span>
    </div>
    <div v-if="isLoading" class="px-4 pb-4 space-y-2">
      <Skeleton class="h-10 w-full" />
      <Skeleton class="h-10 w-full" />
      <Skeleton class="h-10 w-full" />
    </div>
    <div
      v-else-if="loadError"
      class="px-4 py-6 text-sm"
      :style="{ color: 'var(--color-danger-fg)' }"
    >
      Failed to load history: {{ loadError }}
    </div>
    <div
      v-else-if="filteredRuns.length === 0"
      class="px-4 py-12 text-center text-sm"
      :style="{ color: 'var(--color-text-muted)' }"
    >
      <p v-if="runs.length === 0">No review runs yet. Run a review on /review to populate this list.</p>
      <p v-else>No runs match the active filter.</p>
    </div>
    <div v-else>
      <RunRow
        v-for="run in filteredRuns"
        :key="run.id"
        :run="run"
        @click="openRun"
      />
    </div>
  </Card>
</template>
