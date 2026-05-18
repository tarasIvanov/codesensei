import { ReviewApiError, type ReviewErrorCategory } from './review'

export type TestGithubErrorCategory =
  | 'settings_locked'
  | 'github_auth_failed'
  | 'github_api_unavailable'
  | 'github_rate_limited'
  | 'internal'

export interface TestGithubResult {
  ok: true
  login: string
  scopes_hint: string | null
  elapsed_ms: number
}

export class TestGithubError extends Error {
  category: TestGithubErrorCategory
  retryable: boolean
  retryAfterSeconds?: number

  constructor(
    category: TestGithubErrorCategory,
    message: string,
    retryable: boolean,
    retryAfterSeconds?: number,
  ) {
    super(message)
    this.category = category
    this.retryable = retryable
    this.retryAfterSeconds = retryAfterSeconds
  }
}

const TEST_GITHUB_FALLBACK_MSG: Record<TestGithubErrorCategory, string> = {
  settings_locked: 'GitHub PAT is not configured. Add one in Settings.',
  github_auth_failed: 'GitHub rejected the PAT. Check the value and permissions.',
  github_api_unavailable: 'GitHub is unreachable. Try again.',
  github_rate_limited: 'GitHub rate-limited the probe.',
  internal: 'Unexpected server error.',
}

export async function testGithub(): Promise<TestGithubResult> {
  const response = await fetch('/api/settings/test/github')
  if (response.ok) {
    return (await response.json()) as TestGithubResult
  }
  let category: TestGithubErrorCategory = 'internal'
  let message = TEST_GITHUB_FALLBACK_MSG.internal
  let retryable = false
  let retryAfterSeconds: number | undefined
  try {
    const parsed = (await response.json()) as {
      error?: {
        category?: TestGithubErrorCategory
        message?: string
        retryable?: boolean
      }
      retry_after_seconds?: number
    }
    if (parsed?.error?.category) {
      category = parsed.error.category
      message = parsed.error.message || TEST_GITHUB_FALLBACK_MSG[category]
      retryable = Boolean(parsed.error.retryable)
    }
    if (typeof parsed?.retry_after_seconds === 'number') {
      retryAfterSeconds = parsed.retry_after_seconds
    }
  } catch {
    // not JSON
  }
  throw new TestGithubError(category, message, retryable, retryAfterSeconds)
}

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
