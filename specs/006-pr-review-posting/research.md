# Phase 0 — Research: PR Review Comment Posting

All architectural unknowns from the spec resolved against GitHub's public REST documentation, the existing codebase, ADR-006, and the Constitution. Each entry is in the canonical Decision / Rationale / Alternatives format.

---

## R1 — GitHub Reviews API endpoint shape and semantics

**Decision**: Use `POST /repos/{owner}/{repo}/pulls/{n}/reviews` with `application/vnd.github+json`, `X-GitHub-Api-Version: 2022-11-28`, `Authorization: Bearer <PAT>`. Body shape: `{event: "COMMENT"|"REQUEST_CHANGES"|"APPROVE", body: <markdown>, comments: [{path, side: "RIGHT", line, body}]}`. Response 200 returns `{id, html_url, submitted_at, ...}`. One request creates one review with all inline comments attached atomically — there is no need to call `POST /pulls/{n}/comments` per finding.

**Rationale**: The Reviews-API call is the only GitHub endpoint that creates a unified review with inline comments in a single transaction. The per-comment endpoint (`POST /pulls/{n}/comments`) produces *standalone* review comments that are not grouped under one review, which would scatter findings across the PR's "Conversation" tab and lose the verdict-level signal carried by `event`. Atomicity is the second reason — one HTTP call means we cannot end up in a partial-post state where some findings landed and others did not.

**Alternatives considered**:
- *Per-comment API* (`POST /pulls/{n}/comments` for each finding + a `POST /reviews` with empty comments): rejected. Loses atomicity, multiplies the rate-limit blast radius, fragments the UX on GitHub's side.
- *GraphQL `addPullRequestReview`*: rejected for parity with the existing REST client used in `codesensei.review.github_diff` — keeping one transport keeps the code shape consistent and avoids a second authentication path.
- *GitHub App as authoring identity*: explicitly out of scope per ADR-006.

---

## R2 — Authentication path

**Decision**: Read the PAT through `codesensei.settings_store.store.get_setting("GITHUB_TOKEN")` exactly as `codesensei.review.github_diff` already does. If the call returns `None`, refuse the request with `ReviewError(SETTINGS_LOCKED, …)` *before* any outbound HTTP — preserving the exact behaviour `/api/review` exhibits when a PAT is missing.

**Rationale**: ADR-008 (the Settings store) is the single authorised secret-storage surface and ADR-006 names the `codesensei-bot` fine-grained PAT as the canonical posting credential. There is no second token to introduce, no per-repo PAT, no rotation logic. Re-using the existing path means the settings-update flow (clear PAT → cache miss → re-read on next call) already covers this feature without modification.

**Alternatives considered**:
- *New `GITHUB_BOT_TOKEN` key separate from the diff-fetch token*: rejected. The same bot account legitimately serves both reads and writes; introducing a second row would create a "two-out-of-sync tokens" failure mode we'd then have to test against.
- *Env-only secret*: rejected because Constitution III demands Settings-UI configurability.

---

## R3 — Inline-comment payload shape

**Decision**: Each finding with both `file` and `line` becomes `{path: finding.file, side: "RIGHT", line: finding.line, body: <rendered markdown>}`. Markdown body template:

```
**{severity}** ({category}): {message}

_Suggestion_: {suggestion}
```

Where `category` is the existing Finding category (mapped from the LLM output by the parser in feature 003), and the `_Suggestion_` paragraph is omitted when `suggestion` is null. Severity is rendered in bold so the GitHub-side eye can scan one severity per comment without expanding it.

**Rationale**: GitHub renders Markdown faithfully in review-comment bodies. The "Severity (Category): message" ordering matches the on-screen rendering in `/review` so the reviewer reads the same words in two places. `side: "RIGHT"` is the *new* file in a diff; we never annotate the deleted side because there is no useful artefact to comment on a line that no longer exists.

**Alternatives considered**:
- *`start_line` + `line` multi-line comments*: rejected for V1 — would require the LLM to emit ranges, which it does not today. Single-line comments are unambiguous.
- *GitHub-flavoured suggestion blocks* (\`\`\`suggestion … \`\`\`): explicitly out of scope per the spec. The LLM's `suggestion` field is free-form natural language today, not a code-replacement diff.
- *HTML in the body*: rejected. GitHub Markdown is what every other tool emits; HTML would render but feel out-of-place in the UI.

---

## R4 — Locationless findings and the 50-cap overflow

**Decision**: Findings with no `file` or no `line` are rendered into the top-level review `body` as a bullet list with the same `**{severity}** ({category}): {message}` shape (with an indented `Suggestion` sub-bullet when present). The first 50 located findings become inline comments; located findings beyond the 50-cap join the same bullet list with an additional `({path}:{line})` suffix so the reviewer can still navigate to the location manually. The bullet list is preceded by a short verdict summary (`Verdict: REQUEST_CHANGES — 3 blocker, 7 major, 12 minor, 1 nit`).

**Rationale**: Two failure modes to defend against: (1) findings GitHub will not accept as inline (no file/line) — they cannot be silently dropped because the reviewer would not learn about them; (2) findings beyond the cap — same problem at a different threshold. The decision unifies both into "anything that cannot be inline goes into body as a bullet". Reviewer always sees every finding exactly once.

**Alternatives considered**:
- *Drop overflow with a warning header*: rejected — violates SC-003 ("100% of findings reach the posted review").
- *Multiple sequential reviews* (one per 50-finding batch): rejected — pollutes the PR with N reviews where the reviewer expects one, and breaks the one-button-click UX.
- *50-cap = configurable*: rejected for V1; the cap is documented in code and the spec, runtime knobs are deferred.

---

## R5 — Event-from-verdict mapping

**Decision**: Default event = `{approve → APPROVE, request_changes → REQUEST_CHANGES, comment → COMMENT}`. The mapping is a UI-only default; the backend honours whatever event the caller supplies without override. The frontend pre-selects the default and lets the reviewer change it freely before clicking post.

**Rationale**: Verdict already encodes intent. Honouring caller choice without override preserves the "reviewer is the boss" mental model — if the LLM said `request_changes` but the reviewer disagrees, posting as `COMMENT` is the right escape hatch. Forcing the verdict's event would create a "fight the tool" moment we want to avoid.

**Alternatives considered**:
- *Always `COMMENT` and force the human to escalate*: rejected — wastes the LLM's verdict signal.
- *Map `request_changes` → `COMMENT` to never block humans accidentally*: rejected — `REQUEST_CHANGES` is the exact GitHub semantic for "this PR is not OK to merge as is", which is what the LLM means.

---

## R6 — 422 fallback strategy

**Decision**: On the first `POST /reviews` call, if GitHub returns 422 with an error body that mentions a comment position (commonly `"pull_request_review_comment.path: <path> is invalid"` or "Line not part of the pull request diff"), retry exactly once with `comments: []` and the same `body` + `event`. If GitHub returns 422 again on the retry, raise `ReviewError(GITHUB_REVIEW_REJECTED, <raw GH body>)`. Any non-comment-position 422 (e.g. malformed `event`) skips the retry and raises directly.

**Rationale**: The "line not in diff" failure is genuinely transient on our side — it happens when the user's review was generated against an older snapshot of the PR diff than the one GitHub has now. The body-only fallback degrades gracefully: the verdict and the prose still reach the PR. Doing one retry rather than two preserves the FR-013 contract that this endpoint makes at most two outbound calls per user click. If the body-only retry also fails, we have hit a structural problem (bad token scope on private repo, fork-without-permission, GitHub bug) and the caller deserves the raw GH body to debug from.

**Alternatives considered**:
- *Drop the failed comment and retry with the rest*: rejected for V1 — the 422 body sometimes does not identify *which* comment is bad, and probing comment-by-comment costs O(N) extra GitHub calls.
- *Auto-relocate the comment to the closest in-diff line*: rejected — silent rewrites are a Constitution-IV-adjacent footgun; reviewer should know the line is gone.

---

## R7 — Rate-limit handling

**Decision**: A `429` response surfaces as `ReviewError(GITHUB_RATE_LIMITED, …, retryable=True)` with a `retry_after_seconds` field derived from `Retry-After` (defaulting to 60 if the header is missing). The backend never sleeps inside the request; the frontend reads `retry_after_seconds` and presents a "retry in N s" countdown next to the retry button.

**Rationale**: The bot account's primary rate limit (5 000 req/h for authenticated PATs) makes 429 a rare event in normal use; pushing the wait to the frontend keeps the request-thread budget unblocked and avoids the "spinner stuck for 60 seconds" UX. `Retry-After` is honoured because GitHub's documented behaviour is to populate it on 429.

**Alternatives considered**:
- *Sync backoff inside the request*: rejected — burns one request thread per waiting client and produces the worst-case spinner UX.
- *Background retry via arq*: rejected — over-engineering for an endpoint that should resolve in seconds or fail loud.

---

## R8 — httpx client configuration

**Decision**: One `httpx.AsyncClient(timeout=15.0)` per outbound call, instantiated inside an `async with`. No connection pooling across requests, no retry-transport, no `follow_redirects` (the Reviews-API endpoint never redirects). Status-code translation lives in `codesensei.posting.client`; the call site in `codesensei.posting.service` only catches the translated exceptions.

**Rationale**: Mirrors the established `codesensei.review.github_diff` pattern (timeout=10 s there; 15 s here because the request payload is larger when we attach many comments and we want a small safety margin without breaking SC-002's 5-second goal in the median case). Per-call client construction is fine at this traffic scale and keeps test setup simple (`respx` matches per route without needing to share a client instance across tests).

**Alternatives considered**:
- *Shared singleton client*: rejected for the test-isolation reasons above; we can revisit once posting traffic justifies pooling.
- *Built-in httpx retries on 5xx*: rejected — retries are a *caller* decision per FR-013; auto-retrying would double-bill GitHub against the bot's rate limit.

---

## R9 — Structured log line

**Decision**: One `github_review_posted` log line per attempted post, success or failure, with fields: `pr_url`, `event`, `comment_count`, `body_chars`, `elapsed_ms`, `review_id` (None on failure), `outcome` (`"ok"` / `"<category>"`), and `attempted_calls` (1 for happy path, 2 for body-only fallback). The line is emitted *after* the outbound call resolves, even on exception (try/finally), so the log always exists. The PAT is never logged. The review `body` content is never logged. The PR URL *is* logged (it is not a secret).

**Rationale**: Closes FR-016. Sufficient to debug rate-limit issues (count rows by `outcome=github_rate_limited` per minute), happy-path latency regressions (`elapsed_ms` distribution), and fallback frequency (`attempted_calls=2`) without ever capturing the comment payload itself.

**Alternatives considered**:
- *Log the comment count after the fallback too (as a separate field)*: rejected — `comment_count` is already the *posted* count, which is the meaningful number; recording the pre-fallback count adds noise.
- *Log structured GitHub error bodies on failure*: rejected — error bodies sometimes echo URL-path content and could leak PR titles; the human message in the `ReviewError` envelope is sufficient for UI rendering and is the right place to surface those details.

---

## R10 — Frontend single-use lock

**Decision**: The `PostToGitHubPanel` component owns a `posted` ref. On the first successful response, `posted` is set to the `{html_url, review_id, posted_at}` triple; the radio + submit are unmounted and replaced by a `Posted ✓` confirmation with a link to `html_url` that opens in a new tab. The lock resets only when a new `ReviewResult` arrives (either via re-running the review or navigating away and back). Concurrent double-click within the same in-flight call is prevented by an `inFlight` ref that disables the submit button while the request is pending.

**Rationale**: SC-006 demands single-page-view double-post prevention. The frontend-only lock is sufficient because the backend is intentionally non-idempotent (FR-017 forbids the only mechanism — an audit table — that could enforce backend-side de-dup). Two browser tabs can still both post; the spec documents this as accepted behaviour.

**Alternatives considered**:
- *Backend de-dup via an in-memory cache of the (pr_url, review_hash) tuple*: rejected — adds stateful behaviour to an endpoint we've sworn off persistence for, and would fail in a multi-worker deploy without the kind of shared cache the project does not have.
- *Backend uses the GitHub `If-None-Match` header*: GitHub does not honour conditional writes on this endpoint.
