export type Severity = 'blocker' | 'major' | 'minor' | 'nit'
export type Verdict = 'approve' | 'request_changes' | 'comment'

export type ReviewErrorCategory =
  | 'invalid_input'
  | 'payload_too_large'
  | 'github_fetch_failed'
  | 'provider_unavailable'
  | 'provider_malformed_output'
  | 'internal'

export interface Finding {
  file: string
  line: number | null
  severity: Severity
  message: string
  suggestion?: string | null
}

export interface ReviewResult {
  verdict: Verdict
  findings: Finding[]
  provider: string
  elapsed_ms: number
}

export interface ReviewBody {
  diff?: string
  pr_url?: string
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
  internal: 'Unexpected server error.',
}

export async function runReview(body: ReviewBody): Promise<ReviewResult> {
  const response = await fetch('/api/review', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
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
