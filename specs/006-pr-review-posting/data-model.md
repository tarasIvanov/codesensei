# Phase 1 — Data Model: PR Review Comment Posting

**No persisted schema is introduced by this feature.** No new tables, no new migration, no new SQL types. The model below is the in-memory wire shape — pydantic models on the backend and TypeScript interfaces on the frontend.

---

## Entities

### `PostReviewRequest` (wire input — backend)

| Field | Type | Required | Validation |
|-------|------|:--------:|------------|
| `review_result` | `ReviewResult` (existing model from `codesensei.review.schema`) | ✓ | Must validate per the existing schema; verdict in {`approve`, `request_changes`, `comment`}; findings is a non-empty list of `Finding` instances. |
| `pr_url` | `str` | ✓ | Matches `^https://github\.com/[^/\s]+/[^/\s]+/pull/\d+$` (re-uses the regex already present in `codesensei.review.schema._PR_URL_RE`). Parsed into `(owner, repo, number)` by `posting.service`. Validation failure → `ReviewError(INVALID_INPUT)`. |
| `event` | `Literal["COMMENT", "REQUEST_CHANGES", "APPROVE"]` | ✓ | The caller must commit to an event. Server does not silently default — it is the *frontend* that pre-fills the verdict-derived default and lets the reviewer change it before sending. |

Pydantic config: `extra="forbid"` (a typo client-side becomes a 400 rather than a silent ignore).

### `PostedReviewReceipt` (wire output — backend)

| Field | Type | Notes |
|-------|------|-------|
| `review_id` | `int` | GitHub's `id` from the response body — large positive integer. |
| `html_url` | `str` | GitHub's `html_url` — opens the new review on the PR's "Files changed" tab. Used by the frontend success state. |
| `posted_at` | `datetime` (UTC ISO-8601) | Server-side timestamp. Not the GitHub `submitted_at` — that field is sometimes null right after creation; we record the moment our request returned 200. |
| `comment_count` | `int` | Number of inline comments actually attached to the posted review, *after* the 50-cap and *after* any 422-fallback. Zero is a legitimate value (body-only review). |
| `attempted_calls` | `int` | 1 on the happy path, 2 if the 422-fallback ran. Diagnostic field, used by the structured log and by tests; not surfaced in the UI. |

Pydantic config: `extra="ignore"` (forward-compatible with any GitHub response fields we have not modelled).

### `_InlineComment` (internal — backend)

| Field | Type | Notes |
|-------|------|-------|
| `path` | `str` | File path from the finding, repo-relative. |
| `side` | `Literal["RIGHT"]` | Always `RIGHT` — see R3. Constant, not a field the mapper computes. |
| `line` | `int` | The finding's `line`, after validation that it is ≥ 1. |
| `body` | `str` | Markdown body rendered by the mapper template (R3). |

This struct is the intermediate the mapper produces and the client serialises into GitHub's request body. It is **not** part of any wire contract.

### `ReviewError` — extended category set

The existing `codesensei.review.errors.ReviewErrorCategory` enum gains five new members:

| Category | HTTP | `retryable` | Surfaces when |
|----------|:----:|:-----------:|---------------|
| `github_auth_failed` | 401 | false | GitHub 401 or 403 on the post call. Message names the missing permission. |
| `github_pr_not_found` | 404 | false | GitHub 404. |
| `github_review_rejected` | 502 | false | GitHub 422 still failing after the body-only fallback, or the *first* 422 if its body indicates a non-position structural problem. Message contains the raw GH error body. |
| `github_api_unavailable` | 502 | true | GitHub 5xx, network error, or httpx timeout. |
| `github_rate_limited` | 429 | true | GitHub 429. Envelope carries `retry_after_seconds` derived from `Retry-After`. |

`SETTINGS_LOCKED` (existing, HTTP 503) is *reused* — no new category — when the PAT is missing from `app_settings`. `INVALID_INPUT` (existing, HTTP 400) is *reused* when the PR URL is malformed.

The `to_envelope()` shape stays:

```json
{"error": {"category": "<value>", "message": "<human>", "retryable": <bool>}}
```

For `github_rate_limited` only, the envelope is augmented with `"retry_after_seconds": <int>` at the *envelope* level (alongside `error`), so the frontend's typed error parser can read it without sniffing the message text.

---

## Frontend mirrors

`frontend/src/api/posting.ts` defines:

```ts
export type PostReviewInput = {
  review_result: ReviewResult;   // imported from api/review
  pr_url: string;
  event: "COMMENT" | "REQUEST_CHANGES" | "APPROVE";
};

export type PostedReviewReceipt = {
  review_id: number;
  html_url: string;
  posted_at: string;             // ISO-8601
  comment_count: number;
  attempted_calls: number;
};

export type PostReviewErrorCategory =
  | "invalid_input"
  | "settings_locked"
  | "github_auth_failed"
  | "github_pr_not_found"
  | "github_review_rejected"
  | "github_api_unavailable"
  | "github_rate_limited"
  | "internal";

export class PostReviewError extends Error {
  category: PostReviewErrorCategory;
  retryable: boolean;
  retryAfterSeconds?: number;   // only present for github_rate_limited
}
```

---

## Validation rules summary

- The PR URL regex is *the same* one used by `ReviewRequest.pr_url` — there is only one valid URL shape in the system.
- `event` must be exactly one of the three values; lower-case or mixed-case input is a 400 (`event` is a Literal, pydantic does not coerce).
- `review_result.findings` may be empty (a body-only review is legal: verdict + summary, no findings to discuss).
- A finding with `line == 0` or `line < 0` is treated as locationless and demoted to the body bullet list (defensive — the parser already coerces these to None, but the mapper rechecks).

## State transitions

There are none. This feature is stateless on the backend (no persisted state), and the frontend's single-use lock is a per-component-instance UI state, not an entity lifecycle.
