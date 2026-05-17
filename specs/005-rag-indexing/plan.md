# Implementation Plan: Repo indexing + RAG-augmented review

**Branch**: `005-rag-indexing` | **Date**: 2026-05-17 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/005-rag-indexing/spec.md`

## Summary

Adds a repository-indexing pipeline and bolts retrieval onto the existing `/api/review` endpoint. Two new tables (`repos`, `code_chunks`) under a fresh alembic migration. A new `codesensei.indexing` package: language-aware chunking (Python via `ast`, JS/TS/Java/Go via fixed-line sliding window, Markdown by heading), embedding through the existing `EmbeddingProvider` abstraction from feature 002, persistence into pgvector with an HNSW index per ADR-004. Sync path for ≤200-file repos; async path enqueues a new `index_repo_job` against the arq queue scaffolded in feature 004 and surfaces status through the existing `/api/jobs/{id}` endpoint. `/api/review` gains an optional `repo_id`; when present, the review service derives per-hunk semantic queries, fetches top-K chunks under a token budget, and stitches them into the LLM prompt as a "Relevant context from repository" block — with the existing diff-only path preserved for `repo_id == null`. A new `/repos` Vue page lets the reviewer manage repositories; `/review` gains a context-repo selector. Embedding-model mismatch (provider/model recorded at index time vs. currently configured) is detected and refused with a clear error to avoid silently querying across two vector spaces.

## Technical Context

**Language/Version**: Python 3.12+ (backend), TypeScript 5.7 + Vue 3.5 + Vite 6 (frontend).
**Primary Dependencies (backend, new)**: `tree-sitter-languages` is **rejected** in favour of stdlib `ast` (Python only) + line-based fallback windows — keeps the dependency footprint tight (R2). `tiktoken>=0.7` (NEW — required by Constitution §"Pre-flight token counting" for the prompt-budget enforcement in FR-018; no provider-equivalent for Anthropic/Ollama, so `tiktoken` is the single source of truth on token counts). `aiofiles>=24` (NEW — async file reads in the chunker so the indexing flow stays fully async per Constitution §"Async by default"; `asyncio.to_thread` is the fallback we considered and rejected in R3 because the chunker walks thousands of files).
**Primary Dependencies (backend, reused)**: FastAPI, SQLAlchemy 2.x async + asyncpg, alembic, `pydantic`, `structlog`, `arq>=0.26` (from feature 004), `cryptography` (from feature 004 — only indirectly: the embedding-provider model name we record was set through the 004 Settings store). pgvector ≥0.7 (already enabled via alembic 001).
**Primary Dependencies (frontend, new)**: none. Vue 3 + vue-router from 003 cover everything.
**Storage**: PostgreSQL 16 with pgvector. Two new tables under alembic migration `003_repos_chunks`:
- `repos(id uuid PK default gen_random_uuid(), source text not null, source_kind text not null check in ('https','local'), default_branch text null, embedding_provider text null, embedding_model text null, indexed_at timestamptz null, chunk_count int not null default 0, last_error text null, created_at timestamptz not null default now())` with `unique (source)` so re-submitting the same URL hits the same row.
- `code_chunks(id uuid PK default gen_random_uuid(), repo_id uuid not null references repos(id) on delete cascade, file_path text not null, language text not null, start_line int not null, end_line int not null, content text not null, token_count int not null, embedding vector(1536) not null)` with `index code_chunks_embedding_hnsw using hnsw (embedding vector_cosine_ops)` per ADR-004 (cosine ops — see R5; ADR-004 names HNSW but is operator-agnostic so this plan picks cosine to match what OpenAI's `text-embedding-3-small` returns natively).
**Testing**: pytest + pytest-asyncio + `respx` (existing), `pytest-postgresql` or live container DB for the few integration tests that need a real pgvector to assert HNSW behaviour. Unit tests use `AsyncMock` of `EmbeddingProvider.embed` and an in-memory fake `code_chunks` store to exercise the retrieval algorithm without a DB round-trip.
**Target Platform**: Linux container, same docker-compose `api` and `worker` services from features 001/004. **One Dockerfile change**: install `git` into the `api` and `worker` images so the indexing service can shell out to clone repos. This is the only host-side requirement that changes — fully covered by the image build per Constitution V.
**Project Type**: Web service (`backend/` FastAPI + `frontend/` Vue SPA + `worker/` arq runner) — same layout as features 001/002/003/004.
**Performance Goals**: SC-002 — 200 source files end-to-end ≤ 90 s on OpenAI `text-embedding-3-small` (the documented cheapest configuration). SC-003 — RAG path adds ≤ 25 % to median diff-only review latency. SC-004 — ≥ 80 % of test reviews on commits drawn from this repo show non-empty `context_files`. SC-005 — retrieved-context bundle ≤ 3 000 tokens (the budget — see R6) in every test run.
**Constraints**: 5 000-chunk hard cap per repo (FR-005). Synchronous threshold at ≤ 200 source files (FR-006). Top-K = 5 per derived query (R7). Token-budget = 3 000 tokens of retrieved context (R6). HNSW index built once per migration; ANALYZE deferred (`autovacuum` handles it; the V1 dataset is small enough that the planner's cold stats are adequate — see R8). Embedding-model mismatch refuses retrieval (FR-021) with HTTP 422 `embedding_mismatch`.
**Scale/Scope**: Single-tenant deployment. Anticipated steady-state: ≤ 5 indexed repositories, ≤ 25 000 chunks total across all repos. One indexing job active at a time per repo (FR-013 atomicity); concurrent reviews across different repos allowed.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Justification |
|-----------|:-----:|---------------|
| **I. Spec-Driven Development** | ✅ | `spec.md` (24 FRs / 4 USs / 7 SCs), this plan, `checklists/requirements.md` (16/16 PASS) all exist. `/speckit-tasks` produces `tasks.md` before any production code lands. |
| **II. ADR-Driven Architectural Decisions** | ⚠ → ✅ | Three architectural touches need ADR coverage. (a) pgvector HNSW index choice is **already** ratified by ADR-004 — no new ADR. (b) The retrieval algorithm (per-hunk query derivation + cosine top-K + token-budget trim) is a new RAG strategy → **new ADR-009: "RAG retrieval strategy = per-hunk semantic queries, top-K=5 cosine, 3 000-token budget"**, appended to `../_decision_log.md` before any retrieval code is written. (c) The async-vs-sync indexing threshold (200 files) is a deployment-shape decision → **new ADR-010: "Sync indexing threshold = 200 source files, async via 004's arq queue, no review-job migration"**, also appended before implementation. Both are draft-ready in `research.md` §R1 and §R4. |
| **III. Pluggable AI Provider Boundaries** | ✅ | The indexing service and the retrieval service both consume `codesensei.providers.get_embedding_provider()` exclusively. Zero direct imports of `openai` / `sentence_transformers`. The provider/model names that are persisted onto `repos.embedding_provider`/`embedding_model` are read **through** the provider abstraction at write time (R9). FR-021 (embedding-model mismatch refusal) is the runtime enforcement of this principle — switching the embedding provider in `/settings` (feature 004) must not silently corrupt retrieval. |
| **IV. Privacy & Credentials Discipline** | ✅ | Source code being indexed is sent to the configured embedding provider as chunks — explicitly permitted by Constitution IV ("User source code MUST NOT leave the self-hosted boundary except as chunks sent to embedding or LLM APIs"). No new credentials are introduced. Cloned repos land in a per-request tmpdir that is cleaned up in a `finally` block; the chunker streams files, never copying them into long-lived storage. `repos.source` stores public URLs / local paths — no tokens, no PATs (only public HTTPS clones are supported in V1 per Assumptions). Indexing emits a structured log line carrying provider/model/chunk-count/duration but **never** chunk content (R10). |
| **V. Single-Command Deployment** | ✅ | One Dockerfile line: `RUN apt-get install -y git` in `backend/Dockerfile` (shared by `api` and `worker` images per 004 layout). No new compose services. No new host-side env vars are mandatory — embedding-provider/model continues to come from feature-004's Settings store and `.env`. The `/repos` page is a new Vue route inside the existing `frontend` service. |

**Verdict**: PASS with two ADRs (ADR-009 + ADR-010) to be appended to `../_decision_log.md` before implementation begins (see Phase 0). No Complexity-Tracking entries needed.

## Project Structure

### Documentation (this feature)

```text
specs/005-rag-indexing/
├── plan.md                      # This file
├── spec.md                      # Already written (/speckit-specify)
├── research.md                  # Phase 0 — written below
├── data-model.md                # Phase 1 — written below
├── quickstart.md                # Phase 1 — written below
├── contracts/
│   ├── api_index.md             # POST /api/index + GET /api/repos + DELETE /api/repos/{id}
│   ├── api_review_v2.md         # POST /api/review (delta: repo_id input, context_files output)
│   ├── llm_prompt_v3.md         # SYSTEM/USER prompt with "Relevant context from repository" block
│   ├── retrieval_algorithm.md   # Per-hunk query derivation + top-K + token-budget trim
│   └── index_repo_job.md        # arq job signature + status transitions
├── checklists/
│   └── requirements.md          # Already written (16/16 PASS)
└── tasks.md                     # Phase 2 (/speckit-tasks — separate command)
```

### Source Code (repository root)

```text
backend/
├── alembic/versions/
│   └── 003_repos_chunks.py            # NEW — repos + code_chunks tables, HNSW index
├── src/codesensei/
│   ├── indexing/                      # NEW package
│   │   ├── __init__.py
│   │   ├── api.py                     # POST /api/index, GET /api/repos, DELETE /api/repos/{id}
│   │   ├── chunker.py                 # ast-based + line-window + Markdown chunkers
│   │   ├── clone.py                   # async git clone via subprocess, tmpdir lifecycle
│   │   ├── errors.py                  # IndexError categories: invalid_input, payload_too_large, clone_failed, embedding_failed, queue_unavailable, embedding_mismatch
│   │   ├── models.py                  # SQLAlchemy mapped: Repo, CodeChunk
│   │   ├── service.py                 # Orchestrates clone → chunk → embed → upsert (sync) | enqueue (async)
│   │   ├── store.py                   # Atomic chunk replacement (FR-013) via "staging schema + swap" pattern
│   │   ├── retrieval.py               # derive_queries(diff) → embed → SQL `<=>` top-K → trim by token budget
│   │   └── tasks.py                   # index_repo_job: same signature as ping_job, lives in tasks/ for arq import path; re-exported from worker.py functions list
│   ├── review/
│   │   ├── service.py                 # MODIFIED — accept repo_id, call retrieval before LLM, attach context_files to ReviewResult
│   │   ├── schema.py                  # MODIFIED — ReviewRequest.repo_id: UUID | None; ReviewResult.context_files: list[str] | None
│   │   └── prompt.py                  # MODIFIED — USER_TEMPLATE adds optional {repository_context} section
│   ├── tasks/
│   │   └── worker.py                  # MODIFIED — extend WorkerSettings.functions with index_repo_job
│   └── main.py                        # MODIFIED — mount indexing router under /api
└── tests/
    ├── unit/
    │   ├── test_indexing_chunker.py   # ast splits, Markdown by ##, sliding-window overlap, binary skip
    │   ├── test_indexing_service.py   # mock EmbeddingProvider, assert cap enforcement + atomic swap
    │   ├── test_retrieval.py          # query-derivation determinism, token-budget trim, mismatch refusal
    │   ├── test_index_repo_job.py     # arq job idempotency: 2× enqueue → 1× chunk-set
    │   └── test_review_with_context.py# review.run_for_diff with repo_id=...: prompt assembly + context_files surfaced
    └── integration/
        ├── test_index_endpoint.py     # POST /api/index sync → 201; payload-too-large → 413; clone_failed → 502
        ├── test_repos_endpoint.py     # GET /api/repos ordering; DELETE cascade
        ├── test_review_with_repo.py   # POST /api/review with repo_id → context_files non-empty; unknown repo_id → 400
        └── test_pgvector_search.py    # one real-DB test: HNSW top-K + distance ordering

frontend/
├── src/
│   ├── api/
│   │   ├── repos.ts                   # NEW — typed listRepos/createIndex/deleteRepo/getJob
│   │   └── review.ts                  # MODIFIED — add repo_id to runReview() input, context_files to result type
│   ├── pages/
│   │   ├── ReposPage.vue              # NEW — form + list + delete/reindex
│   │   └── ReviewPage.vue             # MODIFIED — add repo selector (hidden when repos empty)
│   ├── components/
│   │   ├── RepoForm.vue               # NEW — URL + default branch input
│   │   ├── RepoList.vue               # NEW — table with status pills + actions
│   │   └── ContextFilesPanel.vue      # NEW — collapsible "files that contributed context" widget
│   ├── router.ts                      # MODIFIED — add /repos route + topnav link
│   └── App.vue                        # MODIFIED — topnav: + Repositories link
```

**Structure Decision**: Identical web-service layout (`backend/` + `frontend/`) used by 001/002/003/004; one new backend package (`codesensei.indexing`), one frontend page, one frontend API client. The indexing job lives under `codesensei.indexing.tasks` rather than `codesensei.tasks` so all RAG concerns are co-located, then explicitly re-exported into `tasks.worker.WorkerSettings.functions`. The model `Repo` does **not** subclass anything from `codesensei.tasks.models` — it is its own SQLAlchemy `DeclarativeBase` slice (`codesensei.indexing.models.Base`), and the alembic env autogen will pick it up via the existing `target_metadata` registry.

## Complexity Tracking

*Empty — Constitution Check passed.*
