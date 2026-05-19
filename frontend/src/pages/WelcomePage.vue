<script setup lang="ts">
import { onMounted, ref } from 'vue'

import Badge from '../components/primitives/Badge.vue'
import Card from '../components/primitives/Card.vue'
import { getSettings, type SettingsState } from '../api/settings'
import { listRepos, type RepoEntry } from '../api/repos'
import { listReviews } from '../api/reviews'

const settings = ref<SettingsState | null>(null)
const repos = ref<RepoEntry[]>([])
const reviewsCount = ref(0)

onMounted(async () => {
  try {
    settings.value = await getSettings()
  } catch {
    /* ignore */
  }
  try {
    repos.value = await listRepos()
  } catch {
    /* ignore */
  }
  try {
    const runs = await listReviews(1)
    reviewsCount.value = runs.length
  } catch {
    /* ignore */
  }
})

interface Step {
  done: boolean
  title: string
  hint: string
  to: string
  cta: string
}

function steps(): Step[] {
  const s = settings.value
  const llmReady = Boolean(
    s &&
      ((s.active_llm_provider === 'openai' && s.credentials.openai_api_key.set) ||
        (s.active_llm_provider === 'anthropic' && s.credentials.anthropic_api_key.set) ||
        s.active_llm_provider === 'ollama'),
  )
  const ghReady = Boolean(s && s.credentials.github_token.set)
  const repoReady = repos.value.some((r) => r.status === 'ready')
  return [
    {
      done: llmReady,
      title: 'Configure an LLM provider',
      hint: 'Save an OpenAI or Anthropic API key (or switch to Ollama) in Settings before /review can call out.',
      to: '/settings',
      cta: 'Open Settings',
    },
    {
      done: ghReady,
      title: 'Connect a GitHub bot PAT (optional)',
      hint: 'Needed only if you want one-click "Post to GitHub" on PR reviews. Fine-grained PAT, Pull requests read+write + Contents read.',
      to: '/settings',
      cta: 'Add token',
    },
    {
      done: repoReady,
      title: 'Index a repository (optional, RAG)',
      hint: 'Add an HTTPS GitHub URL on /repos. The repo is auto-detected from the PR URL on /review, so reviews against this repo get retrieved context + git-history hints.',
      to: '/repos',
      cta: 'Open Repos',
    },
    {
      done: reviewsCount.value > 0,
      title: 'Run your first review',
      hint: 'Paste a PR URL on /review. Findings render inline grouped by file with severity pills, code snippets, and history hints. Past runs land on /history.',
      to: '/review',
      cta: 'Open Review',
    },
  ]
}
</script>

<template>
  <Card
    title="Welcome to CodeSensei"
    subtitle="Self-hosted AI Code Reviewer with persistent RAG indexing and git-temporal context. Single docker-compose deploy, no external state."
  >
    <div class="flex flex-col gap-3 text-sm" :style="{ color: 'var(--color-text)' }">
      <p class="m-0" :style="{ color: 'var(--color-text-muted)' }">
        Three differentiators vs. plain LLM PR reviewers:
      </p>
      <ul class="m-0 pl-5 list-disc flex flex-col gap-1.5">
        <li>
          <strong>Self-hosted</strong>, air-gappable via Ollama — no PR diff leaves
          your stack when you point it at a local model.
        </li>
        <li>
          <strong>Persistent AST-RAG index</strong> (tree-sitter + pgvector HNSW)
          over indexed repositories — the reviewer sees your whole codebase, not
          just the diff.
        </li>
        <li>
          <strong>Git-temporal analysis</strong> via
          <code class="font-mono">git log -L</code> — every finding carries the
          recent commits touching the same line range, so volatile hotspots are
          flagged inline.
        </li>
      </ul>
    </div>
  </Card>

  <Card title="Quick setup" subtitle="Four steps to a working first review.">
    <ol class="m-0 p-0 list-none flex flex-col gap-3">
      <li
        v-for="(s, idx) in steps()"
        :key="idx"
        class="flex items-start gap-3 px-3 py-2.5"
        :style="{
          backgroundColor: 'var(--color-bg-elevated)',
          border: '1px solid var(--color-border)',
          borderRadius: 'var(--radius-sm)',
        }"
      >
        <span
          class="inline-flex items-center justify-center font-mono text-xs"
          :style="{
            width: '1.5rem',
            height: '1.5rem',
            borderRadius: '9999px',
            backgroundColor: s.done ? 'var(--color-success-bg)' : 'var(--color-bg-page)',
            color: s.done ? 'var(--color-success-fg)' : 'var(--color-text-muted)',
            border: '1px solid var(--color-border)',
          }"
          :aria-label="s.done ? 'done' : 'pending'"
        >{{ s.done ? '✓' : idx + 1 }}</span>
        <div class="flex-1 min-w-0">
          <div class="flex items-center gap-2 flex-wrap">
            <strong :style="{ color: 'var(--color-text)' }">{{ s.title }}</strong>
            <Badge v-if="s.done" tone="success">done</Badge>
          </div>
          <p
            class="m-0 mt-1 text-sm"
            :style="{ color: 'var(--color-text-muted)' }"
          >{{ s.hint }}</p>
        </div>
        <RouterLink
          :to="s.to"
          class="focus-ring text-xs font-medium px-2.5 py-1 whitespace-nowrap"
          :style="{
            backgroundColor: 'var(--color-brand-600)',
            color: 'var(--color-neutral-0)',
            borderRadius: 'var(--radius-sm)',
          }"
        >{{ s.cta }}</RouterLink>
      </li>
    </ol>
  </Card>

  <Card title="What's in the SPA" subtitle="Five pages, all wired to the same FastAPI backend.">
    <div class="grid grid-cols-2 gap-3 text-sm">
      <RouterLink
        to="/review"
        class="focus-ring p-3 transition-colors hover:brightness-110"
        :style="{
          backgroundColor: 'var(--color-bg-elevated)',
          border: '1px solid var(--color-border)',
          borderRadius: 'var(--radius-sm)',
          color: 'var(--color-text)',
        }"
      >
        <div class="font-semibold">/review</div>
        <p class="m-0 mt-1 text-xs" :style="{ color: 'var(--color-text-muted)' }">
          Paste a PR URL → structured findings + verdict. Auto-detects indexed
          repo for RAG context. One-click post back to GitHub.
        </p>
      </RouterLink>
      <RouterLink
        to="/repos"
        class="focus-ring p-3 transition-colors hover:brightness-110"
        :style="{
          backgroundColor: 'var(--color-bg-elevated)',
          border: '1px solid var(--color-border)',
          borderRadius: 'var(--radius-sm)',
          color: 'var(--color-text)',
        }"
      >
        <div class="font-semibold">/repos</div>
        <p class="m-0 mt-1 text-xs" :style="{ color: 'var(--color-text-muted)' }">
          Index a public HTTPS repo (sync ≤ 200 files, async via arq above that).
          Chunks live in pgvector (HNSW + cosine, 1536-dim).
        </p>
      </RouterLink>
      <RouterLink
        to="/history"
        class="focus-ring p-3 transition-colors hover:brightness-110"
        :style="{
          backgroundColor: 'var(--color-bg-elevated)',
          border: '1px solid var(--color-border)',
          borderRadius: 'var(--radius-sm)',
          color: 'var(--color-text)',
        }"
      >
        <div class="font-semibold">/history</div>
        <p class="m-0 mt-1 text-xs" :style="{ color: 'var(--color-text-muted)' }">
          Every successful review auto-persists. Re-open detail view without a
          fresh LLM call. Re-run, re-post to GitHub, or delete a row.
        </p>
      </RouterLink>
      <RouterLink
        to="/settings"
        class="focus-ring p-3 transition-colors hover:brightness-110"
        :style="{
          backgroundColor: 'var(--color-bg-elevated)',
          border: '1px solid var(--color-border)',
          borderRadius: 'var(--radius-sm)',
          color: 'var(--color-text)',
        }"
      >
        <div class="font-semibold">/settings</div>
        <p class="m-0 mt-1 text-xs" :style="{ color: 'var(--color-text-muted)' }">
          Active provider, model overrides, API keys. Credentials stored Fernet-encrypted
          via auto-generated MASTER_KEY. Test buttons probe live providers.
        </p>
      </RouterLink>
      <RouterLink
        to="/status"
        class="focus-ring p-3 transition-colors hover:brightness-110 col-span-2"
        :style="{
          backgroundColor: 'var(--color-bg-elevated)',
          border: '1px solid var(--color-border)',
          borderRadius: 'var(--radius-sm)',
          color: 'var(--color-text)',
        }"
      >
        <div class="font-semibold">/status</div>
        <p class="m-0 mt-1 text-xs" :style="{ color: 'var(--color-text-muted)' }">
          Live readiness of every component (db, redis, pgvector, LLM provider,
          embedding provider, worker). Hover any dot for the last error string.
        </p>
      </RouterLink>
    </div>
  </Card>

  <footer
    class="text-center text-xs py-4"
    :style="{ color: 'var(--color-text-muted)' }"
  >
    Something went wrong, or have feedback? Write to
    <a
      href="mailto:taras.ivanov.ua@gmail.com?subject=CodeSensei%20feedback"
      class="focus-ring underline-offset-2 hover:underline"
      :style="{ color: 'var(--color-brand-700)' }"
    >taras.ivanov.ua@gmail.com</a>.
  </footer>
</template>
