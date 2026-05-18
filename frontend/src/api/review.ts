export type Severity = 'blocker' | 'major' | 'minor' | 'nit'
export type Verdict = 'approve' | 'request_changes' | 'comment'

export type ReviewErrorCategory =
  | 'invalid_input'
  | 'payload_too_large'
  | 'github_fetch_failed'
  | 'provider_unavailable'
  | 'provider_malformed_output'
  | 'settings_locked'
  | 'repo_not_ready'
  | 'embedding_mismatch'
  | 'internal'

export interface TemporalEntry {
  commit_sha: string
  short_sha: string
  author_email: string
  author_date: string
  subject: string
  hunk_lines_changed: number
}

export interface Finding {
  file: string
  line: number | null
  severity: Severity
  message: string
  suggestion?: string | null
  temporal_context?: TemporalEntry[] | null
}

export interface ReviewResult {
  verdict: Verdict
  findings: Finding[]
  provider: string
  elapsed_ms: number
  context_files?: string[] | null
}

export interface ReviewBody {
  diff?: string
  pr_url?: string
  repo_id?: string | null
}

export class ReviewApiError extends Error {
  category: ReviewErrorCategory
  retryable: boolean

  constructor(category: ReviewErrorCategory, message: string, retryable: boolean) {
    super(message)
    this.category = category
    this.retryable = retryable
  }
}

const FALLBACK_MESSAGE_FOR_CATEGORY: Record<ReviewErrorCategory, string> = {
  invalid_input: 'The input could not be reviewed. Check the diff or PR URL and try again.',
  payload_too_large: 'The diff is too large for a single review. Try a smaller change.',
  github_fetch_failed:
    'Could not fetch this PR from GitHub. Check the URL and the configured token.',
  provider_unavailable: 'The review service is currently unavailable. Try again.',
  provider_malformed_output:
    'The review service returned an unexpected response. Try again.',
  settings_locked:
    'Settings storage is locked — set MASTER_KEY before saving credentials.',
  repo_not_ready:
    'The selected repository is still being indexed. Wait until it is ready and retry.',
  embedding_mismatch:
    'This repository was indexed with a different embedding provider/model than the active one. Re-index the repository or revert the provider change.',
  internal: 'Unexpected server error.',
}

export async function runReview(body: ReviewBody): Promise<ReviewResult> {
  const payload: Record<string, unknown> = {}
  if (body.diff !== undefined) payload.diff = body.diff
  if (body.pr_url !== undefined) payload.pr_url = body.pr_url
  if (body.repo_id) payload.repo_id = body.repo_id
  const response = await fetch('/api/review', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (response.ok) {
    return (await response.json()) as ReviewResult
  }
  let category: ReviewErrorCategory = 'internal'
  let message = FALLBACK_MESSAGE_FOR_CATEGORY.internal
  let retryable = false
  try {
    const parsed = (await response.json()) as {
      error?: { category?: ReviewErrorCategory; message?: string; retryable?: boolean }
    }
    if (parsed?.error?.category) {
      category = parsed.error.category
      message = parsed.error.message || FALLBACK_MESSAGE_FOR_CATEGORY[category]
      retryable = Boolean(parsed.error.retryable)
    }
  } catch {
    // Body wasn't JSON — fall back to defaults above.
  }
  throw new ReviewApiError(category, message, retryable)
}
