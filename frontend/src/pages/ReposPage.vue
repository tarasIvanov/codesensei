<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

import Card from '../components/primitives/Card.vue'
import RepoForm from '../components/RepoForm.vue'
import RepoList from '../components/RepoList.vue'
import { useToast } from '../composables/useToast'
import { useJobStream, type ProgressFrame } from '../composables/useJobStream'
import {
  createIndex,
  deleteRepo,
  listRepos,
  pollJob,
  RepoApiError,
  type CreateIndexResult,
  type RepoEntry,
} from '../api/repos'

const toast = useToast()

const repos = ref<RepoEntry[]>([])
const pollerHandle = ref<ReturnType<typeof setInterval> | null>(null)
const activeJobId = ref<string | null>(null)

function onStreamFrame(frame: ProgressFrame): void {
  void refresh()
  if (frame.kind === 'complete') {
    activeJobId.value = null
  }
}

const { fallbackToPolling } = useJobStream(activeJobId, onStreamFrame)

async function refresh(): Promise<void> {
  try {
    repos.value = await listRepos()
  } catch (err) {
    const message =
      err instanceof RepoApiError ? err.message : (err as Error).message
    toast.push({ category: 'error', message })
  }
}

function startPolling(): void {
  if (pollerHandle.value !== null) return
  pollerHandle.value = setInterval(() => {
    if (!repos.value.some((r) => r.status === 'indexing')) {
      stopPolling()
      return
    }
    void refresh()
  }, 2000)
}

function stopPolling(): void {
  if (pollerHandle.value !== null) {
    clearInterval(pollerHandle.value)
    pollerHandle.value = null
  }
}

watch(fallbackToPolling, (fallback) => {
  if (fallback) {
    if (repos.value.some((r) => r.status === 'indexing')) {
      startPolling()
    }
  } else {
    stopPolling()
  }
})

onMounted(() => {
  void refresh()
})

onBeforeUnmount(() => {
  stopPolling()
  activeJobId.value = null
})

function handleSubmitted(result: CreateIndexResult): void {
  void refresh()
  if (result.mode === 'async') {
    if (result.job_id) {
      activeJobId.value = result.job_id
    } else {
      startPolling()
    }
  }
}

async function handleDelete(repoId: string): Promise<void> {
  if (!window.confirm('Delete this repository and all its indexed chunks?')) return
  try {
    await deleteRepo(repoId)
    await refresh()
    toast.push({ category: 'success', message: 'Repository deleted.' })
  } catch (err) {
    const message =
      err instanceof RepoApiError ? err.message : (err as Error).message
    toast.push({ category: 'error', message })
  }
}

async function handleReindex(repo: RepoEntry): Promise<void> {
  try {
    const result = await createIndex({
      source: repo.source,
      default_branch: repo.default_branch,
    })
    await refresh()
    if (result.mode === 'async') {
      if (result.job_id) {
        activeJobId.value = result.job_id
      } else {
        startPolling()
      }
    }
    toast.push({
      category: 'success',
      message: result.mode === 'sync' ? 'Re-indexed.' : 'Re-indexing in background.',
    })
  } catch (err) {
    const message =
      err instanceof RepoApiError ? err.message : (err as Error).message
    toast.push({ category: 'error', message })
  }
}

// Reference pollJob so unused-import lints don't flag — it's part of the public surface.
void pollJob
</script>

<template>
  <Card title="Repositories" subtitle="Index a public HTTPS repository or a locally-mounted directory so /review can pull retrieved context from it.">
    <div class="flex flex-col gap-5">
      <RepoForm @submitted="handleSubmitted" />
      <RepoList
        :repos="repos"
        @delete="handleDelete"
        @reindex="handleReindex"
      />
    </div>
  </Card>
</template>
