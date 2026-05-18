---
description: "Tasks for feature 006 — PR review comment posting"
---

# Tasks: PR Review Comment Posting

**Input**: Design documents from `/specs/006-pr-review-posting/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Critical-path tests are included per the Constitution's TDD-for-critical-paths rule (the mapper, the GitHub-client error translation, and the endpoint contract).

**Organization**: Tasks are grouped by user story. US1 is MVP — the whole thing works end-to-end after US1 ships. US2 is error-envelope completeness. US3 is the /review-page UI panel.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

Repo is a web-app per plan.md: `backend/src/`, `frontend/src/`, tests under `backend/tests/{unit,integration}/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Wire up the new `codesensei.posting` package and its router mount. No new external dependencies.

- [X] T001 Create empty package `backend/src/codesensei/posting/__init__.py` with module docstring "GitHub Reviews API posting — feature 006".
- [X] T002 Append five new categories to `ReviewErrorCategory` in `backend/src/codesensei/review/errors.py`: `GITHUB_AUTH_FAILED = "github_auth_failed"`, `GITHUB_PR_NOT_FOUND = "github_pr_not_found"`, `GITHUB_REVIEW_REJECTED = "github_review_rejected"`, `GITHUB_API_UNAVAILABLE = "github_api_unavailable"`, `GITHUB_RATE_LIMITED = "github_rate_limited"`. Extend the `HTTP_FOR_CATEGORY` MappingProxyType with their codes (401, 404, 502, 502, 429 respectively). Existing categories untouched.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Build the wire models + the URL parser + the rate-limit envelope hook. Everything below US1 depends on these.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T003 [P] Create pydantic wire models in `backend/src/codesensei/posting/schema.py`: `PostReviewRequest` (`review_result: ReviewResult`, `pr_url: str`, `event: Literal["COMMENT","REQUEST_CHANGES","APPROVE"]`, `extra="forbid"`), `PostedReviewReceipt` (`review_id: int`, `html_url: str`, `posted_at: datetime`, `comment_count: int`, `attempted_calls: int`, `extra="ignore"`). Import `ReviewResult` from `codesensei.review.schema`.
- [X] T004 [P] Implement `parse_pr_url(pr_url: str) -> tuple[str, str, int]` in `backend/src/codesensei/posting/service.py`. Reuse the regex `^https://github\.com/([^/\s]+)/([^/\s]+)/pull/(\d+)$`. Mismatch → raise `ReviewError(INVALID_INPUT, "PR URL must match https://github.com/<owner>/<repo>/pull/<n>.")`.
- [X] T005 Extend `ReviewError.to_envelope()` callers' error-handler in `backend/src/codesensei/main.py` (or wherever the existing FastAPI exception handler lives) so that for `GITHUB_RATE_LIMITED` the JSON response also carries top-level `retry_after_seconds: int` next to `error`. Field source: `ReviewError` gains an optional `retry_after_seconds: int | None = None` constructor kwarg; the handler reads it.

**Checkpoint**: Foundation ready — US1 can now begin.

---

## Phase 3: User Story 1 — Post review to a GitHub PR (Priority: P1) 🎯 MVP

**Goal**: End-to-end happy path. From a `ReviewResult` + PR URL + event, publish one GitHub review with inline comments and return `PostedReviewReceipt`.

**Independent Test**: Run a review on /review against a PR URL the bot can access. Click "Post to GitHub" (or `curl` the endpoint). Verify the GitHub PR shows a new review with all located findings as inline comments and the response carries `review_id` + `html_url`.

### Tests for User Story 1 ⚠️ (write FIRST, must FAIL before T011–T014)

- [X] T006 [P] [US1] Write `backend/tests/unit/test_posting_mapper.py`: 6 cases. (1) Empty findings → `comments == []`, `body` contains the verdict line. (2) Three findings all with file+line → three inline comments, no body bullet list. (3) Mixed: 2 located + 2 locationless → 2 inline + 2 body bullets under `### Findings without inline location`. (4) 52 located findings → 50 inline + 2 in body under `### Additional findings (beyond the 50-comment cap)` with `at file:line` suffix. (5) Finding with `suggestion=None` renders body line without the `_Suggestion_:` paragraph. (6) Finding with `line == 0` is treated as locationless (defensive).
- [X] T007 [P] [US1] Write `backend/tests/unit/test_posting_pr_url_parse.py`: 4 cases. Well-formed `https://github.com/foo/bar/pull/42` → `("foo","bar",42)`. Trailing slash → mismatch → `INVALID_INPUT`. `http://` (not https) → mismatch. Missing pull number → mismatch.
- [X] T008 [P] [US1] Write `backend/tests/unit/test_github_posting.py` with the **happy path** test only (200 response). Use `respx` to mock `POST https://api.github.com/repos/owner/repo/pulls/42/reviews` returning `{"id": 999, "html_url": "https://github.com/owner/repo/pull/42#pullrequestreview-999"}`. Assert outbound headers (`Accept`, `X-GitHub-Api-Version`, `Authorization: Bearer fake-token`), body shape (event, body, comments), and that the returned `PostedReviewReceipt.review_id == 999`. Use `monkeypatch.setattr("codesensei.posting.service.get_setting", AsyncMock(return_value="fake-token"))`.
- [X] T009 [P] [US1] Write `backend/tests/integration/test_review_post_endpoint.py` with the happy-path test only: FastAPI TestClient submits a valid `PostReviewRequest`, `respx` returns 200, assert HTTP 200 + JSON receipt fields + that the structured log line `github_review_posted` was emitted with `outcome="ok"` and `attempted_calls=1`.

### Implementation for User Story 1

- [X] T010 [P] [US1] Implement the mapper in `backend/src/codesensei/posting/mapper.py`. Public function `build_payload(review_result: ReviewResult, event: str) -> dict` returning `{"event": event, "body": <markdown>, "comments": [...]}`. Private `_render_body_line(finding) -> str` for the inline-comment markdown body. Private `_compose_top_body(verdict, provider, elapsed_ms, locationless, overflow) -> str` for the review body. Constants: `INLINE_COMMENT_CAP = 50`, `SIDE = "RIGHT"`. Markdown body template exactly per `contracts/github_review_payload.md`. The mapper does not import httpx — pure transformation.
- [X] T011 [US1] Implement the GitHub HTTP client in `backend/src/codesensei/posting/client.py`. `async def post_review(*, owner: str, repo: str, number: int, token: str, payload: dict) -> dict` — runs `httpx.AsyncClient(timeout=15.0)`, POSTs to `https://api.github.com/repos/{owner}/{repo}/pulls/{number}/reviews`, returns parsed JSON on 200. Translates non-200 by status code into `ReviewError`: 401/403→`GITHUB_AUTH_FAILED`, 404→`GITHUB_PR_NOT_FOUND`, 422→raise a typed internal exception `_GitHub422(response_body)` so the caller (service) can decide on fallback, 429→`GITHUB_RATE_LIMITED` with `retry_after_seconds` parsed from `Retry-After` (default 60), 5xx→`GITHUB_API_UNAVAILABLE(retryable=True)`. `httpx.TimeoutException` / `httpx.ConnectError` / `httpx.HTTPError` → `GITHUB_API_UNAVAILABLE(retryable=True)`. Auth message on 401/403 must literally be `"PAT invalid or missing permissions (need pull_requests:write)."`.
- [X] T012 [US1] Implement the orchestrator in `backend/src/codesensei/posting/service.py`. `async def post_review_to_github(req: PostReviewRequest) -> PostedReviewReceipt`. Sequence: (1) `parse_pr_url(req.pr_url)` → owner/repo/number; (2) `token = await get_setting("GITHUB_TOKEN")`; if `None` raise `ReviewError(SETTINGS_LOCKED, "No GitHub bot token configured. Open Settings to add one.")`; (3) `payload = build_payload(req.review_result, req.event)`; (4) call `client.post_review(...)`; (5) on `_GitHub422` raised: inspect body for the position-error predicate from `contracts/github_review_payload.md`; if it matches, rebuild payload with `comments=[]`, retry once, set `attempted_calls=2`; if the body-only retry returns 422 again or the first 422 is structural, raise `GITHUB_REVIEW_REJECTED` with the raw GH body in the message; (6) compose and return `PostedReviewReceipt`; (7) wrap the whole call in `try/finally` that emits the `github_review_posted` structlog line.
- [X] T013 [US1] Implement the FastAPI route in `backend/src/codesensei/posting/api.py`. `POST /api/review/post` body=`PostReviewRequest`, response=`PostedReviewReceipt`. Calls `posting.service.post_review_to_github`. No `response_model` decorator — manual `JSONResponse(model_dump_json())` so error envelope translation lives in the existing exception handler (T005).
- [X] T014 [US1] Mount the router in `backend/src/codesensei/main.py`: `app.include_router(posting_router, prefix="/api")`. Import `from codesensei.posting.api import router as posting_router`.

### Followup tests for US1 (must pass after T010–T014)

- [X] T015 [US1] Append to `backend/tests/unit/test_github_posting.py` the **422-fallback success** test: `respx` returns 422 once (with `errors: [{"resource":"PullRequestReviewComment","field":"line"}]`) then 200. Assert `attempted_calls == 2`, `comment_count == 0`, `review_id == <from second response>`.
- [X] T016 [US1] Append to `backend/tests/integration/test_review_post_endpoint.py`: invalid PR URL → 400 `invalid_input`; missing PAT (mock `get_setting` returning None) → 503 `settings_locked`.

**Checkpoint**: US1 fully functional. `POST /api/review/post` works end-to-end against a real GitHub PR.

---

## Phase 4: User Story 2 — Predictable error handling (Priority: P2)

**Goal**: All seven failure paths return distinct, contract-compliant envelopes.

**Independent Test**: Trigger each path (Settings deletes, revoked token, 404 PR, 422 line out of diff, 5xx, 429). Verify each response carries the expected `category`, `retryable`, HTTP code, and `retry_after_seconds` (rate-limit only).

### Tests for User Story 2 ⚠️

- [X] T017 [P] [US2] Append to `backend/tests/unit/test_github_posting.py` six **error-path** tests: 401, 403, 404, 422-twice (structural rejection), 500, 504, 429 with `Retry-After: 90`. Assert: 401/403 → `GITHUB_AUTH_FAILED, retryable=False`, message contains `pull_requests:write`. 404 → `GITHUB_PR_NOT_FOUND, retryable=False`. 422-twice → `GITHUB_REVIEW_REJECTED` with raw body in message, `retryable=False`, `attempted_calls=2`. 500/504/timeout → `GITHUB_API_UNAVAILABLE, retryable=True`. 429 → `GITHUB_RATE_LIMITED, retryable=True, retry_after_seconds=90`.
- [X] T018 [P] [US2] Append to `backend/tests/integration/test_review_post_endpoint.py`: each error envelope is rendered into the right HTTP response shape. In particular: 429 response carries top-level `retry_after_seconds` (not nested under `error`).

### Implementation for User Story 2

- [X] T019 [US2] Verify the position-error predicate in `backend/src/codesensei/posting/service.py` matches `contracts/github_review_payload.md` exactly: matches `errors[].resource == "PullRequestReviewComment"` with `field` in `{path, line, position, start_line}`, OR top-level `message.lower()` contains `"not part of the pull request diff"`. Anything else is a structural rejection (no fallback retry). Add a small helper `_is_position_error(body: dict) -> bool` so it can be unit-tested.
- [X] T020 [US2] Make sure the `github_review_posted` log line in `service.py` records `outcome=<category>` on all failure paths (including the SETTINGS_LOCKED and INVALID_INPUT paths) and `attempted_calls=2` when the body-only fallback ran. Use a `finally` block so an exception path still emits the line. The PAT MUST NOT be logged — assert by inspection of the log-fields dict.

**Checkpoint**: All seven failure paths are distinct and contract-compliant.

---

## Phase 5: User Story 3 — "Post to GitHub" panel on /review (Priority: P3)

**Goal**: A reviewer can post the rendered review with at most three clicks (open the panel, choose event, click post) and gets a single-use lock + a category-specific error UX.

**Independent Test**: Run a review on /review from a PR URL. Verify the panel appears, the radio defaults to the verdict's event, clicking posts, the success state shows the GitHub link, the lock survives further clicks. Run the same flow with a raw-diff review and verify the panel is hidden.

### Implementation for User Story 3

- [X] T021 [P] [US3] Create typed API client `frontend/src/api/posting.ts` exporting `postReview(input: PostReviewInput): Promise<PostedReviewReceipt>`. Throws `PostReviewError` on non-2xx (per `data-model.md` shape) — parse `category`, `retryable`, and `retry_after_seconds` from the envelope. Mirror the existing fetch-error pattern used in `frontend/src/api/review.ts`.
- [X] T022 [P] [US3] Create the panel component `frontend/src/components/PostToGitHubPanel.vue`. Props: `reviewResult: ReviewResult`, `prUrl: string`. Internal refs: `event` (default derived from `reviewResult.verdict`), `inFlight: boolean`, `posted: PostedReviewReceipt | null`, `error: PostReviewError | null`. Render the state machine from `contracts/post_review_ui.md` exactly: INITIAL → IN-FLIGHT (button has `aria-busy="true"`, radio disabled) → POSTED (replace panel with `Posted ✓` + `View on GitHub` link `target="_blank" rel="noopener"`) | ERROR (banner `role="alert"`; retry visible iff `error.retryable`; for `github_rate_limited` show countdown via `setInterval` decrementing `retry_after_seconds` and re-enable retry at 0). On `settings_locked` the banner renders a `<RouterLink to="/settings">` styled as a button.
- [X] T023 [US3] Wire the panel into `frontend/src/pages/ReviewPage.vue`. Mount `<PostToGitHubPanel :review-result="result" :pr-url="prUrl" />` iff `result` is non-null AND the local `prUrl` ref is non-empty (i.e. the form's URL input was the source of this review, not the diff textarea). Unmount when the user clears or re-submits with a different input shape. Page-level state for `prUrl` must be set inside the submit handler when the URL input is used, and cleared when the diff input is used.

### Manual smoke for US3

- [X] T024 [US3] Run the `quickstart.md` flow §2–§6 end-to-end against a live PR the bot can access. Verify: panel visibility predicate, radio default, in-flight spinner, success badge with working link, single-use lock, raw-diff review hides the panel. Capture one Playwright DOM snapshot per state into the PR description as evidence.

**Checkpoint**: All three user stories work independently and together.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T025 [P] Update `_decision_log.md` in the project root: append a one-line `Notes:` continuation to ADR-006 — `Shipped in feature 006-pr-review-posting (2026-05-17): POST /api/review/post; one Reviews-API call per post; 50 inline-comment cap + body-overflow; reuses GITHUB_TOKEN from feature 004 Settings store.` Do NOT add a new ADR — strategy was already accepted in ADR-006.
- [X] T026 [P] Update `README.md` to add `/review` "Post to GitHub" capability to the feature list, and add `POST /api/review/post` to the API table if there is one.
- [X] T027 Run `uv run ruff check backend/src backend/tests --fix` then `uv run ruff format backend/src backend/tests`. Confirm clean.
- [X] T028 Run `cd backend && uv run pytest -q`. Confirm 0 failures. Existing tests from 001–005 must remain green.
- [X] T029 Run `cd frontend && npx vue-tsc --noEmit`. Confirm 0 type errors.
- [X] T030 Walk the `quickstart.md` failure-path table §6 manually for the four paths reachable without engineering effort (`settings_locked`, `github_auth_failed`, `github_pr_not_found`, `github_api_unavailable`). Record any UX deviations as follow-ups; if none, mark T024 + T030 complete and the feature ready to commit.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No deps.
- **Foundational (Phase 2)**: Depends on Phase 1. BLOCKS Phases 3, 4, 5.
- **US1 (Phase 3)**: Depends on Phase 2.
- **US2 (Phase 4)**: Depends on Phase 3 (US2 tests reuse the `respx` patterns and `client.py` translator established by US1).
- **US3 (Phase 5)**: Depends on Phase 3 only (US3 is the UI for US1; it does not need US2's error tests to ship — though it benefits from US2's polished error envelopes for the banner UX).
- **Polish (Phase 6)**: Depends on all desired US phases.

### Within Each User Story

- **TDD** for the mapper, the GitHub client, and the endpoint contract: T006/T007/T008/T009 before T010–T014. T015/T016 (US1 followup tests) after the implementation.
- Mapper before client before service before route (T010 → T011 → T012 → T013 → T014).

### Parallel Opportunities

- **Phase 2**: T003, T004 in parallel (different files).
- **US1 tests (T006/T007/T008/T009)**: all four are [P] — different files, no inter-dependency. Run together before implementation.
- **US1 implementation**: T010 [P] (mapper) is independent of T011 (client) is independent of T012 (service). T012 imports T010 and T011, so T012 must run after them. T013/T014 are sequential (route registration depends on the service).
- **US2 tests (T017/T018)**: [P] — append-only to two different test files.
- **US3 (T021/T022)**: [P] — different files (API client vs component).
- **Polish (T025/T026)**: [P] — different files.

---

## Parallel Example: US1 Tests

```bash
# Four test files, run before any implementation lands:
Task: "test_posting_mapper.py — 6 mapping cases"
Task: "test_posting_pr_url_parse.py — 4 URL cases"
Task: "test_github_posting.py — happy path with respx mock"
Task: "test_review_post_endpoint.py — happy path with TestClient + respx"
```

---

## Implementation Strategy

### MVP First (US1 only)

1. Phase 1 + Phase 2 (T001–T005).
2. US1 tests fail (T006–T009).
3. US1 implementation green (T010–T014). Followup tests green (T015–T016).
4. Smoke against a real PR. Deploy/demo.

### Incremental Delivery

1. MVP (US1) → demonstrate one-click post.
2. Add US2 → all seven error categories deterministic.
3. Add US3 → polished /review-panel UX.

### Test discipline

- Mapper, client error translation, and endpoint contract: **tests first**, per the Constitution.
- UI panel: tested manually via `quickstart.md` walk-through; no Vitest tests in scope for V1.

---

## Notes

- [P] = different files, no dependencies — safe to parallelise.
- No new migrations, no new compose services, no new env vars.
- ADR-006 *closed* by this feature; do NOT open ADR-011 for the same decision.
- The 50-comment cap is in code (`INLINE_COMMENT_CAP = 50` in `mapper.py`); revisiting it in V2 is a one-constant change, no architectural impact.
- Token never logged. Token never echoed in responses. Quickstart §7 covers verification.
