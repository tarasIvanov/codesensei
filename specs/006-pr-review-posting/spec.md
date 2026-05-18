# Feature Specification: PR Review Comment Posting

**Feature Branch**: `006-pr-review-posting`
**Created**: 2026-05-17
**Status**: Draft
**Input**: User description: "006 PR review comment posting — closing the loop: take the review result currently rendered only on /review and publish it back to the GitHub PR as an official review with inline comments via the GitHub Reviews API."

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Post review to a GitHub PR (Priority: P1)

As a reviewer who has just generated a review against a GitHub PR URL, I can publish that review back to the PR with one click so the PR author sees the findings as native GitHub review comments instead of having to switch tools.

**Why this priority**: This is the entire point of the feature. Without it the review result is read-only on the /review page; with it CodeSensei becomes a participant in the team's actual code-review workflow on GitHub. Stories 2 and 3 only matter if Story 1 works.

**Independent Test**: Run a review against a real public PR URL belonging to a repo to which the configured bot account has push access. From the /review page, choose an event type and click "Post to GitHub". Verify that a new review appears on the PR with the expected verdict, summary body, and per-finding inline comments, and that the response carries the GitHub review id and HTML URL.

**Acceptance Scenarios**:

1. **Given** a successful review result with at least one finding that has a file path and line number, and a configured bot token in the Settings store, **When** the reviewer clicks "Post to GitHub" with event `Comment`, **Then** a single GitHub review is created on the target PR, each located finding appears as an inline comment on the correct file/line, and the response returns `{review_id, html_url, posted_at, comment_count}`.
2. **Given** a review result whose findings have no file/line location, **When** the review is posted, **Then** those findings appear inside the top-level review body as a bullet list rather than as inline comments, and `comment_count` reports only the inline-comment count.
3. **Given** the original /review request was driven by a PR URL (not a raw diff paste), **When** the result is displayed, **Then** the "Post to GitHub" action is offered and pre-selects an event derived from the verdict (`approve→APPROVE`, `request_changes→REQUEST_CHANGES`, `comment→COMMENT`); the reviewer may override the choice before posting.
4. **Given** a review has already been posted from the current /review result, **When** the reviewer looks at the page, **Then** the "Post to GitHub" control is disabled with a hint linking to the posted review's GitHub URL, so the same result cannot be double-posted by accident.

---

### User Story 2 — Predictable error handling (Priority: P2)

As a reviewer trying to post a review, I get a clear, actionable error when something goes wrong (bad token, missing PR, GitHub rejected the comment positions, GitHub is down, rate limit) and a retry control when retrying is meaningful.

**Why this priority**: Posting touches an external system that fails in many ways. Without predictable error envelopes the reviewer cannot tell "fix the token" from "GitHub is down right now". This is what makes Story 1 reliable in practice.

**Independent Test**: Trigger each failure path (revoke the bot token; target a non-existent PR; force GitHub to 422 by referencing a line outside the diff; simulate 503/timeout; simulate 429 with `Retry-After`; clear the bot token from Settings) and verify the response category, HTTP code, retryable flag, and UI affordance match the contract below.

**Acceptance Scenarios**:

1. **Given** the configured bot token is missing the required PR-write permission, **When** the post is attempted, **Then** the system returns a 401-level error with category `github_auth_failed` and a message naming the missing permission, and the UI shows the error without a retry button.
2. **Given** the PR URL points to a repository or pull number the bot cannot see, **When** the post is attempted, **Then** the system returns a 404-level error with category `github_pr_not_found`, the UI offers no retry.
3. **Given** the review contains an inline comment whose `line` is no longer present in the PR's current diff, **When** the post is attempted, **Then** the system retries the call once with only the summary body (no inline comments) so the review is still recorded; if GitHub still rejects, a `github_review_rejected` error is returned that includes the raw GitHub error body.
4. **Given** GitHub responds with a 5xx or the request times out, **When** the post is attempted, **Then** the system returns a 502-level error with category `github_api_unavailable` and `retryable=true`, and the UI exposes a retry button that re-submits the same payload.
5. **Given** GitHub responds with 429 and a `Retry-After` header, **When** the post is attempted, **Then** the system surfaces `github_rate_limited` with `retryable=true` and a `retry_after_seconds` value the UI displays in the error banner.
6. **Given** no bot token is configured at all in the Settings store, **When** the post is attempted, **Then** the system returns `settings_locked` (503) with a message instructing the reviewer to open Settings and add the token; the UI links to the Settings page.

---

### User Story 3 — "Post to GitHub" control on /review (Priority: P3)

As a reviewer reading the rendered findings, I can pick the review event type (Comment / Request changes / Approve) and post the review without leaving the page.

**Why this priority**: The backend endpoint from Story 1 is usable from `curl`, but the human workflow lives on /review. This story closes the UX gap.

**Independent Test**: Generate a review from a PR URL on /review. Verify the post control appears, the event radio group defaults to the verdict-derived option, switching it is allowed, clicking it shows a spinner during the call, success replaces the control with a "Posted ✓" badge linking to the GitHub review, and a server error shows an inline banner that mirrors the retryable flag.

**Acceptance Scenarios**:

1. **Given** a review result derived from a PR URL is on screen, **When** the page renders, **Then** a panel labelled "Post to GitHub" is shown with three radio options (Comment, Request changes, Approve) and a primary "Post to GitHub" button.
2. **Given** the same review result was derived from a raw diff paste (no PR URL), **When** the page renders, **Then** the "Post to GitHub" panel is hidden because there is no target PR.
3. **Given** the reviewer clicks "Post to GitHub", **When** the call is in flight, **Then** the button shows a loading state and is non-interactive until the call resolves.
4. **Given** the call succeeds, **When** the response is received, **Then** the panel is replaced by a confirmation linking to the posted review on GitHub, and the link opens in a new tab.

---

### Edge Cases

- Reviewer clicks "Post to GitHub" twice in quick succession (double-submit) — the UI must lock the control after the first click so only one review is created on GitHub.
- The configured bot token works but is read-only on the target repo — surfaces as `github_auth_failed` (the missing-permission branch), not as a generic 500.
- The PR is from a fork — GitHub rejects inline comments on forks without the right permission; covered under `github_review_rejected` with the same fallback as the line-not-in-diff path.
- The review carries more findings than GitHub will accept in one review payload — the system caps inline comments at 50 per posted review; anything beyond the cap is appended to the review body as a bullet list with the same `severity / category / message / suggestion` format.
- The same review result is posted twice from two different browser tabs — the backend has no audit table, so it cannot reject duplicates; the UI prevents this within a single page-view but two tabs can legally create two GitHub reviews. Documented as accepted behaviour.
- The PR URL is malformed (not `https://github.com/{owner}/{repo}/pull/{n}`) — returns `invalid_input` (400) before any GitHub call.
- The Settings store is reachable but the bot token decrypt fails (bad MASTER_KEY) — returns `settings_locked` (503) so the reviewer is sent to Settings.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST expose an endpoint that accepts a previously-generated review result, a target GitHub PR URL, and an explicit review event (`COMMENT`, `REQUEST_CHANGES`, or `APPROVE`).
- **FR-002**: The system MUST publish exactly one GitHub review per accepted request, combining a top-level review body and any inline comments derived from the findings, in a single call to the GitHub Reviews API.
- **FR-003**: The system MUST map each finding that has both a file path and a line number to an inline review comment on the new (right-hand) side of the diff. The comment body MUST contain the finding's severity, category, message and (if present) suggestion, formatted as Markdown.
- **FR-004**: The system MUST place findings that have no file path or no line number into the top-level review body as a bullet list, rendered with the same severity/category/message/suggestion fields.
- **FR-005**: The system MUST cap the number of inline review comments at 50 per posted review; any findings beyond the cap MUST be appended to the top-level review body bullet list instead of being silently dropped.
- **FR-006**: The system MUST suggest a default review event based on the result's verdict (`approve→APPROVE`, `request_changes→REQUEST_CHANGES`, `comment→COMMENT`) but MUST honour the event explicitly supplied by the caller without override.
- **FR-007**: The system MUST authenticate to GitHub using the encrypted bot token stored in the existing Settings store; it MUST NOT introduce any new persistent secret-storage surface.
- **FR-008**: If the Settings store contains no usable bot token, the system MUST refuse the request with a `settings_locked` error before contacting GitHub.
- **FR-009**: On a successful post the system MUST return the GitHub review id, the GitHub HTML URL of the posted review, the timestamp it was posted, and the count of inline comments actually attached.
- **FR-010**: On a GitHub 401 or 403 the system MUST return error category `github_auth_failed`; the user-visible message MUST name the GitHub permission the token is missing.
- **FR-011**: On a GitHub 404 the system MUST return error category `github_pr_not_found`.
- **FR-012**: On a GitHub 422 indicating a comment position outside the diff, the system MUST retry the call exactly once with no inline comments (summary body only); if GitHub still rejects, it MUST return `github_review_rejected` and include GitHub's raw error body in the human message.
- **FR-013**: On a GitHub 5xx or a request timeout the system MUST return `github_api_unavailable` with `retryable=true`.
- **FR-014**: On a GitHub 429 the system MUST return `github_rate_limited` with `retryable=true` and surface the `Retry-After` value (in seconds) to the caller.
- **FR-015**: If the supplied PR URL cannot be parsed as a standard GitHub PR URL, the system MUST return `invalid_input` (no GitHub call attempted).
- **FR-016**: The system MUST emit one structured log line per attempted post (success or failure), carrying at least: the PR URL, the chosen event, the resolved comment count, the elapsed time in milliseconds, and the GitHub review id if applicable.
- **FR-017**: The system MUST NOT persist posted-review history locally. GitHub is the source of truth; the local backend keeps no audit table.
- **FR-018**: The /review page MUST show the "Post to GitHub" control only when the current review result is associated with a PR URL the reviewer fetched the diff from; for raw-diff reviews the control MUST NOT appear.
- **FR-019**: The /review page MUST disable the "Post to GitHub" control after a successful post from the same loaded review, and surface a link to the GitHub review URL in its place, until the page reloads or a new review is generated.
- **FR-020**: For retryable errors the /review page MUST offer a retry control that re-submits the exact same payload; for non-retryable errors it MUST NOT offer a retry.

### Key Entities

- **Post Review Request**: composed of an already-validated review result (verdict + ordered findings), a target PR identifier (owner, repo name, PR number) derived from a PR URL, and an explicit review event chosen by the reviewer.
- **Inline Review Comment**: a derivation of one finding into the structured shape GitHub accepts — file path relative to the repo root, side (always "right"), line number in the new file, body text rendered from the finding's fields.
- **Posted Review Receipt**: the response returned to the caller once GitHub has accepted the review — the GitHub review id, its HTML URL, the server-side timestamp it was posted at, and the number of inline comments actually attached (after cap and any 422 fallback).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A reviewer can publish a generated review to GitHub in fewer than three interactions on the /review page (open the panel, choose event, click post).
- **SC-002**: On the happy path the end-to-end post completes in under 5 seconds for reviews with up to 50 findings, measured from the click on "Post to GitHub" to the success badge appearing.
- **SC-003**: 100% of generated findings that carry both a file path and a line number reach the posted GitHub review — either as inline comments (under the 50-cap) or as bullet entries inside the review body (above the cap or after the 422 fallback). No findings are silently dropped.
- **SC-004**: Each of the seven defined failure paths (`invalid_input`, `settings_locked`, `github_auth_failed`, `github_pr_not_found`, `github_review_rejected`, `github_api_unavailable`, `github_rate_limited`) produces a distinct error category in the response, so the UI can render a different remediation hint for each.
- **SC-005**: After a successful post, the reviewer can navigate to GitHub from the /review page in exactly one click; the link opens the new review on the PR's "Files changed" tab.
- **SC-006**: The /review page reliably prevents accidental double-post within a single page view (verified by clicking the action multiple times in succession in a manual smoke test — only one GitHub review is created).
- **SC-007**: The feature does not introduce any new persisted user-visible state in the database; an end-to-end smoke test confirms no new tables, no new rows, and no schema migration is shipped.

## Assumptions

- The user has already configured a working GitHub bot token in the existing Settings store (feature 004). This feature consumes that token but does not own the configuration UX.
- The target PR is on `github.com`. GitHub Enterprise hosts are out of scope for this iteration.
- Authorisation model on GitHub side is whatever the bot account's fine-grained PAT grants; the system does not attempt to enrich or downgrade those permissions.
- All review event semantics (Comment / Request changes / Approve) follow GitHub's existing behaviour; the system does not redefine what "approve" means.
- A review result is the unit of posting. Partial or finding-by-finding posting is out of scope.
- The reviewer is the sole intended audience of error messages; messages are intended to be read by an engineer, not a non-technical operator.
- For the thesis-scope cap of 50 inline comments, no PR has been observed in normal use that exceeds it; the cap exists to guarantee a bounded payload, not to throttle legitimate reviews.

## Out of Scope

- Replying to existing review threads, marking comments resolved, or interacting with prior reviews on the same PR.
- Editing or deleting a previously posted review through CodeSensei.
- Multi-token / per-repository token rotation (one bot token, one Settings store entry).
- Persistent audit log of posted reviews inside CodeSensei.
- A webhook back-channel where GitHub events update CodeSensei state.
- Rendering GitHub "suggested code change" blocks (\`\`\`suggestion … \`\`\`); suggestions are posted as plain Markdown for now.
- Supporting any non-`github.com` host (GitHub Enterprise, GitLab, Bitbucket).
- Concurrent / parallel posting of the same review from two browser tabs is allowed at the protocol level — CodeSensei takes no lock.
