import { ReviewApiError, type ReviewErrorCategory } from './review'

export interface CredentialFingerprint {
  set: boolean
  fingerprint: string | null
}

export interface SettingsState {
  active_llm_provider: string
  active_embedding_provider: string
  llm_model: string
  embedding_model: string
  ollama_base_url: string
  credentials: {
    openai_api_key: CredentialFingerprint
    anthropic_api_key: CredentialFingerprint
    github_token: CredentialFingerprint
  }
  master_key_present: boolean
}

export interface SettingsUpdate {
  active_llm_provider?: string
  active_embedding_provider?: string
  llm_model?: string
  embedding_model?: string
  ollama_base_url?: string
  openai_api_key?: string
  anthropic_api_key?: string
  github_token?: string
}

async function _call(method: 'GET' | 'POST', body?: SettingsUpdate): Promise<SettingsState> {
  const init: RequestInit = {
    method,
    headers: { 'Content-Type': 'application/json' },
  }
  if (body !== undefined) init.body = JSON.stringify(body)
  const response = await fetch('/api/settings/', init)
  if (response.ok) {
    return (await response.json()) as SettingsState
  }
  let category: ReviewErrorCategory = 'internal'
  let message = 'Unexpected server error.'
  let retryable = false
  try {
    const parsed = (await response.json()) as {
      error?: { category?: ReviewErrorCategory; message?: string; retryable?: boolean }
    }
    if (parsed?.error?.category) {
      category = parsed.error.category
      message = parsed.error.message || message
      retryable = Boolean(parsed.error.retryable)
    }
  } catch {
    // fall through
  }
  throw new ReviewApiError(category, message, retryable)
}

export function getSettings(): Promise<SettingsState> {
  return _call('GET')
}

export function saveSettings(body: SettingsUpdate): Promise<SettingsState> {
  return _call('POST', body)
}
