<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { ReviewApiError } from '../api/review'
import {
  getSettings,
  saveSettings,
  type SettingsState,
  type SettingsUpdate,
} from '../api/settings'

const state = ref<SettingsState | null>(null)
const isLoading = ref(true)
const isSaving = ref(false)
const errorMessage = ref('')
const flash = ref('')

// Form fields (local).
const activeLlm = ref('openai')
const activeEmbedding = ref('openai')
const llmModel = ref('')
const embeddingModel = ref('')
const ollamaBaseUrl = ref('')
const openaiKey = ref('')
const anthropicKey = ref('')
const githubToken = ref('')

function hydrate(s: SettingsState) {
  state.value = s
  activeLlm.value = s.active_llm_provider
  activeEmbedding.value = s.active_embedding_provider
  llmModel.value = s.llm_model
  embeddingModel.value = s.embedding_model
  ollamaBaseUrl.value = s.ollama_base_url
  // Keep secret inputs blank — user must explicitly type to change.
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

async function save() {
  isSaving.value = true
  errorMessage.value = ''
  flash.value = ''
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
    flash.value = 'Settings saved. Next call uses the new values.'
  } catch (err) {
    if (err instanceof ReviewApiError) {
      errorMessage.value = err.message
    } else {
      errorMessage.value = (err as Error).message || 'Save failed.'
    }
  } finally {
    isSaving.value = false
  }
}

async function clearSecret(field: 'openai_api_key' | 'anthropic_api_key' | 'github_token') {
  isSaving.value = true
  errorMessage.value = ''
  flash.value = ''
  try {
    hydrate(await saveSettings({ [field]: '' } as SettingsUpdate))
    flash.value = 'Credential cleared.'
  } catch (err) {
    errorMessage.value =
      err instanceof ReviewApiError
        ? err.message
        : (err as Error).message || 'Clear failed.'
  } finally {
    isSaving.value = false
  }
}
</script>

<template>
  <section>
    <h1>Settings</h1>
    <p class="subtitle">
      Active providers, model overrides, and credentials. Saved values
      override the equivalent <code>.env</code> entries on the next provider
      factory call.
    </p>

    <p v-if="isLoading">Loading…</p>

    <div v-else-if="state">
      <p v-if="!state.master_key_present" class="warn">
        Settings storage is locked — set <code>MASTER_KEY</code> in
        <code>.env</code> before saving credentials. You can still change
        provider names and model overrides.
      </p>

      <fieldset>
        <legend>Active providers</legend>
        <label>
          LLM provider
          <select v-model="activeLlm">
            <option value="openai">openai</option>
            <option value="anthropic">anthropic</option>
            <option value="ollama">ollama</option>
          </select>
        </label>
        <label>
          Embedding provider
          <select v-model="activeEmbedding">
            <option value="openai">openai</option>
            <option value="ollama">ollama</option>
          </select>
        </label>
      </fieldset>

      <fieldset>
        <legend>Model overrides</legend>
        <label>
          LLM model
          <input v-model="llmModel" type="text" spellcheck="false" placeholder="(default)" />
        </label>
        <label>
          Embedding model
          <input v-model="embeddingModel" type="text" spellcheck="false" placeholder="(default)" />
        </label>
        <label>
          Ollama base URL
          <input v-model="ollamaBaseUrl" type="text" spellcheck="false" placeholder="http://ollama:11434" />
        </label>
      </fieldset>

      <fieldset>
        <legend>Credentials</legend>
        <label>
          OpenAI API key
          <div class="cred-row">
            <input
              v-model="openaiKey"
              type="password"
              :disabled="secretsDisabled"
              :placeholder="state.credentials.openai_api_key.set
                ? state.credentials.openai_api_key.fingerprint || '…stored…'
                : 'not configured'"
              spellcheck="false"
            />
            <button
              v-if="state.credentials.openai_api_key.set"
              type="button" class="clear" :disabled="isSaving"
              @click="clearSecret('openai_api_key')"
            >Clear</button>
          </div>
        </label>
        <label>
          Anthropic API key
          <div class="cred-row">
            <input
              v-model="anthropicKey"
              type="password"
              :disabled="secretsDisabled"
              :placeholder="state.credentials.anthropic_api_key.set
                ? state.credentials.anthropic_api_key.fingerprint || '…stored…'
                : 'not configured'"
              spellcheck="false"
            />
            <button
              v-if="state.credentials.anthropic_api_key.set"
              type="button" class="clear" :disabled="isSaving"
              @click="clearSecret('anthropic_api_key')"
            >Clear</button>
          </div>
        </label>
        <label>
          GitHub token
          <div class="cred-row">
            <input
              v-model="githubToken"
              type="password"
              :disabled="secretsDisabled"
              :placeholder="state.credentials.github_token.set
                ? state.credentials.github_token.fingerprint || '…stored…'
                : 'not configured'"
              spellcheck="false"
            />
            <button
              v-if="state.credentials.github_token.set"
              type="button" class="clear" :disabled="isSaving"
              @click="clearSecret('github_token')"
            >Clear</button>
          </div>
        </label>
      </fieldset>

      <div class="actions">
        <button class="submit" :disabled="isSaving" @click="save">
          {{ isSaving ? 'Saving…' : 'Save' }}
        </button>
        <span v-if="flash" class="flash">{{ flash }}</span>
      </div>

      <p v-if="errorMessage" class="error">{{ errorMessage }}</p>
    </div>
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
fieldset {
  border: 1px solid #e5e7eb;
  border-radius: 0.5rem;
  padding: 0.75rem 1rem;
  margin: 0 0 1rem;
}
legend {
  font-size: 0.85rem;
  font-weight: 600;
  color: #334155;
  padding: 0 0.4rem;
}
label {
  display: block;
  margin: 0.5rem 0;
  font-size: 0.9rem;
}
input, select {
  display: block;
  width: 100%;
  padding: 0.45rem 0.55rem;
  border: 1px solid #d1d5db;
  border-radius: 0.4rem;
  font-family: ui-monospace, Menlo, monospace;
  font-size: 0.9rem;
  background: #f9fafb;
  box-sizing: border-box;
}
input:disabled {
  background: #f3f4f6;
  color: #9ca3af;
}
.cred-row {
  display: flex;
  gap: 0.5rem;
}
.cred-row input {
  flex: 1;
}
.clear {
  background: #6b7280;
  color: #fff;
  border: 0;
  border-radius: 0.3rem;
  padding: 0 0.7rem;
  font-size: 0.8rem;
  cursor: pointer;
}
.actions {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}
.submit {
  background: #2563eb;
  color: #fff;
  border: 0;
  border-radius: 0.4rem;
  padding: 0.5rem 1.1rem;
  font-size: 0.95rem;
  font-weight: 600;
  cursor: pointer;
}
.submit:disabled {
  background: #94a3b8;
  cursor: not-allowed;
}
.flash {
  color: #166534;
  font-size: 0.85rem;
}
.warn {
  padding: 0.6rem 0.85rem;
  background: #fef9c3;
  border: 1px solid #fde68a;
  border-radius: 0.4rem;
  color: #713f12;
  font-size: 0.85rem;
}
.error {
  margin-top: 0.9rem;
  padding: 0.6rem 0.85rem;
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: 0.4rem;
  color: #991b1b;
  font-size: 0.9rem;
}
</style>
