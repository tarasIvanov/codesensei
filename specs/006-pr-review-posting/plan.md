# Implementation Plan: PR Review Comment Posting

**Branch**: `006-pr-review-posting` | **Date**: 2026-05-17 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/006-pr-review-posting/spec.md`

## Summary

Adds a single new endpoint `POST /api/review/post` that takes an already-rendered `ReviewResult` plus a target GitHub PR URL plus an explicit review event, and publishes it as one native GitHub review against the PR's "Files changed" tab via `POST /repos/{owner}/{repo}/pulls/{n}/reviews`. Findings with `(file, line)` become inline comments on the right-hand side; locationless findings and the overflow above the 50-inline-comment cap become a bullet list inside the review body. The endpoint reuses the encrypted bot PAT from feature 004's Settings store — no new credential surface, no audit table. A new small composable + panel on `/review` exposes the action when (and only when) the rendered result was driven by a PR URL, with a radio choice for the GitHub event and a single-use post button that locks itself after success. ADR-006's PR-posting strategy decision is closed by this implementation; no new ADR is required because no architectural surface changes — only a new outbound HTTP call from an existing service through an already-ratified PAT path.

## Technical Context

**Language/Version**: Python 3.12+ (backend), TypeScript 5.7 + Vue 3.5 + Vite 6 (frontend).
**Primary Dependencies (backend, new)**: none. `httpx>=0.27` is already in use for the existing GitHub diff fetch in `codesensei.review.github_diff`; the new posting client reuses the same client pattern (timeout=15 s, no retries — the caller owns retry policy per FR-013 / FR-014).
**Primary Dependencies (backend, reused)**: FastAPI, pydantic v2, `structlog`, `cryptography` (transitively — the bot token decrypt path is the existing `get_setting("GITHUB_TOKEN")` helper from feature 004), `codesensei.review.errors.ReviewError` (extended with five new categories — see Phase 1 / `contracts/api_post_review.md`).
**Primary Dependencies (frontend, new)**: none. Reuses the typed `fetch` wrapper already shared by `frontend/src/api/review.ts` and `frontend/src/api/repos.ts`.
**Storage**: **No schema change.** No new tables, no new migration, no new rows persisted by this feature. The endpoint is a pure proxy: it reads the PAT from the existing `app_settings` row and writes nothing locally. GitHub is the source of truth for the posted review.
**Testing**: pytest + pytest-asyncio + `respx` (existing). All seven failure paths plus the happy path are exercised in `tests/unit/test_github_posting.py` by mocking the GitHub REST API with `respx`; the body-only fallback after a 422 is exercised by composing a `respx` route that returns 422 once and 200 on the second call. One thin integration test (`tests/integration/test_review_post_endpoint.py`) wires the FastAPI handler against a `respx`-faked GitHub to assert the wire shape end-to-end. No new DB integration test is required because the feature touches no schema.
**Target Platform**: Linux container, same `api` service from previous features. No image change. No new env var. The endpoint becomes reachable as soon as a `GITHUB_TOKEN` row exists in `app_settings` — the feature inherits feature 004's `settings_locked` (503) refusal path verbatim when it is not.
**Project Type**: Web service (`backend/` FastAPI + `frontend/` Vue SPA) — identical layout to 001/002/003/004/005.
**Performance Goals**: SC-002 — happy-path post under 5 s for reviews ≤ 50 findings (one outbound GitHub call with a 15 s ceiling; the budget is set so the UI's spinner is never the bottleneck). SC-006 — single-page-view double-submit prevention (frontend-side lock; backend is intentionally non-idempotent because GitHub itself is non-idempotent on this endpoint, and adding local de-dup would require the audit table FR-017 forbids).
**Constraints**: 50 inline comments per posted review (FR-005). Exactly one `POST /reviews` call on the happy path, exactly two on the 422-fallback path, never more (FR-012 — caps the blast radius of one user action). httpx timeout = 15 s, no internal retry (FR-013 makes retry the caller's responsibility). `Retry-After` header is surfaced verbatim as `retry_after_seconds` to the caller (FR-014) — the backend never sleeps inside a request.
**Scale/Scope**: Single-tenant. Anticipated traffic: at most a few posts per minute under demo conditions; well below GitHub's primary-rate-limit floor for an authenticated bot account.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Justification |
|-----------|:-----:|---------------|
| **I. Spec-Driven Development** | ✅ | `spec.md` (20 FRs / 3 USs / 7 SCs / 7-item edge-case list), this plan, `checklists/requirements.md` (PASS) all exist. `/speckit-tasks` produces `tasks.md` before any production code. No exceptions claimed. |
| **II. ADR-Driven Architectural Decisions** | ✅ | The PR-comment-posting *strategy* — bot account, fine-grained PAT scoped on `Pull requests: write` + `Contents: read`, no user-PAT branch, no GitHub App in MVP — is **already** ratified by **ADR-006**. This feature is the implementation of that decision and introduces no new architectural surface that Principle II enumerates (no schema engine change, no queue change, no web-framework change, no AI-provider change, no deployment-shape change, no *new* posting strategy). The implementation tactics inside ADR-006 (the 50-comment cap, the 422→body-only fallback, the dedicated `/api/review/post` endpoint instead of overloading `/api/review`) are tactical choices, not architectural ones, and live in this plan and in `contracts/api_post_review.md`. After implementation, ADR-006 is updated in place: `Status` stays `accepted`, the `Notes` field gains a one-line "Shipped in feature 006." pointer. No new ADR-NNN. |
| **III. Pluggable AI Provider Boundaries** | ✅ | This feature does not touch any LLM or embedding provider. Zero new imports of `openai`, `anthropic`, `ollama`, or `sentence_transformers`. The review *content* being posted is whatever the existing provider-abstracted pipeline produced; this feature is a downstream proxy of that result. |
| **IV. Privacy & Credentials Discipline** | ✅ | The bot PAT lives encrypted-at-rest in `app_settings` from feature 004 and is read through `settings_store.store.get_setting("GITHUB_TOKEN")` exactly as the existing GitHub-diff-fetch path already does. The token MUST NOT appear in any HTTP response body, log line, or error envelope (Phase 1 contract enforces this — see `contracts/api_post_review.md` "Forbidden response fields"). The structured log line `github_review_posted` (FR-016) logs the *PR URL*, *event*, *comment count*, *elapsed time*, and *review id* — never the PAT, never the review body, never the diff. No source code crosses the boundary because of this feature (the diff and the chunks already crossed under feature 003/005); only the LLM's findings — already public-facing review text — go out to GitHub. |
| **V. Single-Command Deployment** | ✅ | Zero changes to `docker-compose.yml`. Zero changes to `backend/Dockerfile`. Zero new env vars are mandatory (the existing `MASTER_KEY` is the only key the feature transitively needs, and it is already required by feature 004). The `/review` page gains one new panel inside the existing `frontend` container. The whole feature ships behind the same `docker compose up` as everything else. |

**Verdict**: PASS. No new ADR. No Complexity-Tracking entries.

## Project Structure

### Documentation (this feature)

```text
specs/006-pr-review-posting/
├── plan.md                      # This file
├── spec.md                      # Already written (/speckit-specify)
├── research.md                  # Phase 0 — written below
├── data-model.md                # Phase 1 — written below
├── quickstart.md                # Phase 1 — written below
├── contracts/
│   ├── api_post_review.md       # POST /api/review/post wire shape, all 8 envelopes, log line
│   ├── github_review_payload.md # GitHub Reviews API request body + the mapping from ReviewResult
│   └── post_review_ui.md        # /review-page panel: visibility predicate, radio defaults, single-use lock
├── checklists/
│   └── requirements.md          # Already written (PASS)
└── tasks.md                     # Phase 2 (/speckit-tasks — separate command)
```

### Source Code (repository root)

```text
backend/
├── src/codesensei/
│   ├── posting/                          # NEW package — all GitHub-posting concerns isolated
│   │   ├── __init__.py
│   │   ├── api.py                        # POST /api/review/post route handler
│   │   ├── client.py                     # async httpx POST to GitHub Reviews API, status-code translation
│   │   ├── mapper.py                     # ReviewResult → {body, comments[], event} + the 50-cap + locationless-overflow rules
│   │   ├── schema.py                     # pydantic wire models: PostReviewRequest, PostedReviewReceipt
│   │   └── service.py                    # Orchestrates: parse pr_url → read PAT → map → POST → translate errors → emit log
│   ├── review/
│   │   └── errors.py                     # MODIFIED — add 5 new ReviewErrorCategory members: github_auth_failed, github_pr_not_found, github_review_rejected, github_api_unavailable, github_rate_limited
│   └── main.py                           # MODIFIED — mount posting router under /api
└── tests/
    ├── unit/
    │   ├── test_posting_mapper.py        # findings → comments mapping, 50-cap, locationless overflow, severity-style markdown rendering
    │   ├── test_github_posting.py        # respx-mocked GH: 200, 401, 403, 404, 422-then-200, 422-then-422, 500, 504, 429+Retry-After
    │   └── test_posting_pr_url_parse.py  # well-formed URLs, malformed → invalid_input
    └── integration/
        └── test_review_post_endpoint.py  # FastAPI TestClient + respx faking GH; full envelope assertions

frontend/
├── src/
│   ├── api/
│   │   └── posting.ts                    # NEW — typed postReview() client, narrow Error type per category
│   ├── components/
│   │   └── PostToGitHubPanel.vue         # NEW — radio (Comment | Request changes | Approve), submit, spinner, success/error states
│   └── pages/
│       └── ReviewPage.vue                # MODIFIED — mount PostToGitHubPanel when result+pr_url present; surface success link
```

**Structure Decision**: A separate `codesensei.posting` package — instead of stuffing the new endpoint into `codesensei.review` — for one reason: `review` already owns "produce a review" (LLM pipeline + retrieval + parsing) and "post a review" is the inverse direction (outbound HTTP to a third party, no LLM, no retrieval). Keeping them in one module would entangle the LLM-provider and retrieval test fixtures with GitHub-API test fixtures, and the import graph would suggest a coupling that does not exist. The `ReviewError` envelope is intentionally shared (single error-translation point at the FastAPI layer) — that is the only piece that crosses the boundary, and only through the `errors.py` module which both packages already depend on. Frontend follows the same separation: one new typed API client (`posting.ts`), one panel component, one MODIFIED page.

## Complexity Tracking

*Empty — Constitution Check passed.*
