# Implementation Plan: Git Temporal Analysis

**Branch**: `008-git-temporal-analysis` | **Date**: 2026-05-19 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/008-git-temporal-analysis/spec.md`

## Summary

Deliver the third (and final) MUST differentiator promised in ADR-011: a per-line-window `git log -L` lookup that runs once per review against an indexed repository, feeds a compact "Code history hints" section to the LLM, and lands as a collapsible per-finding History disclosure on `/review`. The runtime cache lives entirely inside the API container under `/var/tmp/codesensei-temporal/`; no compose-yml change, no host-side volume, no new env-var exposure in v1. The wire shape changes additively: each `Finding` gains an optional `temporal_context: list[TemporalEntry] | null` field.

The implementation slots into the existing review pipeline at three points: (1) a new `review/git_temporal.py` module owning the clone cache + subprocess fan-out; (2) `review/service.py` calling that module after RAG retrieval but before LLM dispatch, then routing the in-memory pool back onto findings after parsing; (3) `review/prompt.py` injecting the hints block when the pool is non-empty. The frontend extends `FindingRow.vue` plus the `Finding` TS type — no new primitive component, no route change.

## Technical Context

**Language/Version**: Python 3.12 (backend), TypeScript / Vue 3.5 (frontend).
**Primary Dependencies**: FastAPI, httpx, asyncio (stdlib subprocess + TaskGroup), structlog, SQLAlchemy 2.x async, pydantic 2.x (backend); Vue 3.5, Vite 6, `@tailwindcss/vite` 4 (frontend). No new runtime dependency is introduced; `git` is already present in the API container image because the indexing pipeline shells out to it (`backend/src/codesensei/indexing/clone.py`).
**Storage**: PostgreSQL 16 + pgvector for the existing `repos` / `chunks` tables — read-only access through `indexing.store.fetch_repo(repo_id)` to resolve `repo.source`. No schema change, no migration. Runtime clone cache lives on the API container's writable filesystem at `/var/tmp/codesensei-temporal/<sha1(source)>/`; sized at 5 entries max with mtime LRU eviction.
**Testing**: pytest with `pytest-asyncio` and `respx` (both already pinned in `backend/pyproject.toml`). Unit tests build real synthetic git repositories under `tmp_path` via `subprocess.run`, then exercise the public async fetcher directly with a `_clone_for_test` monkeypatch hook that swaps the clone step for the tmp-path. Integration tests stub `fetch_temporal_context` with `unittest.mock.AsyncMock` and exercise `/api/review/run` end-to-end via the existing `async_client` fixture. No frontend Vitest in scope; manual smoke via `quickstart.md`.
**Target Platform**: Linux x86_64 (the API container's runtime); the SPA targets evergreen desktop browsers (Chromium ≥ 120, Firefox ≥ 122, Safari ≥ 17).
**Project Type**: Web service (`backend/`) + Vue SPA (`frontend/`); already in monorepo layout established by ADR-002.
**Performance Goals**: Per-call lookup ≤ 1.5 s wall clock; total temporal-collection budget per review ≤ 2.0 s; second review against the same repo on the same container completes its temporal phase in ≤ half the first-run time (cache amortisation, SC-005).
**Constraints**: Indexed-repo path adds ≤ 2.0 s wall-clock to overall review latency; diff-only path adds zero overhead (FR-010). Cache footprint stable at five entries (FR-016, SC-009). No blocking sync git call on the request path (FR-018). All subprocess outputs absorbed silently with a single structured warning log line per failed lookup (FR-019). Wire-compatible response shape (FR-022).
**Scale/Scope**: One bachelor-thesis-scale developer host; cache holds ≤ 5 indexed repos; ≤ 200 lines per line window after clamping. Plan keeps everything inside one repo / one container.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Status: **PASS** — no hard-trigger crossed.

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Spec-Driven Development (NON-NEGOTIABLE) | PASS | `/speckit-specify` produced `spec.md`; this `plan.md` precedes `/speckit-tasks` and any production code. |
| II. ADR-Driven Architectural Decisions (NON-NEGOTIABLE) | PASS | No DB schema/engine change, no queue change, no web framework change, no AI provider/embedding change, no deployment-shape change, no PR-comment-posting change. Soft-trigger record: append a paragraph to ADR-011 *Notes* documenting the runtime-cache shape (`/var/tmp/codesensei-temporal/`, LRU=5, per-call 1.5 s, total 2.0 s, code-internal defaults). **No new ADR is required**, because ADR-011 already anchors `git log -L` as a MUST differentiator — this feature is the shipping evidence of that decision, not a new architectural choice. |
| III. Pluggable AI Provider Boundaries | N/A | This feature does not call any `LLMProvider` / `EmbeddingProvider` directly. The only interaction with the LLM is via the existing prompt-assembly path inside `review/service.py`. |
| IV. Privacy & Credentials Discipline | PASS | Clones target the *public* `repo.source` HTTPS URL only; no PAT is read or sent. Subprocess `stderr` is parsed only for first-line summaries and not echoed back to the response body. Cache directory is container-internal — never serialised to the frontend. |
| V. Single-Command Deployment | PASS | No new compose service, no host-side volume, no `.env.example` change, no manual setup step. `git` is already in the API container image (used by `indexing/clone.py`). Cache directory is created lazily on first lookup. |

**Async discipline** (Tech Stack §): all git subprocess calls use `asyncio.create_subprocess_exec`; per-call timeout via `asyncio.wait_for`; per-file fan-out via `asyncio.TaskGroup`. No blocking call on the request path (FR-018).

**Test-first** (Dev Workflow §): retrieval / prompt assembly / parsing are listed in the "critical paths" bullet — this feature touches all three, so failing tests are committed before implementation in each `/speckit-implement` task chunk (see tasks.md).

**Structured logging**: exactly one info entry per review (`temporal_fetch`) summarising files looked up, entries collected, elapsed, budget-exceeded flag (FR-020); plus one warning entry per failed individual lookup (FR-019). No `print()` introduced.

## Project Structure

### Documentation (this feature)

```text
specs/008-git-temporal-analysis/
├── plan.md              # This file (/speckit-plan output)
├── spec.md              # /speckit-specify output (already on disk)
├── research.md          # Phase 0 output — see below
├── data-model.md        # Phase 1 output — wire-shape entities + cache model
├── quickstart.md        # Phase 1 output — manual smoke walkthrough
├── contracts/
│   ├── git_temporal_module.md   # Public surface of review/git_temporal.py
│   └── review_response.md       # Additive change to ReviewResult.findings[].temporal_context
├── checklists/
│   └── requirements.md  # Spec quality checklist (all green)
└── tasks.md             # Generated by /speckit-tasks (NOT created here)
```

### Source Code (repository root)

This feature is a thin slice through the existing web-application layout established by ADR-002. No new top-level directory is introduced.

```text
backend/src/codesensei/review/
├── git_temporal.py             # NEW — async fetch_temporal_context + clone-cache LRU
├── prompt.py                   # MODIFIED — inject "Code history hints" block when pool non-empty
├── schema.py                   # MODIFIED — TemporalEntry model + optional field on Finding
├── service.py                  # MODIFIED — call fetch_temporal_context post-RAG / pre-LLM; route pool back onto findings
├── github_diff.py              # READ-ONLY — already returns parsed hunks; reused to derive line windows
├── parser.py                   # UNCHANGED
├── router.py                   # UNCHANGED (response model passes through pydantic)
└── errors.py                   # UNCHANGED

backend/tests/unit/
└── test_git_temporal.py        # NEW — synthetic git repo under tmp_path

backend/tests/integration/
└── test_review_with_temporal.py  # NEW — mocked fetcher + full /api/review/run pipeline

frontend/src/
├── api/
│   └── review.ts                # MODIFIED — extend Finding type with optional temporal_context
└── components/findings/
    └── FindingRow.vue           # MODIFIED — render History <Collapsible> + volatility <Badge>
```

**Structure Decision**: Slice the existing `backend/src/codesensei/review/` module by adding **one** new file (`git_temporal.py`) and editing **three** existing files (`service.py`, `prompt.py`, `schema.py`). On the frontend, edit **two** files (`api/review.ts`, `components/findings/FindingRow.vue`). No new directories, no new primitives — the volatility badge reuses the in-tree `Badge` primitive shipped in feature 007, and the History disclosure reuses the in-tree `Collapsible` primitive from the same set.

## Complexity Tracking

> *Filled only when Constitution Check has unjustified violations.*

Constitution Check is PASS. No row required.

## Phase 0: Outline & Research

Open questions captured during spec analysis and resolved in [`research.md`](./research.md):

- **R1** Why `git log -L` and not `git blame` per line — picked `-L` because it follows line *ranges* (cheap O(touched commits) walk through the rev list) vs. `blame`'s O(file lines) walk; we collapse the diff into ≤ 3 windows per file and want the commit-level history, not per-line authorship.
- **R2** How to make the clone fast — `--filter=blob:none --no-checkout` skips blobs and working-tree materialisation, keeping commits + trees only. Empirically completes in ≤ 2 s for repos with ≤ 5 k commits on a warm host.
- **R3** Why `/var/tmp` and not `/tmp` — `/var/tmp` survives container PID-1 process restarts without `--rm`, which matches the LRU-across-requests semantics expected by SC-005. We still tolerate full container recreation blowing it away (Assumptions, spec.md).
- **R4** Cache key derivation — `sha1(repo.source)` (canonical form after `.git`-strip from `indexing/clone.py:normalise_source`) gives stable filesystem-safe directory names without revealing the URL to a casual `ls`.
- **R5** Eviction policy — mtime-based LRU using `os.stat(...).st_mtime`. On lookup, `touch` the cache root. When count exceeds the cap, `rmtree` the oldest. Eviction runs synchronously inside the lookup since it touches metadata only.
- **R6** Parallelisation of per-file lookups — `asyncio.TaskGroup` with a soft total-budget guard (cancel pending children on budget breach). Per-call `asyncio.wait_for` enforces the 1.5 s ceiling.
- **R7** How to derive line windows from PR diff — reuse `review/github_diff.py:parse_hunks()` already pinned by feature 003; collapse touched hunks per file into ≤ 3 windows; clamp each to 200 lines (FR-006).
- **R8** Subprocess hygiene — `asyncio.create_subprocess_exec` with explicit `cwd=`, `env={"GIT_TERMINAL_PROMPT": "0"}` to defeat interactive auth pops on private repos, and `stderr=PIPE` for one-line log extraction.
- **R9** Routing the in-memory pool back onto findings — keep a `dict[str, list[(window, entries)]]` keyed by file path; for each finding, walk its file's windows and pick the entries whose window contains `finding.line`. Strictly in-memory; no second git pass.
- **R10** "Volatility badge" threshold — three or more entries (FR-013). Picked 3 because a single rewrite + a fix is the normal cadence of "stable code being maintained"; ≥ 3 commits in the most recent five represents disproportionate churn against the typical baseline.
- **R11** Why no new env-var in v1 — operator surface area cost is high (compose docs, .env.example, README); user-tunable knobs are out of scope (Spec / Out of Scope). Code-internal constants in `git_temporal.py` are simple to relocate to env later if real operators ask.
- **R12** Why no schema migration — `temporal_context` is a transient compute output, not persisted. The DB doesn't change; the wire shape extends additively. Existing clients that don't know about the field continue to parse the payload (FR-022).

**Output**: [research.md](./research.md) (PASS — every NEEDS CLARIFICATION-class question resolved).

## Phase 1: Design & Contracts

**Prerequisites**: research.md complete.

1. **Entities** → [data-model.md](./data-model.md):
   - `TemporalEntry` (transient, in-memory + wire-shape on `Finding`).
   - `LineWindow` (transient, in-memory).
   - `FileTemporalPool` (transient, in-memory; keyed by file path; consumed twice — once for prompt assembly, once for finding-population).
   - `CachedClone` (filesystem-only; not persisted to DB, not on the wire).
   - **No DB schema delta** — the existing `repos` / `chunks` / `settings` tables are read-only here.

2. **Contracts** → [contracts/](./contracts/):
   - `git_temporal_module.md` — public signature of `review/git_temporal.py`: `async fetch_temporal_context(...)`, `async fetch_temporal_pool_for_review(...)`, the test-seam `_clone_for_test`, and the runtime-cache invariants.
   - `review_response.md` — additive change to the `/api/review/run` response: `findings[].temporal_context` is `list[TemporalEntry] | null`, optional, snake-case, never breaks existing clients.

3. **Manual-smoke walkthrough** → [quickstart.md](./quickstart.md): 8-step path — index a public repo, run a review against a PR touching a known volatile file, expand the History on a finding, verify the volatility badge on the most-touched finding, verify a fresh re-run is faster, verify the diff-only path is unaffected.

4. **Agent context update**: bump the SPECKIT marker in `CLAUDE.md` to point to `specs/008-git-temporal-analysis/plan.md` (done as the last step of `/speckit-implement`, see tasks.md T01).

**Output**: data-model.md, contracts/git_temporal_module.md, contracts/review_response.md, quickstart.md, plus the agent-context bump.

## Constitution Check (Re-evaluation, post-design)

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Spec-Driven Development | PASS | spec → plan → research → data-model + contracts → tasks (next phase). |
| II. ADR-Driven Decisions | PASS | No hard trigger crossed. The soft-trigger paragraph is appended to ADR-011 Notes during implementation (tasks.md T39). |
| III. Pluggable AI Providers | N/A | No provider call touched. |
| IV. Privacy & Credentials | PASS | Public clones only; no PAT use; cache stays container-internal. |
| V. Single-Command Deployment | PASS | No compose / volume / env-var addition. |

Design-time gate satisfied. Proceed to `/speckit-tasks`.

## Notes for `/speckit-tasks`

- Three user stories, three priority bands. P1 is end-to-end across `git_temporal.py` → `service.py` → `schema.py` → `FindingRow.vue`; P2 is `prompt.py` integration; P3 is the volatility-badge slice on `FindingRow.vue`.
- Tests-before-code applies to: `git_temporal.fetch_temporal_context` (unit), the `review/service.py` wiring (integration), and the prompt-assembly delta (unit on `review/prompt.py`).
- Final-phase polish: ADR-011 Notes paragraph + `README.md` blurb under `/review` describing the new disclosure.
