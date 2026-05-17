<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'

import RepoForm from '../components/RepoForm.vue'
import RepoList from '../components/RepoList.vue'
import {
  createIndex,
  deleteRepo,
  listRepos,
  pollJob,
  RepoApiError,
  type CreateIndexResult,
  type RepoEntry,
} from '../api/repos'

const repos = ref<RepoEntry[]>([])
const errorMessage = ref('')

const pollerHandle = ref<ReturnType<typeof setInterval> | null>(null)

async function refresh(): Promise<void> {
  try {
    repos.value = await listRepos()
  } catch (err) {
    errorMessage.value = err instanceof RepoApiError ? err.message : (err as Error).message
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

onMounted(() => {
  void refresh()
})

onBeforeUnmount(stopPolling)

function handleSubmitted(result: CreateIndexResult): void {
  void refresh()
  if (result.mode === 'async') {
    startPolling()
  }
}

async function handleDelete(repoId: string): Promise<void> {
  if (!window.confirm('Delete this repository and all its indexed chunks?')) return
  try {
    await deleteRepo(repoId)
    await refresh()
  } catch (err) {
    errorMessage.value = err instanceof RepoApiError ? err.message : (err as Error).message
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
      startPolling()
    }
  } catch (err) {
    errorMessage.value = err instanceof RepoApiError ? err.message : (err as Error).message
  }
}

// Reference pollJob so unused-import lints don't flag — it's part of the public surface
// of `../api/repos` even though this page polls via `listRepos` for now.
void pollJob
</script>

<template>
  <section>
    <h1>Repositories</h1>
    <p class="subtitle">
      Index a public HTTPS repository or a locally-mounted directory so the
      <RouterLink to="/review">Review</RouterLink> page can pull retrieved context from it.
    </p>

    <RepoForm @submitted="handleSubmitted" />

    <p v-if="errorMessage" class="error">{{ errorMessage }}</p>

    <RepoList
      :repos="repos"
      @delete="handleDelete"
      @reindex="handleReindex"
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
.error {
  margin: 0.6rem 0;
  padding: 0.5rem 0.7rem;
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: 0.4rem;
  color: #991b1b;
  font-size: 0.88rem;
}
</style>
