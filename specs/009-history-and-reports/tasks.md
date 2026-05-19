# Tasks — Feature 009: Review History & Reports

**Feature**: `009-history-and-reports`
**Plan**: [plan.md](./plan.md)
**Spec**: [spec.md](./spec.md)

Tests in scope per plan.md: backend pytest unit on `reviews_history/store.py` (CRUD + prune boundary), backend pytest integration on `/api/reviews` (list/detail/delete + persist-on-review wiring), backend pytest regression on existing `/api/review`. Manual frontend smoke via [quickstart.md](./quickstart.md). No Vitest.

**ADR-013 is a HARD gate** — drafted in T002 BEFORE any production code lands (Constitution Principle II is NON-NEGOTIABLE).

---

## Phase 1 — Setup

- [X] T001 Sync feature scaffolding: confirm `.specify/feature.json` points to `specs/009-history-and-reports`, confirm CLAUDE.md SPECKIT marker points to `specs/009-history-and-reports/plan.md`; both should already be set by `/speckit-plan` — verify-and-fix-if-needed.
- [X] T002 **(HARD GATE — Constitution Principle II)** Draft ADR-013 in `/Users/tarasivanov/Desktop/Диплом/_decision_log.md` (insert above ADR-012). Title: "Persist review history in DB — `review_runs` + `review_findings` tables". Status: accepted, date 2026-05-19. Decision lists: two tables + composite index on `(created_at DESC, id)`, `ON DELETE SET NULL` to `repos.id`, `ON DELETE CASCADE` from `review_runs` → `review_findings`, JSONB column for per-finding `temporal_context` (preserves feature-008 payload verbatim), retention 1000-row LRU cap pruned on overflow + at process startup, no env-var exposure in v1. Why: closes MUST-scope FR-3.3 / FR-5.1 / FR-5.2 from `_mvp_scope.md`. NFR-3.1 confirmation: no plaintext credentials persisted — only diff text + parsed findings + metadata. Supersedes nothing.

## Phase 2 — Foundational (blocking prerequisites for all user stories)

- [X] T003 Create new alembic revision `backend/alembic/versions/004_review_history.py` with `down_revision = "003_repos_chunks"`. `upgrade()` runs two `op.create_table` calls (`review_runs` + `review_findings`) per [data-model.md](./data-model.md) — UUID PKs via `gen_random_uuid()`, `created_at TIMESTAMPTZ` default `now()`, CHECK constraints on `input_kind`/`verdict`/`severity`, FK `review_runs.repo_id` → `repos.id` `ON DELETE SET NULL`, FK `review_findings.run_id` → `review_runs.id` `ON DELETE CASCADE`, `UNIQUE (run_id, position)`. Then `op.create_index("review_runs_created_at_id_idx", "review_runs", [sa.text("created_at DESC"), "id"])`. `downgrade()` reverses in the opposite order.
- [X] T004 Create package skeleton: `backend/src/codesensei/reviews_history/__init__.py` (empty), `reviews_history/models.py` (ORM models `ReviewRun` + `ReviewFinding` per [data-model.md](./data-model.md) ORM sketch), `reviews_history/schema.py` (pydantic wire shapes `ReviewRunSummary`, `ReviewRunDetail`, `ReviewRunListResponse`).
- [X] T005 Verify migration runs cleanly: from repo root run `cd backend && .venv/bin/alembic upgrade head` against the local test DB. Confirm both new tables + index exist; rollback works (`alembic downgrade 003_repos_chunks` then re-upgrade).

---

## Phase 3 — User Story 1 (P1) — Persist + list + detail + delete

**Goal**: Every successful review persists; `/history` lists runs; clicking a row opens a detail view that re-renders findings with no LLM call; "Delete this run" works.

**Independent test**: Run two reviews on `/review` (one diff-only, one PR-URL with indexed repo); `/history` shows both rows newest-first; click each → detail view matches what was shown live; delete one → row disappears; URL of deleted run resolves to a 404 "Run not found" empty state.

### Tests (TDD — failing tests committed first)

- [X] T006 [US1] Add `backend/tests/unit/test_reviews_history_store.py` with the CRUD + invariants suite per [contracts/store_module.md](./contracts/store_module.md): (a) `insert_run` writes `review_runs` + N `review_findings` ordered by position; (b) `fetch_run` returns findings ordered by position ASC; (c) `delete_run` cascades; (d) `list_runs(limit=50)` returns newest-first; (e) `has_temporal` truthiness from a finding with non-null `temporal_context`; (f) FK `ON DELETE SET NULL` on `repos.id` keeps the run alive after `repos_store.delete_repo_by_id`. Uses the existing test DB sessionmaker.
- [X] T007 [P] [US1] Add `backend/tests/integration/test_reviews_history_endpoint.py` with: (a) `GET /api/reviews` after a successful `POST /api/review` returns the new run as the topmost row; (b) `GET /api/reviews/{run_id}` returns full payload with findings array + temporal_context preserved verbatim; (c) `GET /api/reviews/{run_id}` for a non-existent UUID returns 404 with the `ReviewError` envelope `category="invalid_input"`; (d) `DELETE /api/reviews/{run_id}` returns 204 + subsequent GET returns 404; (e) `GET /api/reviews?limit=N` clamps `limit` to `1..200`; (f) `POST /api/review` with a provider error does NOT create a row.

### Implementation

- [X] T008 [US1] Implement `backend/src/codesensei/reviews_history/store.py`: `insert_run`, `list_runs`, `fetch_run`, `delete_run` async functions per [contracts/store_module.md](./contracts/store_module.md). Use SQLAlchemy 2.x async ORM (mirror `backend/src/codesensei/indexing/store.py` style). All functions commit before returning. `insert_run` derives `has_temporal = any(f.temporal_context for f in findings)`.
- [X] T009 [P] [US1] Implement `backend/src/codesensei/reviews_history/api.py`: FastAPI APIRouter on prefix `/api/reviews`. Routes: `GET /` (list, query `limit`), `GET /{run_id}` (detail), `DELETE /{run_id}` (204/404). Convert ORM → pydantic via `model_validate` per [data-model.md](./data-model.md). 404 raises `ReviewError(category="invalid_input", "Review run not found.")` translated by the existing exception handler.
- [X] T010 [US1] Wire the router in `backend/src/codesensei/main.py`: import `reviews_history.api.router`, call `app.include_router(reviews_history_router)`. Mirror the include pattern of the existing `posting`/`indexing`/`settings_store` routers.
- [X] T011 [US1] Modify `backend/src/codesensei/review/service.py:_run_chat`: after the existing `return ReviewResult(...)` is fully composed, but BEFORE returning, persist the run via a best-effort `try/except` block. Build the persist call inside a new `async with sessionmaker() as session:` block; on any exception, `_logger.warning("review_persist_failed", reason=str(exc)[:200])` and proceed. The `try` block calls `reviews_history.store.insert_run(...)`. Schema mapping: `input_kind = "pr_url" if pr_url_was_used else "diff"`, `pr_url`, `repo_id`, `diff`, `verdict`, `provider`, `elapsed_ms`, `findings` (use the `findings` list already in scope), `context_files`. On success, log `_logger.info("review_persisted", run_id=str(run.id), finding_count=len(findings))`. **Persist runs ONLY when `findings` is set (no exception thrown earlier in the function)** — this respects FR-004 (failed reviews not stored).
- [X] T012 [US1] Modify `backend/src/codesensei/review/service.py:_run_chat` signature to thread `pr_url` and `original_diff` from `run_for_url` (which currently fetches the diff but doesn't surface the original URL). Add a keyword-only parameter `original_pr_url: str | None = None` passed by `ReviewService.run_for_url` so persistence can record the user's input shape correctly.
- [X] T013 [P] [US1] Add `frontend/src/api/reviews.ts`: typed wrapper for `listReviews(limit?)`, `getReview(runId)`, `deleteReview(runId)`. Reuse the `ReviewApiError` class from `frontend/src/api/review.ts` (re-export or import). Type `ReviewRunSummary` + `ReviewRunDetail` interfaces matching the contract.
- [X] T014 [P] [US1] Add `frontend/src/components/history/RunRow.vue`: single row card showing relative timestamp (computed via `Intl.RelativeTimeFormat`), verdict pill (re-use `<Badge tone="info|success|danger">` mapping `approve→success|comment→info|request_changes→danger`), provider badge, finding count, optional `<a>` to `pr_url` (preventDefault on bubble so click on the link doesn't trigger row-click), and `has_temporal` indicator. Emits `click` event with `runId`.
- [X] T015 [US1] Add `frontend/src/pages/HistoryPage.vue`: on mount call `listReviews()`, store result in `ref<ReviewRunSummary[]>`. Render a Card wrapping a list of `<RunRow>` instances. Each row click navigates to `/history/<runId>` via `useRouter().push`. Skeleton during in-flight load. Empty state when zero rows. Surface load errors via the existing toast queue.
- [X] T016 [US1] Add `frontend/src/pages/HistoryDetailPage.vue`: takes route param `runId` as a prop. On mount calls `getReview(runId)`. Renders a Card with run metadata (created_at full timestamp, verdict, provider, elapsed_ms, optional pr_url link) + the existing `<FindingsList :findings="run.findings">` block re-using feature 007 + 008 rendering. Includes a "Delete this run" Button calling `deleteReview(runId)` → on success toast + `router.push('/history')`. Includes a "Re-run" Button (US2 — implemented in T021). Includes a `<PostToGitHubPanel>` when `run.input_kind === 'pr_url'` (US2 — wiring in T022). Friendly "Run not found" empty state on 404.
- [X] T017 [US1] Modify `frontend/src/router.ts`: add `{ path: '/history', component: HistoryPage }` and `{ path: '/history/:runId', component: HistoryDetailPage, props: true }`. Both lazy-loaded via `() => import('@/pages/HistoryPage.vue')` etc., matching the pattern of existing routes.
- [X] T018 [US1] Modify `frontend/src/components/AppShell.vue`: add 5th `<RouterLink>` "History" between "Repos" and "Settings". Mirror the styling of the existing 4 links.
- [X] T019 [US1] Frontend type-check + build guard: run `corepack pnpm -C frontend exec vue-tsc --noEmit && corepack pnpm -C frontend exec vite build` from repo root; confirm both exit 0 and JS bundle size grew by ≤ 8 KB gzipped vs feature 008 baseline.

**Checkpoint**: US1 complete → backend pytest green (unit + integration), frontend type-check + build clean. Reviewer can run a review, see it in `/history`, open a detail view, delete a run.

---

## Phase 4 — User Story 2 (P2) — Re-run + re-post from history

**Goal**: Detail view of a PR-URL run shows the `<PostToGitHubPanel>` ready to publish the stored findings; any detail view shows a "Re-run" Button that POSTs to `/api/review` with the stored input.

**Independent test**: Open the detail view of a stored PR-URL run → click "Post to GitHub" → toast confirms success + PR comment appears on GitHub. Click "Re-run" → a fresh run appears at top of `/history`; original stays.

### Implementation

- [X] T020 [US2] In `frontend/src/pages/HistoryDetailPage.vue` add the `<PostToGitHubPanel>` mount that the US1 stub left in place. Wire props: `diff = run.diff`, `verdict = run.verdict`, `findings = run.findings`, `pr_url = run.pr_url`. Conditionally render only when `run.input_kind === 'pr_url'`. The panel ships from feature 006 already — no panel edit needed; verify the existing prop shape accepts what we pass.
- [X] T021 [US2] In `frontend/src/pages/HistoryDetailPage.vue` implement the "Re-run" Button click handler: call `runReview({ diff: run.diff })` for `diff` runs OR `runReview({ pr_url: run.pr_url, repo_id: run.repo_id })` for `pr_url` runs. On success → toast + navigate to `/history` (the persist hook on the server side will surface the fresh run at the top).
- [X] T022 [P] [US2] Verify the existing `frontend/src/components/PostToGitHubPanel.vue` prop interface accepts `pr_url` as a prop. If it currently sources `pr_url` from a parent ref instead of props, refactor minimally to accept it as a prop (no behaviour change for the live `/review` page).

**Checkpoint**: US2 complete → re-post + re-run work from the detail view; original stays in history.

---

## Phase 5 — User Story 3 (P3) — Retention prune + verdict filter chips

**Goal**: 1000-row LRU cap enforced via inline prune after every persist AND a one-shot startup prune. `/history` page has verdict filter chips that narrow the loaded 50-row list client-side; URL preserves the chip state.

**Independent test**: Insert 1005 rows programmatically → after the next live review (which triggers prune), exactly 1000 rows survive; 5 oldest detail URLs return 404. On `/history`, click "approve" chip → only approve rows visible; URL becomes `?verdict=approve`; refresh preserves filter.

### Tests

- [X] T023 [US3] Extend `backend/tests/unit/test_reviews_history_store.py` with the prune-boundary suite: (a) `prune_to_cap` returns 0 when count ≤ 1000; (b) after inserting 1001 rows, `prune_to_cap` returns 1 and the oldest row is gone; (c) after inserting 1100 rows, `prune_to_cap` returns 100 and the 100 oldest are gone; (d) prune cascades to `review_findings` (no orphaned findings).
- [X] T024 [US3] Extend `backend/tests/integration/test_reviews_history_endpoint.py` with the overflow test: insert 1001 rows by repeatedly POSTing minimal `/api/review` calls; verify `GET /api/reviews?limit=200` returns exactly 1000 rows.

### Implementation

- [X] T025 [US3] Implement `prune_to_cap(session)` in `backend/src/codesensei/reviews_history/store.py` per [contracts/store_module.md](./contracts/store_module.md): `DELETE FROM review_runs WHERE id IN (SELECT id FROM review_runs ORDER BY created_at ASC LIMIT :overflow)` where `overflow = max(0, count - _HISTORY_MAX_ROWS)`. Returns the row-count deleted. Commits before returning.
- [X] T026 [US3] In `backend/src/codesensei/review/service.py:_run_chat`, after the `insert_run` call in the same `async with sessionmaker()` block, call `await prune_to_cap(session)` inside the same try/except. The persist log entry becomes `_logger.info("review_persisted", run_id=..., finding_count=..., pruned=N)` carrying the prune count.
- [X] T027 [US3] In `backend/src/codesensei/main.py`, register an app startup hook: `@app.on_event("startup")` async function that opens a session via `get_sessionmaker()` and calls `await prune_to_cap(session)` once, then closes. Wrap in try/except — failure logs warning but does NOT block startup.
- [X] T028 [US3] In `frontend/src/pages/HistoryPage.vue` add verdict filter chips: three `<Badge>` elements ("approve" / "request_changes" / "comment") rendered as clickable filter buttons. Active chip(s) drive a `computed` that filters the loaded `runs` array client-side. URL sync via `useRoute().query.verdict` (read on mount + write via `router.replace({ query: { verdict } })` on chip click). Chips re-use existing `Badge` primitive with a custom click handler.
- [X] T029 [US3] Frontend type-check + build guard: run the same commands as T019; confirm clean.

**Checkpoint**: US3 complete → retention cap stable; filter chips work + URL persists.

---

## Phase 6 — Polish & Cross-Cutting

- [X] T030 [P] Update `README.md` `/` section: append a sentence under the `/review` blurb mentioning that every successful run is auto-saved and reopenable from `/history`. Add a new bullet for `/history` listing what the page shows. Append a link to `specs/009-history-and-reports/quickstart.md` in the existing quickstart-link cluster.
- [X] T031 [P] Run backend lint + format gate: `cd backend && .venv/bin/ruff check src/codesensei/reviews_history/ src/codesensei/review/service.py tests/unit/test_reviews_history_store.py tests/integration/test_reviews_history_endpoint.py` and `.venv/bin/ruff format --check` on the same paths. Fix any flagged files this feature introduced.
- [X] T032 Run new test suite: `cd backend && .venv/bin/python -m pytest tests/unit/test_reviews_history_store.py tests/integration/test_reviews_history_endpoint.py -q` — confirm all green.
- [X] T033 Run full backend test suite (regression guard): `cd backend && .venv/bin/python -m pytest -q` — confirm green; existing `/api/review` tests must pass unchanged.
- [X] T034 Run frontend type-check + build: `corepack pnpm -C frontend exec vue-tsc --noEmit && corepack pnpm -C frontend exec vite build` → exit 0; bundle size grew ≤ 8 KB gzipped vs feature-008 baseline.
- [X] T035 Manual smoke per `specs/009-history-and-reports/quickstart.md` Steps 1–8 — deferred to the user per project convention.
- [X] T036 Mark all task checkboxes `[X]` in this file at the end of `/speckit-implement` (standard final-step convention).

---

## Dependencies

```
Phase 1 Setup (T001–T002) ─┐
                            │  ADR-013 (T002) is a HARD gate — blocks T003 onward
Phase 2 Foundational (T003–T005) ─┤
                                  │
                                  ├─► Phase 3 US1 (T006–T019)
                                  │
                                  ├─► Phase 4 US2 (T020–T022) [depends on US1 detail page]
                                  │
                                  └─► Phase 5 US3 (T023–T029) [depends on US1 persist + list page]

Phase 6 Polish (T030–T036) requires all prior phases done.
```

- US2 depends on US1's `HistoryDetailPage.vue` skeleton (T016).
- US3's frontend chip work depends on US1's `HistoryPage.vue` (T015).
- US2 and US3 do NOT depend on each other.

## Parallel opportunities

- T006 + T007 + T013 + T014 can run in parallel (different files).
- T009 + T013 can run in parallel.
- T022 + T028 can run in parallel.
- T030 + T031 can run in parallel.

## Implementation strategy

- **MVP scope = US1 only** (T001–T019). Ships persist + list + detail + delete end-to-end; the smallest fully-useful slice.
- US2 (re-run + re-post) and US3 (prune + filters) are additive and can ship in either order after US1.
- Polish (Phase 6) ships at the end of `/speckit-implement` together with the single commit at the pipeline boundary.

## Independent-test criteria per story

- **US1**: Run two reviews on `/review` → `/history` shows both newest-first; click each → detail view matches; delete one → row disappears; re-open URL → "Run not found".
- **US2**: Open a stored PR-URL run → click "Post to GitHub" → publishes; click "Re-run" → fresh row appears in `/history`.
- **US3**: Insert 1005 rows → after next live review, exactly 1000 remain; on `/history`, verdict chips filter the visible list + URL persists.

## Format validation

All 36 tasks above start with `- [X]`, carry a `Txxx` ID, the appropriate `[P]` and `[US?]` markers (Setup/Foundational/Polish phases carry no story label), and reference at least one concrete file path or contracted document.
