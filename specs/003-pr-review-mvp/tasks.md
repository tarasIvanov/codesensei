---

description: "Task list — 003-pr-review-mvp"
---

# Tasks: PR Review MVP (diff-only, no retrieval)

**Input**: Design documents from `/specs/003-pr-review-mvp/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/api_review.md, contracts/llm_prompt.md, contracts/github_diff_fetch.md, quickstart.md

**Tests**: INCLUDED. The constitution §test-first explicitly names "parsing structured LLM output" as a critical path that MUST have failing tests committed before implementation. Tests for the parser, schemas, service, and endpoint are required; tests for trivial plumbing (`prompt.py` is snapshot-only) and UI glue are exempt.

**Organization**: Tasks are grouped by user story (US1 P1, US2 P2, US3 P3). Each story is independently demonstrable per `spec.md`'s Independent Test sections.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Different file from other [P] tasks in the same group → safe to parallelise
- **[Story]**: Maps to spec.md's user stories (US1/US2/US3)
- Paths follow the web-app layout established in 001/002: `backend/src/codesensei/`, `frontend/src/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project-level scaffolding before any review code lands.

- [X] T001 Add review-related Settings fields to `backend/src/codesensei/config.py`: `review_max_diff_bytes: int = 256_000`, `review_llm_timeout_s: float = 60.0`, `github_token: str = ""`. No new imports beyond existing `pydantic-settings` patterns.
- [X] T002 [P] Update `.env.example` with three new keys (`REVIEW_MAX_DIFF_BYTES=`, `REVIEW_LLM_TIMEOUT_S=`, `GITHUB_TOKEN=`) under a new "PR review (003)" section; keep all values empty so defaults from `config.py` apply.
- [X] T003 [P] Create empty package `backend/src/codesensei/review/__init__.py` to anchor the new module.
- [X] T004 [P] Add `vue-router@^4` to `frontend/package.json` (`pnpm add vue-router@^4` produces the lockfile update); do not yet wire any routes.

**Checkpoint**: Settings load with new fields; new env keys documented; empty review package exists; `vue-router` installed but unused.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Cross-story plumbing — error envelope, schemas, FastAPI exception handlers, frontend router. Every user story depends on these.

**⚠️ CRITICAL**: No US-tagged task may start until Phase 2 finishes.

- [X] T005 [P] Define `ReviewErrorCategory(StrEnum)` and `ReviewError(Exception)` in `backend/src/codesensei/review/errors.py` per `data-model.md` (members: `invalid_input`, `payload_too_large`, `github_fetch_failed`, `provider_unavailable`, `provider_malformed_output`, `internal`; constructor: `category`, `message`, `retryable=False`). Add a frozen `_HTTP_FOR_CATEGORY` mapping per the table in `contracts/api_review.md`.
- [X] T006 [P] Define wire-shape pydantic models in `backend/src/codesensei/review/schema.py` per `data-model.md`: `Severity`/`Verdict` `StrEnum`, `Finding`, `ReviewResult`, `ReviewRequest` with `model_validator(mode="after")` enforcing exactly-one of `diff`/`pr_url`. Apply `max_length` truncation server-side for `message` (2000) and `suggestion` (4000) with a trailing `"…"`.
- [X] T007 Add a FastAPI exception handler in `backend/src/codesensei/main.py` that catches `ReviewError` and `RequestValidationError` and emits the uniform envelope `{"error": {"category", "message", "retryable"}}` with the HTTP code from `_HTTP_FOR_CATEGORY` (422 → 400 `invalid_input`). Depends on T005, T006.
- [X] T008 [P] Carve the current health-badge UI out of `frontend/src/App.vue` into a new `frontend/src/pages/HealthPage.vue` (identical markup, no behavioural change). Verify visually: `docker compose up -d --force-recreate web` still shows the four badges at `/`.
- [X] T009 Wire `frontend/src/router.ts` with two routes — `/` → `HealthPage`, `/review` → placeholder component `ReviewPage` (empty `<main/>` body for now). Mount `<RouterView/>` in `App.vue`. Depends on T004, T008.

**Checkpoint**: Backend has the error envelope but no `/api/review` endpoint yet. Frontend `/` and `/review` both resolve; the latter is intentionally blank.

---

## Phase 3: User Story 1 — Paste a unified diff (Priority: P1) 🎯 MVP

**Goal**: Paste a diff into `/review`, get a rendered findings list back. End-to-end pipeline: SPA → `POST /api/review {diff}` → prompt assembly → `LLMProvider.chat` → strict parse → JSON response → grouped-by-file render.

**Independent Test** (per spec.md US1): Paste a known-bad diff (e.g. obvious null-deref) into the textarea, click Review, confirm the rendered findings list contains at least one item naming the right file and a line within ±3 of the defect. Works offline against a mocked `LLMProvider`.

### Tests for User Story 1 (write FIRST, ensure FAIL before implementation)

- [X] T010 [P] [US1] `backend/tests/unit/test_review_schema.py`: pydantic round-trip for `ReviewRequest`; both-set rejection; neither-set rejection; non-diff `diff` value rejection (no `diff --git ` or `--- a/`+`+++ b/`); good unified diff accepted; pydantic-validation errors map to `RequestValidationError`.
- [X] T011 [P] [US1] `backend/tests/unit/test_review_prompt.py`: snapshot-test the verbatim SYSTEM message string against `contracts/llm_prompt.md`; assert USER template wraps the diff in a `` ```diff `` fence; assert call kwargs to a mock `LLMProvider.chat` are `max_tokens=4096`, `temperature=0.1`, `model=None`.
- [X] T012 [P] [US1] `backend/tests/unit/test_review_parser.py`: happy case (valid JSON envelope → list[Finding]); strips a leading ```` ```json ```` fence; raises `ReviewError(provider_malformed_output)` on: non-JSON, missing `verdict`, missing `findings`, unknown severity, non-integer `line`, missing `file`, missing `message`; message ≤ 2000 chars and suggestion ≤ 4000 chars are truncated, not rejected.
- [X] T013 [P] [US1] `backend/tests/unit/test_review_service.py`: mock `LLMProvider` via `AsyncMock`; happy → returns `ReviewResult`; LLM returns clean-empty-findings JSON → 200 with empty `findings`, verdict `approve`; LLM raises `ProviderError(retryable=True)` → `ReviewError(provider_unavailable, retryable=True)`; LLM returns garbage → `ReviewError(provider_malformed_output, retryable=False)`; `elapsed_ms` is populated.
- [X] T014 [P] [US1] `backend/tests/integration/test_review_endpoint.py` (US1 slice): `POST /api/review {"diff": "..."}` against `LLMProvider` mocked at the factory level → 200 with envelope per `contracts/api_review.md`; empty body → 400 `invalid_input`; both `diff` and `pr_url` set → 400 `invalid_input`; mocked malformed LLM output → 502 `provider_malformed_output`.

### Implementation for User Story 1

- [X] T015 [P] [US1] `backend/src/codesensei/review/prompt.py`: module-level constants `SYSTEM_MESSAGE: str` and `USER_TEMPLATE: str` exactly matching `contracts/llm_prompt.md`. Export `build_messages(diff: str) -> list[ChatMessage]`.
- [X] T016 [P] [US1] `backend/src/codesensei/review/parser.py`: `parse_review(provider_name: str, raw: str) -> tuple[Verdict, list[Finding]]`. Strip whitespace; defensively strip ```` ```json ```` / ```` ``` ```` fences; `json.loads`; pydantic-validate; truncate `message`/`suggestion`; on any failure raise `ReviewError(provider_malformed_output, ...)`.
- [X] T017 [US1] `backend/src/codesensei/review/service.py`: `ReviewService.run_for_diff(diff: str) -> ReviewResult`. Steps: byte-count guard (size check is a Phase 5 task — for now just validate `_is_unified_diff(diff)`, raise `invalid_input` if not); build messages via `prompt.build_messages`; call `get_llm_provider().chat(...)` (no `wait_for` yet — that's Phase 5); pass response through `parser.parse_review`; assemble `ReviewResult` with `provider`, `elapsed_ms` (use `time.perf_counter`). Translate `ProviderError(retryable=True)` → `ReviewError(provider_unavailable, retryable=True)`; `ProviderError(retryable=False)` → `ReviewError(provider_unavailable, retryable=False)` (timeout/auth/etc, no retry hint). Depends on T015, T016.
- [X] T018 [US1] Wire `POST /api/review` in `backend/src/codesensei/main.py`: accepts `ReviewRequest`; for now rejects `pr_url`-only with `invalid_input` "PR URL mode lands in US2"; delegates the diff path to `ReviewService.run_for_diff`; returns `ReviewResult.model_dump()`; emits one structured log line (`event=review.completed`/`review.failed`, no diff/finding bodies) per `contracts/api_review.md` § Logging contract. Depends on T007, T017.
- [X] T019 [P] [US1] `frontend/src/components/SeverityBadge.vue`: a `<span>` with class + label per the four severities per `research.md` R9. Props: `severity: 'blocker'|'major'|'minor'|'nit'`.
- [X] T020 [P] [US1] `frontend/src/components/FindingsList.vue`: receives `findings: Finding[]`; groups by `file`; renders per-file collapsible section with severity badge, optional `line`, message, and an optional `<pre><code>` suggestion block. Empty list → renders an explicit "No issues found" empty state (spec AS-3).
- [X] T021 [P] [US1] `frontend/src/api/review.ts`: typed `runReview(body: {diff: string} | {pr_url: string}): Promise<ReviewResult>`. On non-2xx, throws a typed `ReviewApiError(category, message, retryable)`. Maintain a const `MESSAGE_FOR_CATEGORY: Record<ReviewErrorCategory, string>` for any case where the backend message is missing.
- [X] T022 [US1] Build out `frontend/src/pages/ReviewPage.vue` (replacing the Phase-2 placeholder): a `<textarea v-model="diff">`, a Submit button, a loading state, and `<FindingsList :findings>` once `result.findings` is populated. Disable Submit while a request is in flight (edge case "double-click"). On error, surface `error.message` and keep the textarea content (FR-017). Depends on T019, T020, T021.

**Checkpoint**: `docker compose up -d`; paste a diff into `/review`; see findings render. Scenario A from `quickstart.md` passes end-to-end against a configured LLM provider. US2 and US3 work unaffected (no PR URL fetch yet; oversized diffs go straight to the LLM and may simply time out — that's the Phase-5 problem).

---

## Phase 4: User Story 2 — Review a GitHub PR by URL (Priority: P2)

**Goal**: Accept a `pr_url`, fetch the unified diff from GitHub, and feed it into the same pipeline as US1.

**Independent Test** (per spec.md US2): Submit a public PR URL with `GITHUB_TOKEN` either set or empty; confirm rendered findings reference files actually changed in that PR; the textarea path from US1 still works.

### Tests for User Story 2

- [X] T023 [P] [US2] `backend/tests/unit/test_github_diff.py`: per `contracts/github_diff_fetch.md` § Test surface — happy, sends `Authorization` when token present, omits it when empty; 401 → `github_fetch_failed` (auth); 404 → `github_fetch_failed` (not found); 500 → `github_fetch_failed`; `httpx.TimeoutException` and `ConnectError` → `github_fetch_failed`; assert no log line ever contains the token value (capture with `caplog`). Use `respx`.
- [X] T024 [P] [US2] Extend `backend/tests/integration/test_review_endpoint.py` with: `POST {"pr_url": "https://github.com/o/r/pull/1"}` happy (respx-mocked GitHub); malformed URL → 400 `invalid_input`; 404 from GitHub → 502 `github_fetch_failed`; non-`github.com` host in URL → 400 `invalid_input`.

### Implementation for User Story 2

- [X] T025 [P] [US2] `backend/src/codesensei/review/github_diff.py`: `async def fetch_pr_diff(pr_url: str) -> str`. Parses the URL with the regex from `data-model.md`; sends the request per `contracts/github_diff_fetch.md`; maps responses → returns text or raises `ReviewError(github_fetch_failed, ...)`. Never logs `settings.github_token`.
- [X] T026 [US2] `ReviewService.run_for_url(pr_url: str) -> ReviewResult`: calls `fetch_pr_diff`, then reuses the same byte-count guard + chat + parse steps as `run_for_diff`. Depends on T025, T017.
- [X] T027 [US2] Update the endpoint handler in `main.py` to route `ReviewRequest` to `run_for_diff` or `run_for_url` depending on which field is set; delete the Phase-3 placeholder "PR URL mode lands in US2" rejection. Depends on T026.
- [X] T028 [US2] Update `frontend/src/pages/ReviewPage.vue` with an input-mode toggle: a small `<select>` or pair of `<button>` chips switching between **Diff** and **PR URL** input modes. The opposite input is hidden when not active so the wire body always carries exactly one of the two fields. Depends on T022.

**Checkpoint**: Scenarios A and B from `quickstart.md` both pass. US1 textarea flow is unchanged; the URL flow returns findings for a small public PR.

---

## Phase 5: User Story 3 — Graceful hardening (Priority: P3)

**Goal**: Size cap (413), LLM timeout (502 `provider_unavailable retryable=true`), malformed LLM output (502 `provider_malformed_output retryable=false`), uniform UI error display, no logging of sensitive content.

**Independent Test** (per spec.md US3): A 300 KB synthetic diff returns 413 in <1 s (SC-004); a mocked malformed-output test returns 502 `provider_malformed_output`; UI renders distinct messages for each category and preserves the input.

### Tests for User Story 3

- [X] T029 [P] [US3] Extend `backend/tests/integration/test_review_endpoint.py` with: oversized diff (`len > settings.review_max_diff_bytes`) → 413 `payload_too_large` in <1 s wall-clock (use `pytest.mark.timeout` if available, otherwise assert via `time.perf_counter`); no LLM call was made (assert mocked `LLMProvider.chat` not awaited); body never appears in logs (`caplog`).
- [X] T030 [P] [US3] Extend `backend/tests/unit/test_review_service.py` with: `LLMProvider.chat` raises `asyncio.TimeoutError` (simulated via `AsyncMock(side_effect=...)`) → `ReviewError(provider_unavailable, retryable=True)`; the request finishes within `review_llm_timeout_s + 1` (no hang).
- [X] T031 [P] [US3] Extend `backend/tests/integration/test_review_endpoint.py` with: `event=review.failed` log line for each failure category carries `error_category=<name>` and `payload_bytes=<int>` but never the diff body or any finding body (capture and grep `caplog.records`).

### Implementation for User Story 3

- [X] T032 [US3] Add byte-count guard at the top of both `ReviewService.run_for_diff` and `ReviewService.run_for_url` (after fetch, before chat): if `len(diff.encode('utf-8')) > settings.review_max_diff_bytes`, raise `ReviewError(payload_too_large, "Diff exceeds the {n} KB limit. Try a smaller change.", retryable=False)`. Depends on T017, T026.
- [X] T033 [US3] Wrap the `LLMProvider.chat` call in `ReviewService` with `await asyncio.wait_for(..., timeout=settings.review_llm_timeout_s)`; catch `asyncio.TimeoutError` → `ReviewError(provider_unavailable, "Review service timed out — try again.", retryable=True)`. Depends on T017.
- [X] T034 [US3] In `frontend/src/pages/ReviewPage.vue`, render every `ReviewApiError.category` with the matching human message; show a "Try again" button only when `retryable: true`; preserve the textarea / URL input verbatim across an error. Depends on T022.
- [X] T035 [US3] In `backend/src/codesensei/main.py`, ensure the exception-handler log line for every `ReviewError` includes `event="review.failed"`, `error_category=<value>`, `payload_bytes=<int|null>`, `provider=<name|null>`, `elapsed_ms=<int>` — and explicitly **never** the request body, the diff, or any finding content (FR-019). Depends on T007.

**Checkpoint**: All four scenarios in `quickstart.md` pass (A paste, B URL, C oversized, D malformed via test). All six error categories from `contracts/api_review.md` are reachable in tests.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T036 [P] Run `ruff check backend/ && ruff format --check backend/` clean; fix any reported issues without changing behaviour.
- [X] T037 [P] Run `cd frontend && pnpm exec vue-tsc -b` clean; fix any reported issues.
- [X] T038 [P] Run the full backend suite: `cd backend && uv run pytest -q`. All tests added in Phases 3–5 pass; pre-existing 77 tests from 001+002 still pass; no warnings about un-mocked HTTP.
- [X] T039 Update `README.md` with a short "What is `/review`?" section pointing to `specs/003-pr-review-mvp/quickstart.md` (copy a 5-line gist; do not duplicate the quickstart).
- [X] T040 Manually run quickstart Scenario A (paste a diff) and Scenario C (oversize via curl) against the running stack; capture findings in a one-paragraph note inside the PR description.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: no dependencies. T001–T004 can land first.
- **Phase 2 (Foundational)**: depends on Phase 1.
  - T005, T006, T008 can run in parallel.
  - T007 depends on T005 + T006.
  - T009 depends on T004 + T008.
- **Phase 3 (US1)**: depends on Phase 2.
  - All tests (T010–T014) are [P] and land before their implementation targets.
  - Implementation order: T015 + T016 (parallel) → T017 → T018; T019, T020, T021 are [P] and feed T022.
- **Phase 4 (US2)**: depends on Phase 3 (reuses `ReviewService` from T017 and `ReviewPage` from T022).
  - T023 + T024 [P]; T025 [P]; T026 depends on T025 + T017; T027 depends on T026; T028 depends on T022.
- **Phase 5 (US3)**: depends on Phase 3 (and on Phase 4 because the oversize guard sits in both `run_for_diff` and `run_for_url`).
  - T029 + T030 + T031 [P]; T032 + T033 + T035 backend [P] except T032 needs both T017 and T026; T034 depends on T022.
- **Phase 6 (Polish)**: depends on Phases 3–5.

### Within Each Story

- Tests written and committed FAILING before implementation (constitution §test-first for critical paths).
- Schemas/enums before service; service before endpoint; endpoint before frontend page wiring.

### Parallel Opportunities

- T002, T003, T004 within Phase 1.
- T005, T006, T008 within Phase 2.
- All US1 test tasks T010–T014 in one batch (different files).
- T015 and T016 in parallel (no shared file).
- Frontend T019, T020, T021 in parallel.
- US2 tests T023 and T024 in parallel.
- US3 tests T029, T030, T031 in parallel; impl T032, T033, T035 in parallel.

---

## Parallel Example: Phase 3 tests

```bash
Task: "Write backend/tests/unit/test_review_schema.py per contract"
Task: "Write backend/tests/unit/test_review_prompt.py snapshot"
Task: "Write backend/tests/unit/test_review_parser.py table"
Task: "Write backend/tests/unit/test_review_service.py with AsyncMock LLM"
Task: "Write backend/tests/integration/test_review_endpoint.py US1 slice"
```

All five files are disjoint and can be drafted independently. Once committed (failing), run the implementation tasks T015 → T018.

---

## Implementation Strategy

### MVP First (US1 only)

1. Phase 1 → Phase 2 → Phase 3.
2. Stop at the Phase-3 checkpoint, run `quickstart.md` Scenario A, commit & open the PR for partial review if you want a checkpoint commit.
3. The product is already usable from a paste-diff workflow.

### Incremental Delivery

1. Land Phase 3 (US1 MVP) → demonstrable.
2. Land Phase 4 (US2 URL fetch) → no regressions in US1; second demo scenario.
3. Land Phase 5 (US3 hardening) → SC-003/SC-004 satisfied; ready for external eyes.
4. Phase 6 polish before merging the PR.

### Single-Developer Strategy

There is no team here, so "parallel" means "task selection during the same focused session" rather than "two devs at once". The [P] markers help pick the next task without re-reading dependencies.

---

## Notes

- [P] = different file, no dependency on incomplete sibling task.
- [Story] tag is required only in Phases 3–5; Setup/Foundational/Polish carry no [Story] label.
- Every task lists exact file paths.
- No new ADR is required by this feature (per `plan.md` Constitution Check).
- No new docker-compose services; only env-var additions in `.env.example`.
