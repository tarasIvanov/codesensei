import type { ReviewResult } from './review'

export type GitHubEvent = 'COMMENT' | 'REQUEST_CHANGES' | 'APPROVE'

export type PostReviewErrorCategory =
  | 'invalid_input'
  | 'settings_locked'
  | 'github_auth_failed'
  | 'github_pr_not_found'
  | 'github_review_rejected'
  | 'github_api_unavailable'
  | 'github_rate_limited'
  | 'internal'

export interface PostReviewInput {
  review_result: ReviewResult
  pr_url: string
  event: GitHubEvent
}

export interface PostedReviewReceipt {
  review_id: number
  html_url: string
  posted_at: string
  comment_count: number
  attempted_calls: number
}

export class PostReviewError extends Error {
  category: PostReviewErrorCategory
  retryable: boolean
  retryAfterSeconds?: number

  constructor(
    category: PostReviewErrorCategory,
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

const FALLBACK_MESSAGE_FOR_CATEGORY: Record<PostReviewErrorCategory, string> = {
  invalid_input: 'Invalid request — re-run the review and try again.',
  settings_locked:
    'GitHub token not configured. Open Settings to add the codesensei-bot PAT.',
  github_auth_failed:
    'PAT invalid or missing permissions (need pull_requests:write).',
  github_pr_not_found:
    'GitHub could not find this PR — check the URL and the bot’s repo access.',
  github_review_rejected: 'GitHub refused this review.',
  github_api_unavailable: 'GitHub is unreachable. Try again.',
  github_rate_limited: 'GitHub rate limit hit.',
  internal: 'Unexpected server error.',
}

export async function postReview(
  input: PostReviewInput,
): Promise<PostedReviewReceipt> {
  const response = await fetch('/api/review/post', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  })
  if (response.ok) {
    return (await response.json()) as PostedReviewReceipt
  }
  let category: PostReviewErrorCategory = 'internal'
  let message = FALLBACK_MESSAGE_FOR_CATEGORY.internal
  let retryable = false
  let retryAfterSeconds: number | undefined
  try {
    const parsed = (await response.json()) as {
      error?: {
        category?: PostReviewErrorCategory
        message?: string
        retryable?: boolean
      }
      retry_after_seconds?: number
    }
    if (parsed?.error?.category) {
      category = parsed.error.category
      message = parsed.error.message || FALLBACK_MESSAGE_FOR_CATEGORY[category]
      retryable = Boolean(parsed.error.retryable)
    }
    if (typeof parsed?.retry_after_seconds === 'number') {
      retryAfterSeconds = parsed.retry_after_seconds
    }
  } catch {
    // Body wasn't JSON — fall back to defaults above.
  }
  throw new PostReviewError(category, message, retryable, retryAfterSeconds)
}
