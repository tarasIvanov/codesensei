<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

import Badge from '../components/primitives/Badge.vue'
import Button from '../components/primitives/Button.vue'
import Card from '../components/primitives/Card.vue'
import { useToast } from '../composables/useToast'
import { ReviewApiError } from '../api/review'
import {
  getSettings,
  saveSettings,
  testGithub,
  TestGithubError,
  type SettingsState,
  type SettingsUpdate,
} from '../api/settings'

const toast = useToast()

const state = ref<SettingsState | null>(null)
const isLoading = ref(true)
const isSaving = ref(false)
const errorMessage = ref('')

const activeLlm = ref('openai')
const activeEmbedding = ref('openai')
const llmModel = ref('')
const embeddingModel = ref('')
const ollamaBaseUrl = ref('')
const openaiKey = ref('')
const anthropicKey = ref('')
const githubToken = ref('')

type GithubTestState =
  | { kind: 'idle' }
  | { kind: 'in_flight' }
  | { kind: 'ok'; login: string; scopes_hint: string | null; elapsedMs: number }
  | { kind: 'error'; message: string }

const githubTest = ref<GithubTestState>({ kind: 'idle' })

function hydrate(s: SettingsState) {
  state.value = s
  activeLlm.value = s.active_llm_provider
  activeEmbedding.value = s.active_embedding_provider
  llmModel.value = s.llm_model
  embeddingModel.value = s.embedding_model
  ollamaBaseUrl.value = s.ollama_base_url
  openaiKey.value = ''
  anthropicKey.value = ''
  githubToken.value = ''
}

const secretsDisabled = computed(() => !state.value?.master_key_present)

onMounted(async () => {
  try {
    hydrate(await getSettings())
  } catch (err) {
    errorMessage.value = (err as Error).message || 'Failed to load settings.'
  } finally {
    isLoading.value = false
  }
})

watch(githubToken, () => {
  if (githubTest.value.kind !== 'idle' && githubTest.value.kind !== 'in_flight') {
    githubTest.value = { kind: 'idle' }
  }
})

async function save() {
  isSaving.value = true
  errorMessage.value = ''
  const body: SettingsUpdate = {
    active_llm_provider: activeLlm.value,
    active_embedding_provider: activeEmbedding.value,
    llm_model: llmModel.value,
    embedding_model: embeddingModel.value,
    ollama_base_url: ollamaBaseUrl.value,
  }
  if (openaiKey.value) body.openai_api_key = openaiKey.value
  if (anthropicKey.value) body.anthropic_api_key = anthropicKey.value
  if (githubToken.value) body.github_token = githubToken.value
  try {
    hydrate(await saveSettings(body))
    toast.push({ category: 'success', message: 'Settings saved. Next call uses the new values.' })
  } catch (err) {
    if (err instanceof ReviewApiError) {
      errorMessage.value = err.message
    } else {
      errorMessage.value = (err as Error).message || 'Save failed.'
    }
    toast.push({ category: 'error', message: errorMessage.value })
  } finally {
    isSaving.value = false
  }
}

async function clearSecret(field: 'openai_api_key' | 'anthropic_api_key' | 'github_token') {
  isSaving.value = true
  errorMessage.value = ''
  try {
    hydrate(await saveSettings({ [field]: '' } as SettingsUpdate))
    toast.push({ category: 'success', message: 'Credential cleared.' })
  } catch (err) {
    errorMessage.value =
      err instanceof ReviewApiError
        ? err.message
        : (err as Error).message || 'Clear failed.'
    toast.push({ category: 'error', message: errorMessage.value })
  } finally {
    isSaving.value = false
  }
}

async function runGithubTest() {
  if (githubTest.value.kind === 'in_flight') return
  githubTest.value = { kind: 'in_flight' }
  try {
    const result = await testGithub()
    githubTest.value = {
      kind: 'ok',
      login: result.login,
      scopes_hint: result.scopes_hint,
      elapsedMs: result.elapsed_ms,
    }
  } catch (err) {
    const message =
      err instanceof TestGithubError
        ? err.message
        : (err as Error).message || 'Probe failed.'
    githubTest.value = { kind: 'error', message }
  }
}
</script>

<template>
  <Card title="Settings" subtitle="Active providers, model overrides, and credentials. Saved values override .env on the next provider factory call.">
    <div v-if="isLoading" class="text-sm text-muted">Loading…</div>
    <div v-else-if="state" class="flex flex-col gap-5">
      <p
        v-if="!state.master_key_present"
        class="m-0 px-3 py-2 text-sm"
        :style="{
          backgroundColor: 'var(--color-warning-bg)',
          color: 'var(--color-warning-fg)',
          borderRadius: 'var(--radius-sm)',
        }"
      >
        Settings storage is locked — set <code>MASTER_KEY</code> in <code>.env</code> before
        saving credentials. You can still change provider names and model overrides.
      </p>

      <fieldset
        class="m-0 p-0 border-0 flex flex-col gap-3"
      >
        <legend class="text-xs font-semibold uppercase tracking-wide text-muted">
          Active providers
        </legend>
        <label class="flex flex-col gap-1 text-sm">
          <span :style="{ color: 'var(--color-text)' }">LLM provider</span>
          <select
            v-model="activeLlm"
            class="focus-ring px-2 py-1.5 text-sm font-mono"
            :style="{
              backgroundColor: 'var(--color-bg-elevated)',
              border: '1px solid var(--color-border)',
              borderRadius: 'var(--radius-sm)',
              color: 'var(--color-text)',
            }"
          >
            <option value="openai">openai</option>
            <option value="anthropic">anthropic</option>
            <option value="ollama">ollama</option>
          </select>
        </label>
        <label class="flex flex-col gap-1 text-sm">
          <span :style="{ color: 'var(--color-text)' }">Embedding provider</span>
          <select
            v-model="activeEmbedding"
            class="focus-ring px-2 py-1.5 text-sm font-mono"
            :style="{
              backgroundColor: 'var(--color-bg-elevated)',
              border: '1px solid var(--color-border)',
              borderRadius: 'var(--radius-sm)',
              color: 'var(--color-text)',
            }"
          >
            <option value="openai">openai</option>
            <option value="ollama">ollama</option>
          </select>
        </label>
      </fieldset>

      <fieldset class="m-0 p-0 border-0 flex flex-col gap-3">
        <legend class="text-xs font-semibold uppercase tracking-wide text-muted">
          Model overrides
        </legend>
        <label class="flex flex-col gap-1 text-sm">
          <span :style="{ color: 'var(--color-text)' }">LLM model</span>
          <input
            v-model="llmModel"
            type="text"
            spellcheck="false"
            placeholder="(default)"
            class="focus-ring px-2 py-1.5 text-sm font-mono"
            :style="{
              backgroundColor: 'var(--color-bg-elevated)',
              border: '1px solid var(--color-border)',
              borderRadius: 'var(--radius-sm)',
              color: 'var(--color-text)',
            }"
          />
        </label>
        <label class="flex flex-col gap-1 text-sm">
          <span :style="{ color: 'var(--color-text)' }">Embedding model</span>
          <input
            v-model="embeddingModel"
            type="text"
            spellcheck="false"
            placeholder="(default)"
            class="focus-ring px-2 py-1.5 text-sm font-mono"
            :style="{
              backgroundColor: 'var(--color-bg-elevated)',
              border: '1px solid var(--color-border)',
              borderRadius: 'var(--radius-sm)',
              color: 'var(--color-text)',
            }"
          />
        </label>
        <label class="flex flex-col gap-1 text-sm">
          <span :style="{ color: 'var(--color-text)' }">Ollama base URL</span>
          <input
            v-model="ollamaBaseUrl"
            type="text"
            spellcheck="false"
            placeholder="http://ollama:11434"
            class="focus-ring px-2 py-1.5 text-sm font-mono"
            :style="{
              backgroundColor: 'var(--color-bg-elevated)',
              border: '1px solid var(--color-border)',
              borderRadius: 'var(--radius-sm)',
              color: 'var(--color-text)',
            }"
          />
        </label>
      </fieldset>

      <fieldset class="m-0 p-0 border-0 flex flex-col gap-3">
        <legend class="text-xs font-semibold uppercase tracking-wide text-muted">
          Credentials
        </legend>
        <label class="flex flex-col gap-1 text-sm">
          <span :style="{ color: 'var(--color-text)' }">OpenAI API key</span>
          <div class="flex gap-2">
            <input
              v-model="openaiKey"
              type="password"
              :disabled="secretsDisabled"
              :placeholder="state.credentials.openai_api_key.set
                ? state.credentials.openai_api_key.fingerprint || '…stored…'
                : 'not configured'"
              spellcheck="false"
              class="focus-ring flex-1 px-2 py-1.5 text-sm font-mono"
              :style="{
                backgroundColor: 'var(--color-bg-elevated)',
                border: '1px solid var(--color-border)',
                borderRadius: 'var(--radius-sm)',
                color: 'var(--color-text)',
              }"
            />
            <Button
              v-if="state.credentials.openai_api_key.set"
              variant="secondary"
              size="sm"
              :disabled="isSaving"
              @click="clearSecret('openai_api_key')"
            >Clear</Button>
          </div>
          <p class="text-xs text-muted m-0">
            OpenAI connectivity is shown on the
            <RouterLink to="/" class="underline">Status</RouterLink> page.
          </p>
        </label>
        <label class="flex flex-col gap-1 text-sm">
          <span :style="{ color: 'var(--color-text)' }">Anthropic API key</span>
          <div class="flex gap-2">
            <input
              v-model="anthropicKey"
              type="password"
              :disabled="secretsDisabled"
              :placeholder="state.credentials.anthropic_api_key.set
                ? state.credentials.anthropic_api_key.fingerprint || '…stored…'
                : 'not configured'"
              spellcheck="false"
              class="focus-ring flex-1 px-2 py-1.5 text-sm font-mono"
              :style="{
                backgroundColor: 'var(--color-bg-elevated)',
                border: '1px solid var(--color-border)',
                borderRadius: 'var(--radius-sm)',
                color: 'var(--color-text)',
              }"
            />
            <Button
              v-if="state.credentials.anthropic_api_key.set"
              variant="secondary"
              size="sm"
              :disabled="isSaving"
              @click="clearSecret('anthropic_api_key')"
            >Clear</Button>
          </div>
        </label>
        <label class="flex flex-col gap-1 text-sm">
          <span :style="{ color: 'var(--color-text)' }">GitHub token</span>
          <div class="flex gap-2">
            <input
              v-model="githubToken"
              type="password"
              :disabled="secretsDisabled"
              :placeholder="state.credentials.github_token.set
                ? state.credentials.github_token.fingerprint || '…stored…'
                : 'not configured'"
              spellcheck="false"
              class="focus-ring flex-1 px-2 py-1.5 text-sm font-mono"
              :style="{
                backgroundColor: 'var(--color-bg-elevated)',
                border: '1px solid var(--color-border)',
                borderRadius: 'var(--radius-sm)',
                color: 'var(--color-text)',
              }"
            />
            <Button
              variant="secondary"
              size="sm"
              :loading="githubTest.kind === 'in_flight'"
              :disabled="!state.credentials.github_token.set && !githubToken"
              @click="runGithubTest"
            >Test connection</Button>
            <Button
              v-if="state.credentials.github_token.set"
              variant="secondary"
              size="sm"
              :disabled="isSaving"
              @click="clearSecret('github_token')"
            >Clear</Button>
          </div>
          <div v-if="githubTest.kind === 'ok'" class="flex items-center gap-2 mt-1">
            <Badge tone="success">OK</Badge>
            <span class="text-xs text-muted font-mono">
              {{ githubTest.login }}
              <span v-if="githubTest.scopes_hint"> · {{ githubTest.scopes_hint }}</span>
              · {{ githubTest.elapsedMs }} ms
            </span>
          </div>
          <div v-else-if="githubTest.kind === 'error'" class="flex items-center gap-2 mt-1">
            <Badge tone="danger">FAILED</Badge>
            <span class="text-xs font-mono" :style="{ color: 'var(--color-danger-fg)' }">
              {{ githubTest.message }}
            </span>
          </div>
        </label>
      </fieldset>

      <div class="flex items-center gap-3">
        <Button :loading="isSaving" @click="save">Save</Button>
      </div>

      <p
        v-if="errorMessage"
        class="m-0 px-3 py-2 text-sm"
        :style="{
          backgroundColor: 'var(--color-danger-bg)',
          color: 'var(--color-danger-fg)',
          borderRadius: 'var(--radius-sm)',
        }"
      >
        {{ errorMessage }}
      </p>
    </div>
  </Card>
</template>
