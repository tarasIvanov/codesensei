# Feature Specification: PR Review MVP (diff-only, no retrieval)

**Feature Branch**: `003-pr-review-mvp`
**Created**: 2026-05-17
**Status**: Draft
**Input**: User description: "PR review MVP — приймає unified diff (raw text) або GitHub PR URL, повертає структуровані findings (file, line, severity, message, optional suggestion) через сконфігурений LLMProvider з feature 002. Без RAG/retrieval — review базується лише на самому diff. Frontend сторінка /review з textarea для diff або input для PR URL та рендером findings. Endpoint POST /api/review синхронний (без черги). Великі diff > ліміту відхиляються 413. JSON output від LLM валідується; невалідний JSON → 502 ProviderError."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Review pasted unified diff (Priority: P1)

A reviewer (developer using CodeSensei locally) has a unified diff in their clipboard (e.g. from `git diff main..feature` or a downloaded `.patch` file) and wants an automated first-pass review without sharing the file with a third party they don't control. They open the `/review` page, paste the diff into a textarea, click **Review**, and within a short wait see a structured list of findings — each tied to a specific file and line, tagged with a severity, written in plain English, and optionally including a concrete suggested change.

**Why this priority**: This is the smallest end-to-end product slice that delivers user value. It exercises the full pipeline (input → LLM call → parsed findings → rendered list) and proves the LLM provider abstraction from feature 002 is usable for real work. Everything else (PR URL fetching, RAG, async queue, GitHub integration) can be layered on top.

**Independent Test**: Paste a known-bad diff (e.g., a function with an obvious null-deref or hardcoded credential) into the textarea, press **Review**, and confirm the rendered findings list contains at least one item that names the right file path, the right (or nearby) line number, a non-empty message, and a severity label. Works without any network access to GitHub.

**Acceptance Scenarios**:

1. **Given** the reviewer is on the `/review` page and an LLM provider is configured (per feature 002), **When** they paste a valid unified diff under the size limit into the textarea and click **Review**, **Then** the UI shows a loading state, then renders a list of findings each displaying file path, line number, severity, message, and (when present) a suggested change.
2. **Given** the reviewer pastes an empty or non-diff blob into the textarea, **When** they click **Review**, **Then** the UI shows a validation error explaining that a unified diff is required and the request is not sent to the backend.
3. **Given** the LLM returns no findings (the diff looks clean), **When** the response renders, **Then** the UI shows an explicit "no issues found" empty state rather than a blank panel, and the verdict is conveyed plainly.

---

### User Story 2 - Review a GitHub PR by URL (Priority: P2)

The same reviewer wants to review a teammate's pull request without manually downloading the diff. They paste a GitHub PR URL (e.g. `https://github.com/owner/repo/pull/42`) into a URL input on the `/review` page and click **Review**. The system fetches the unified diff for that PR, then runs the same review pipeline as Story 1 and renders findings.

**Why this priority**: Removes a friction step (manual diff export) and aligns the product with how engineers actually consume PRs. Depends on Story 1's pipeline being in place but adds only a fetch step, so it lands second.

**Independent Test**: With a valid GitHub PAT configured, paste a public PR URL into the URL input, click **Review**, and confirm the rendered findings reference real files from that PR's diff. The textarea path remains independently usable (Story 1 is not broken by adding Story 2).

**Acceptance Scenarios**:

1. **Given** a valid GitHub PR URL is entered and the system has GitHub credentials configured, **When** the reviewer clicks **Review**, **Then** the system fetches the PR's unified diff, runs the review, and renders findings exactly as in Story 1.
2. **Given** the URL is malformed (not a recognizable PR URL), **When** the reviewer clicks **Review**, **Then** the UI shows a validation error and no fetch is attempted.
3. **Given** the URL is well-formed but the PR is private and credentials are missing or invalid, **When** the reviewer clicks **Review**, **Then** the UI shows a clear "could not fetch this PR — check GitHub credentials" error without exposing token values.
4. **Given** the URL is well-formed but the PR or repository does not exist (404), **When** the reviewer clicks **Review**, **Then** the UI shows a clear "PR not found" error.

---

### User Story 3 - Graceful handling of oversized or malformed input (Priority: P3)

A reviewer accidentally pastes a very large diff (e.g., from a refactor touching hundreds of files), or the LLM returns output that doesn't conform to the expected findings shape. The system should fail fast and tell the reviewer what to do, rather than silently truncating, retrying forever, or showing a stack trace.

**Why this priority**: Hardens the MVP against the two most likely failure modes once Stories 1–2 work. Lower priority because the system is still useful without it (reviewers can avoid oversized diffs manually), but required before any external user touches it.

**Independent Test**: Submit a diff larger than the configured size limit and confirm the UI shows a clear "diff too large — try a smaller change" message. Separately, mock the LLM to return invalid output and confirm the UI shows a clear "the review service returned an unexpected response" message without crashing.

**Acceptance Scenarios**:

1. **Given** a diff exceeding the configured size limit is submitted, **When** the request reaches the backend, **Then** the backend rejects it with a "payload too large" response and the UI surfaces a clear, non-technical error message.
2. **Given** the LLM returns output that cannot be parsed into the findings shape, **When** the backend processes the response, **Then** the backend surfaces an upstream-provider error and the UI shows a clear "review service returned an unexpected response — try again" message; the reviewer's input is preserved so they can retry.
3. **Given** the LLM call times out or the provider is unreachable, **When** the backend processes the response, **Then** the UI shows a clear "review service is currently unavailable" message distinct from the "unexpected response" case.

---

### Edge Cases

- **Binary / non-text diffs**: Diffs that contain only binary file changes (e.g., images) carry no reviewable text. The system should accept them and return an empty findings list with a verdict noting that no textual changes were reviewable, rather than erroring.
- **Diff with only deletions or only renames**: Should be accepted; the LLM may legitimately have nothing to flag.
- **Very long lines inside the diff**: A single 5,000-character minified line should not break the renderer; the UI must wrap or truncate visually.
- **Multiple findings on the same line**: The UI must render them all (e.g., grouped under that line), not deduplicate silently.
- **Findings referencing a line not in the diff**: The renderer should still show the finding (since the LLM may comment on context lines) but mark it visually as "context" rather than "changed".
- **Reviewer clicks Review twice quickly**: The second click should not double-charge the LLM; the UI must disable the button while a review is in flight.
- **Non-UTF-8 bytes in the pasted diff**: The system should either accept and best-effort decode, or reject with a clear "diff is not valid UTF-8 text" message — not crash.

## Requirements *(mandatory)*

### Functional Requirements

**Input handling**

- **FR-001**: System MUST expose a single review page in the SPA at `/review` providing two input modes: a multi-line text area for pasting a unified diff and a single-line input for a GitHub PR URL.
- **FR-002**: System MUST accept either a unified-diff payload or a GitHub PR URL as input and MUST treat them as mutually exclusive for a given submission (one input mode active at a time).
- **FR-003**: System MUST validate that the diff input, when present, looks like a unified diff (contains at least one `diff --git` or `--- a/` / `+++ b/` header pair) before sending to the LLM, and MUST reject obviously-not-a-diff input with a user-facing validation error.
- **FR-004**: System MUST validate that the URL input, when present, matches a GitHub pull request URL shape (`https://github.com/{owner}/{repo}/pull/{number}`) before attempting to fetch.
- **FR-005**: System MUST enforce a server-side maximum payload size for the diff content and MUST reject submissions exceeding the limit with an explicit "payload too large" response that the UI translates into a user-facing message.

**Review pipeline**

- **FR-006**: System MUST send the diff (either pasted or fetched from GitHub) to the configured LLM provider exposed by feature 002, without performing any retrieval, embedding lookup, or repository cloning.
- **FR-007**: System MUST instruct the LLM to return findings in a structured shape with these fields per finding: `file` (string, path inside the diff), `line` (integer or null), `severity` (one of a fixed set: `blocker`, `major`, `minor`, `nit`), `message` (string), and optional `suggestion` (string with a concrete proposed change).
- **FR-008**: System MUST parse the LLM response into the structured shape and MUST reject responses that do not conform (missing required fields, unknown severity values, non-integer line numbers) by treating them as an upstream-provider error rather than silently dropping them.
- **FR-009**: System MUST handle the case where the LLM legitimately reports no findings (clean diff) by returning a success response with an empty findings list and a clear verdict, distinguishable from an error.

**PR URL fetching**

- **FR-010**: When the input is a GitHub PR URL, the system MUST fetch the PR's unified diff from GitHub using the credentials configured at deploy time, and MUST surface authentication / not-found errors as distinct, user-facing categories (not a generic 500).
- **FR-011**: System MUST NOT log or surface the configured GitHub credentials in any response, error message, or log line.

**API surface**

- **FR-012**: System MUST expose a single synchronous backend endpoint, `POST /api/review`, that accepts either `{diff: string}` or `{pr_url: string}` and returns the structured findings list together with an overall verdict.
- **FR-013**: The endpoint MUST return distinct, machine-readable error categories for: invalid input, payload too large, GitHub fetch failure (auth/not-found/other), upstream provider unavailable (timeout/connection), upstream provider returned malformed output, and internal error.
- **FR-014**: The endpoint MUST be synchronous (no job queue, no polling) for this MVP. Long-running requests are bounded by a server-side timeout shorter than typical client read timeouts.

**Frontend rendering**

- **FR-015**: The `/review` page MUST render the findings list grouped by file path, with each finding showing severity (visually distinguishable per severity level), line number, message, and — when provided — the suggested change formatted as a readable code block.
- **FR-016**: The `/review` page MUST show a clearly distinguished loading state while a review is in flight, disable the submit control to prevent duplicate submissions, and surface every backend error category with a human-readable message (no raw stack traces or JSON error blobs).
- **FR-017**: The `/review` page MUST preserve the reviewer's input across an error so that retrying does not require re-pasting the diff.

**Privacy & operational discipline**

- **FR-018**: System MUST NOT persist the submitted diff, the PR URL, the fetched diff, or any LLM response to any datastore as part of this feature (review is fire-and-forget; persistence belongs to a later feature).
- **FR-019**: System MUST log enough operational metadata (timestamp, provider name, request id, payload size, finding count, error category) to debug failures without including the diff content or any finding content in logs.

### Key Entities

- **ReviewRequest**: A single submission from the user. Holds either the pasted diff text or the GitHub PR URL (one of the two), and the implicit choice of configured LLM provider. Lives only for the duration of the request; not persisted.
- **Finding**: One reviewer comment produced by the LLM. Attributes: file path (string), line number (integer or null when the comment is general), severity (blocker / major / minor / nit), message (free text), suggestion (free text, optional).
- **ReviewResult**: The complete response to one `ReviewRequest`. Attributes: a verdict summary (e.g., "approve" / "request_changes" / "comment"), the ordered list of findings, the provider that generated the review, and the elapsed wall-clock time. Not persisted.
- **ReviewError**: A structured error category returned when the pipeline cannot produce a `ReviewResult`. Attributes: category (invalid_input / payload_too_large / github_fetch_failed / provider_unavailable / provider_malformed_output / internal), human-readable message, and optional retryability hint.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A reviewer can paste a typical pull-request diff (≤ 200 changed lines) and receive a rendered findings list in under 30 seconds on a default deployment with a remote LLM provider.
- **SC-002**: For diffs containing at least one obvious defect (e.g., hardcoded credential, off-by-one, missing null check), the system surfaces at least one corresponding finding that names the correct file and a line within ±3 lines of the actual defect, in at least 8 out of 10 manually curated test diffs.
- **SC-003**: 100% of LLM responses that fail to conform to the structured findings shape are surfaced to the user as a single, consistent "review service returned an unexpected response" error — never as a stack trace, blank screen, or partial rendering.
- **SC-004**: Submitting a diff above the configured size limit is rejected end-to-end (server response + UI message) in under 1 second, without any LLM call being made.
- **SC-005**: A reviewer can switch between input modes (paste diff ↔ paste PR URL) and complete a review using each mode without restarting the page session.
- **SC-006**: No submitted diff content, fetched diff content, finding content, or GitHub credential ever appears in server logs or in a persisted datastore as part of this feature.

## Assumptions

- The LLM provider abstraction delivered in feature 002 (`LLMProvider.chat`) is available and a provider is configured at deploy time; this feature is unusable until then but does not re-implement provider selection.
- Reviewers are technical users (engineers) running CodeSensei in a single-tenant, single-user local deployment; there is no auth, no per-user state, and no concurrency-control requirement beyond the obvious "don't double-submit while a request is in flight".
- "GitHub PR URL" means a public or private repo on `github.com` (Enterprise / self-hosted GitHub instances are out of scope for this MVP).
- GitHub credentials, when needed, are provided at deploy time as a single token; per-user GitHub OAuth is out of scope.
- Diff size limit is set to a value that comfortably fits typical PRs (single-to-double-digit changed files) but rejects monster refactors; the exact byte value is an operational tuning concern, not a product decision, and lives in configuration.
- "Findings" are advisory; the system makes no attempt to post comments back to GitHub, block merges, or otherwise act on them — rendering in CodeSensei's own UI is the only delivery mechanism in this MVP.
- The LLM call is synchronous and bounded by a server-side timeout shorter than the client's default read timeout; queue-based async review is deferred to a later feature.
- Review quality is bounded by what the LLM can infer from the diff alone (no surrounding repo context). Improving review depth via repository indexing is explicitly the scope of a later feature, not this one.
- The system is single-user; rate limiting, abuse prevention, and audit logging are not in scope for this MVP.
