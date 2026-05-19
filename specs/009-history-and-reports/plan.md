# Implementation Plan: Review History & Reports

**Branch**: `009-history-and-reports` | **Date**: 2026-05-19 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/009-history-and-reports/spec.md`

## Summary

Persist every successful `POST /api/review` outcome (verdict + findings + provider + elapsed_ms + input shape + per-finding temporal context) into two new relational tables and expose three endpoints (`GET /api/reviews`, `GET /api/reviews/{run_id}`, `DELETE /api/reviews/{run_id}`). Ship a new SPA route `/history` (list) + `/history/<run_id>` (detail) that re-uses the existing `FindingsList` rendering branch — no second LLM call to reopen a stored run. Re-post and re-run affordances ride on top of the detail view.

Closes the MUST scope FR-3.3 (`parse → store report`), FR-5.1 (`report storage`), FR-5.2 (`History list, instant open without re-calling LLM`) from `_mvp_scope.md` §2.4 / §2.5 — currently the only unshipped slices of MUST.

This is a **hard-trigger** event on Constitution Principle II (DB schema change) — ADR-013 MUST be drafted in `_decision_log.md` BEFORE any production code lands. Plan.md surfaces this gate; tasks.md puts the ADR draft as Phase 1 Setup (T002), not polish.

## Technical Context

**Language/Version**: Python 3.12 (backend), TypeScript / Vue 3.5 (frontend).
**Primary Dependencies**: FastAPI, SQLAlchemy 2.x async + asyncpg, alembic, pydantic 2.x, structlog, arq (already pinned). Frontend: Vue 3.5, Vite 6, vue-router 4, `@tailwindcss/vite` 4. No new runtime dependency introduced — every persistence primitive (UUID PK, TIMESTAMPTZ default, FK ON DELETE CASCADE, JSONB) is already in play in `repos` / `code_chunks` / `app_settings`.
**Storage**: PostgreSQL 16 with pgvector extension. Two NEW tables: `review_runs` (run-level summary + the original normalised diff text) and `review_findings` (one row per emitted finding, with `temporal_context` stored as JSONB to preserve the per-finding history payload verbatim). One NEW composite B-tree index on `review_runs (created_at DESC, id)` to back the listing query. No pgvector usage — this is plain relational.
**Testing**: pytest with `pytest-asyncio` (already auto mode). Unit tests against `reviews_history/store.py` use an in-process SQLite-via-PostgreSQL-compat boundary? No — the existing async test stack uses the real Postgres test DB via the `async_client` fixture for integration; unit tests on the store will use the same `get_sessionmaker()` against the same test DB. No new test scaffolding required.
**Target Platform**: Linux x86_64 (API container) + evergreen desktop browsers (Chromium ≥ 120, Firefox ≥ 122, Safari ≥ 17).
**Project Type**: Web service (`backend/`) + Vue SPA (`frontend/`); monorepo layout (ADR-002).
**Performance Goals**: Persistence call ≤ 50 ms p95 (single INSERT for `review_runs` + bulk INSERT for `review_findings` + occasional DELETE for prune). Listing endpoint ≤ 30 ms p95 against the composite index. Detail endpoint ≤ 50 ms p95.
**Constraints**: Live `POST /api/review` latency MUST NOT regress (FR-003). DB persist is best-effort — wrapped in `try/except` so a transient DB outage doesn't bubble. Diff size cap inherits `review_max_diff_bytes` (200 KB). Retention cap 1000 rows hard-coded in v1 (no env-var, FR-017).
**Scale/Scope**: One bachelor-thesis host; ≤ 1000 stored runs in steady state; SPA shows top-50.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Status: **PASS (with ADR-013 prerequisite)** — DB-schema hard trigger crossed; ADR-013 to be drafted as Phase 1 task T002 before any code change.

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Spec-Driven Development (NON-NEGOTIABLE) | PASS | `/speckit-specify` produced `spec.md`; this `plan.md` precedes `/speckit-tasks` and any production code. |
| II. ADR-Driven Architectural Decisions (NON-NEGOTIABLE) | **TRIGGERED → SATISFIED via ADR-013 (to draft)** | DB schema change (two new tables + new index) crosses Principle II's hard trigger ("database schema or engine"). ADR-013 ("Persist review history in DB — `review_runs` + `review_findings` tables, ON DELETE SET NULL → repos, 1000-row LRU cap pruning, alembic revision 004") MUST land in `_decision_log.md` BEFORE the first ORM model is touched. `/speckit-implement` will block on this. |
| III. Pluggable AI Provider Boundaries | N/A | This feature does not invoke any `LLMProvider` / `EmbeddingProvider` directly. It only persists the LLM's already-parsed output. |
| IV. Privacy & Credentials Discipline | PASS | No credential is persisted into `review_runs` / `review_findings` — only the diff text + the parsed findings + metadata. The existing `app_settings` Fernet encryption boundary is untouched. The diff column may contain user source code (NFR-3.2 boundary) — but the diff was already POSTed across the host's localhost loopback, so persisting it on the same host is a no-op crossing of that boundary. |
| V. Single-Command Deployment | PASS | No new compose service; no new host-side volume; no new env var. The new tables ship via alembic migration `004_review_history.py` which is applied automatically by the existing API startup migration pass. |

**Async discipline** (Tech Stack §): all DB I/O via the existing `get_sessionmaker()` + SQLAlchemy 2.x async. The persist call inside `review/service.py:_run_chat` MUST be `await`-ed inside a `try/except` whose `except` branch only logs a structured warning and proceeds (FR-003 — DB failure MUST NOT block the live response). Pruning at startup runs via `arq` worker startup hook so it doesn't block API readiness.

**Test-first** (Dev Workflow §): `parse_review` is listed as a critical path — this feature does NOT touch parsing; it persists the parsed output. Critical paths added by this feature are the store's `insert_run` + `prune_to_cap` (failing unit tests committed before implementation per /speckit-tasks plan).

**Structured logging**: exactly one info entry per persist call (`review_persisted`, `run_id=…, finding_count=…, elapsed_ms=…, pruned=…`); plus one warning entry per persist failure (`review_persist_failed`, `reason=…`). No `print()`.

## Project Structure

### Documentation (this feature)

```text
specs/009-history-and-reports/
├── plan.md              # This file (/speckit-plan output)
├── spec.md              # /speckit-specify output (already on disk)
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output — entity sketches + DDL skeleton
├── quickstart.md        # Phase 1 output — manual smoke walkthrough
├── contracts/
│   ├── reviews_history_endpoints.md  # GET/GET-by-id/DELETE shapes + retention semantics
│   └── store_module.md               # Public surface of reviews_history/store.py
├── checklists/
│   └── requirements.md  # Spec quality checklist (all green)
└── tasks.md             # Generated by /speckit-tasks (NOT created here)
```

### Source Code (repository root)

Thin slice through the existing layout. No new top-level directory.

```text
backend/src/codesensei/reviews_history/        # NEW package
├── __init__.py
├── models.py            # ReviewRun + ReviewFinding SQLAlchemy models
├── store.py             # async CRUD: insert_run, list_runs, fetch_run, delete_run, prune_to_cap
├── api.py               # FastAPI router: GET /api/reviews, GET /:id, DELETE /:id
└── schema.py            # Pydantic wire models for listing + detail responses

backend/src/codesensei/review/
└── service.py           # MODIFIED — best-effort persist call appended to _run_chat after parse

backend/alembic/versions/
└── 004_review_history.py  # NEW — create_table x2 + create_index

backend/src/codesensei/main.py
└── (MODIFIED) include reviews_history.api router; trigger prune-on-startup

backend/tests/unit/
└── test_reviews_history_store.py   # NEW — CRUD + prune boundary

backend/tests/integration/
└── test_reviews_history_endpoint.py  # NEW — list/detail/delete + persist-on-review wiring

frontend/src/
├── api/
│   └── reviews.ts                    # NEW — listReviews / getReview / deleteReview / postFromHistory
├── pages/
│   ├── HistoryPage.vue               # NEW — list of runs + verdict filter chips
│   └── HistoryDetailPage.vue         # NEW — re-renders FindingsList + Re-run + Delete + PostToGitHubPanel
├── components/history/
│   └── RunRow.vue                    # NEW — single row in /history list
├── router.ts                         # MODIFIED — add /history + /history/:runId routes
└── components/AppShell.vue           # MODIFIED — 5th nav link "History" between "Repos" and "Settings"
```

**Structure Decision**: Single new backend package `reviews_history/` siblings `posting/`, `settings_store/`, `indexing/` — matches the established convention (one feature → one package containing `models.py + store.py + api.py [+ schema.py]`). One file edit in `review/service.py` (best-effort persist call). One new alembic revision. On the frontend: two new pages + one new row component + one new TS API client + one router edit + one shell edit. PostToGitHubPanel.vue is RE-USED as-is on the detail view (it already takes `diff`/`findings`/`verdict` as props, no edit needed).

## Complexity Tracking

> *Filled only when Constitution Check has unjustified violations.*

Constitution Check is PASS (conditional on ADR-013 draft). No row required.

## Phase 0: Outline & Research

Open questions captured during spec analysis and resolved in [`research.md`](./research.md):

- **R1** Why two tables, not one with a JSONB column for findings — preserves SQL-level joinability, lets us index by severity / file later without rewriting the schema, mirrors existing `repos` + `code_chunks` split.
- **R2** Why JSONB for `temporal_context` per finding — the shape ships verbatim from the LLM-parsed pydantic dataclass + per-finding routing; a relational sub-table for entries would be over-modelled for a payload we never query into.
- **R3** Why `ON DELETE SET NULL` on `repos` FK (not CASCADE) — preserves stored runs after `/repos` deletion (FR-020); the verdict is more durable than the repository handle.
- **R4** Why best-effort persist (try/except) and not transactional bundling with the live response — Constitution FR-003 + Principle IV: the live response is the canonical user-visible artefact; a DB outage MUST NOT regress the live latency or fail the user-facing call.
- **R5** Why prune-on-overflow inline AND once on startup — startup catches any prior excess (e.g. from a process crash mid-prune); inline keeps the cap tight without a recurring background job.
- **R6** Why 1000-row cap as a code-internal constant — operator-tunable knobs are out of scope (Out of Scope §); the cap is plenty for a single-user dev host.
- **R7** Why no `created_by` / multi-user column — single-user self-hosted v1 (Assumptions); a future auth layer would add this in its own ADR.
- **R8** Why the listing endpoint caps at 50 by default with up to 200 max — matches typical SPA "first page" behaviour; > 200 forces the operator to use pagination (out of scope) or query DB directly.
- **R9** How to pass the stored run's diff back to PostToGitHubPanel — the panel already accepts `diff` + `findings` + `verdict` as props; the detail page fetches the run via `GET /api/reviews/{run_id}` (which returns the diff) and feeds the same shape unchanged.
- **R10** Why store the diff verbatim (uncompressed) — 200 KB cap matches existing `review_max_diff_bytes`; PostgreSQL TOAST handles large TEXT columns natively; compression complexity is not worth it.
- **R11** Why the detail endpoint's response shape is byte-identical to the live `POST /api/review` response — re-uses the SPA's existing `FindingsList` rendering branch with zero conditional code (FR-007 / FR-019).
- **R12** Why the prune step uses `DELETE WHERE id IN (SELECT id FROM review_runs ORDER BY created_at ASC LIMIT N)` and not a CTE-based ranked delete — SQLAlchemy 2.x async + Postgres handles this cleanly; the `created_at` index makes the inner SELECT a single index scan.

**Output**: [research.md](./research.md) (PASS — every NEEDS CLARIFICATION-class question resolved).

## Phase 1: Design & Contracts

**Prerequisites**: research.md complete.

1. **Entities** → [data-model.md](./data-model.md):
   - `ReviewRun` (SQLAlchemy model + pydantic wire shape).
   - `ReviewFinding` (SQLAlchemy model + nested wire shape inside the detail response).
   - DDL skeleton mirroring `004_review_history.py`.

2. **Contracts** → [contracts/](./contracts/):
   - `reviews_history_endpoints.md` — `GET /api/reviews?limit=N`, `GET /api/reviews/{run_id}`, `DELETE /api/reviews/{run_id}`. Error envelope shape, status codes, retention semantics, latency budgets.
   - `store_module.md` — public surface of `backend/src/codesensei/reviews_history/store.py`: `insert_run`, `list_runs`, `fetch_run`, `delete_run`, `prune_to_cap`.

3. **Quickstart** → [quickstart.md](./quickstart.md): 8-step manual smoke — run two reviews, verify both in History, open detail, re-post, delete, re-run, verify retention.

4. **Agent context update**: bump CLAUDE.md SPECKIT marker to `specs/009-history-and-reports/plan.md` (done in `/speckit-implement` task T01).

**Output**: data-model.md, contracts/reviews_history_endpoints.md, contracts/store_module.md, quickstart.md, plus the agent-context bump.

## Constitution Check (Re-evaluation, post-design)

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Spec-Driven Development | PASS | spec → plan → research → data-model + 2 contracts → tasks. |
| II. ADR-Driven Decisions | PASS *if* ADR-013 lands in tasks.md T002 | The hard trigger is acknowledged; ADR-013 is queued as the SECOND task in /speckit-tasks (after scaffolding verification). |
| III. Pluggable AI Providers | N/A | No provider call touched. |
| IV. Privacy & Credentials | PASS | No new credential persisted. Diff stays on the same host. |
| V. Single-Command Deployment | PASS | No compose / volume / env-var addition. |

Design-time gate satisfied with the ADR-013 prerequisite. Proceed to `/speckit-tasks`.

## Notes for `/speckit-tasks`

- Three user stories, three priority bands. **P1 = persist + list + detail + delete**, the smallest valuable slice; **P2 = re-run + re-post on detail view**; **P3 = prune retention + verdict filter chips**.
- ADR-013 drafting is an early task (T002), NOT polish.
- Tests-before-code applies to: `reviews_history/store.py` (unit), `reviews_history/api.py` wiring + persist-on-review (integration). The frontend pages are smoke-tested manually via quickstart.md.
- Final-phase polish: README.md `/history` blurb + nav-link order; quickstart.md cross-link from README; verify backend full suite + frontend type-check + build clean.
