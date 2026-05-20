import type { Finding } from './review'
import { ReviewApiError, type ReviewErrorCategory } from './review'

export type Verdict = 'approve' | 'request_changes' | 'comment'
export type InputKind = 'diff' | 'pr_url'

export interface ReviewRunSummary {
  id: string
  created_at: string
  input_kind: InputKind
  pr_url: string | null
  verdict: Verdict
  provider: string
  elapsed_ms: number
  finding_count: number
  has_temporal: boolean
  prompt_tokens?: number | null
  completion_tokens?: number | null
  cost_usd?: number | null
}

export interface ReviewRunDetail {
  id: string
  created_at: string
  input_kind: InputKind
  pr_url: string | null
  diff: string
  verdict: Verdict
  provider: string
  elapsed_ms: number
  findings: Finding[]
  context_files?: string[] | null
  prompt_tokens?: number | null
  completion_tokens?: number | null
  cost_usd?: number | null
}

const FALLBACK_MESSAGE: Record<ReviewErrorCategory, string> = {
  invalid_input: 'Review run not found.',
  payload_too_large: 'Payload too large.',
  github_fetch_failed: 'GitHub fetch failed.',
  provider_unavailable: 'Provider unavailable.',
  provider_malformed_output: 'Provider returned malformed output.',
  settings_locked: 'Settings storage locked.',
  repo_not_ready: 'Repository not ready.',
  embedding_mismatch: 'Embedding model mismatch.',
  internal: 'Unexpected server error.',
}

async function _throwFromResponse(response: Response): Promise<never> {
  let category: ReviewErrorCategory = 'internal'
  let message = FALLBACK_MESSAGE.internal
  let retryable = false
  try {
    const parsed = (await response.json()) as {
      error?: { category?: ReviewErrorCategory; message?: string; retryable?: boolean }
    }
    if (parsed?.error?.category) {
      category = parsed.error.category
      message = parsed.error.message || FALLBACK_MESSAGE[category]
      retryable = Boolean(parsed.error.retryable)
    }
  } catch {
    // Body wasn't JSON.
  }
  throw new ReviewApiError(category, message, retryable)
}

export async function listReviews(limit = 50): Promise<ReviewRunSummary[]> {
  const response = await fetch(`/api/reviews?limit=${limit}`)
  if (!response.ok) await _throwFromResponse(response)
  const body = (await response.json()) as { runs: ReviewRunSummary[] }
  return body.runs
}

export async function getReview(runId: string): Promise<ReviewRunDetail> {
  const response = await fetch(`/api/reviews/${runId}`)
  if (!response.ok) await _throwFromResponse(response)
  return (await response.json()) as ReviewRunDetail
}

export async function deleteReview(runId: string): Promise<void> {
  const response = await fetch(`/api/reviews/${runId}`, { method: 'DELETE' })
  if (response.status === 204) return
  await _throwFromResponse(response)
}
