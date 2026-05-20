# Implementation Plan: MVP closure — custom-ignore + live index progress

**Branch**: `013-mvp-closure` | **Date**: 2026-05-21 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/013-mvp-closure/spec.md`

## Summary

Close two MUST-scope gaps from `_mvp_scope.md §2.3` in one feature pack. (1) Operators add a `.codesensei-ignore` file at the indexed repo root to extend the indexer's built-in skip rules with project-specific globs (no negation, no persistence-by-file — the file is re-read each index run; the parsed pattern list is persisted ON THE `repos` row as a new JSONB column so the `/repos` badge survives reload). (2) The SPA receives real-time index progress via a new `WebSocket` endpoint backed by a Redis pub/sub fan-out from the arq worker, while keeping the existing 2 s polling endpoint as a graceful fallback. One alembic migration adds the new column; one new backend module (`jobs_stream/`) holds the WS router + publisher; the indexer gains an `ignore.py` helper + an `extra_skip_globs` parameter on `iter_source_files`. Frontend introduces a `useJobStream` composable + a badge on the repo card + a Settings help section.

## Technical Context

**Language/Version**: Python 3.12 (backend), TypeScript 5.7 + Vue 3.5 (frontend)
**Primary Dependencies**: FastAPI (incl. `@app.websocket`), SQLAlchemy 2.x async, asyncpg, alembic, arq, redis-py (`redis.asyncio`), structlog, pydantic 2; vue-router 4, Vite 6, Tailwind v4 in-tree primitives.
**Storage**: PostgreSQL 16 (existing). Adds one nullable JSONB column to `repos`: `codesensei_ignore_patterns JSONB NULL`. Redis (existing) gains a pub/sub channel namespace `codesensei:job:<job_id>` — no new keyspace, no eviction policy change.
**Testing**: pytest + pytest-asyncio (existing), respx for HTTP mocks, `fakeredis.aioredis` for redis pub/sub tests. WS tested via `httpx.AsyncClient` against the FastAPI app (`websocket_connect`). No frontend Vitest in scope.
**Target Platform**: docker-compose-deployed self-hosted stack (api + worker + frontend + postgres + redis + optional ollama). Compose's frontend nginx ALREADY proxies `/api/` to api; needs `proxy_http_version 1.1` + `Upgrade`/`Connection` headers to pass WS upgrade — verified during research.
**Project Type**: web application (FastAPI backend + Vue SPA).
**Performance Goals**: WS first-frame ≤ 1 s after subscribe; ≤ 2 progress frames/s (coalesced). `.codesensei-ignore` parse: O(N) over file bytes, N ≤ 4 KB; pattern match cost: O(M × walked_paths) where M ≤ 200 — negligible vs the existing tree-sitter chunking cost.
**Constraints**: must not regress existing polling behaviour (FR-012). Must not change the public `GET /api/jobs/{id}` shape (existing tests pass unchanged). Single-user self-hosted threat model — no auth/CORS surface on the WS endpoint (matches the rest of the API).
**Scale/Scope**: thesis-demo workload — ≤ 1 active index job at a time; ≤ 200 patterns per ignore file; ≤ 10 concurrent SPA tabs subscribed to the same job (negligible fan-out cost on Redis).

## Constitution Check

| Principle | Verdict | Note |
|-----------|---------|------|
| **I. Spec-Driven** | ✓ pass | `spec.md` authored and validated before this plan. `tasks.md` follows before any production code. |
| **II. ADR-Driven** | ⚠️ HARD TRIGGER | Adding `codesensei_ignore_patterns JSONB NULL` to `repos` IS a DB schema change. ADDITIONALLY, exposing a new WebSocket transport on the FastAPI app is a SOFT trigger (new transport surface). **ADR-016 REQUIRED** in `_decision_log.md` BEFORE any production code, covering BOTH concerns in one entry: (a) the JSONB column shape + non-persistence-but-cached semantics for `.codesensei-ignore`; (b) the Redis pub/sub fan-out + WS endpoint contract + polling fallback policy. ADR-016 shape is fully described in `research.md` → §Decision: ADR-016 contents. `tasks.md` MUST place ADR-016 drafting as an early task (Phase 1 Setup), NOT polish. |
| **III. Pluggable AI Providers** | ✓ pass | No LLM or embedding adapter touched. The new `jobs_stream/` module deals with Redis pub/sub + WebSocket only — provider-agnostic. |
| **IV. Privacy & Credentials** | ✓ pass | `.codesensei-ignore` patterns are user-authored filenames/globs — not credentials. The WS stream carries progress integers + file paths from the indexed source tree (which already crossed the same boundary at clone time per NFR-3.2). No new credential surface, no debug-endpoint leak. |
| **V. Single-Command Deploy** | ✓ pass | No new docker-compose service. The existing nginx config inside `frontend/` may need ONE line tweaked to forward WS upgrade headers — that lives inside the existing frontend Dockerfile/nginx.conf, not a host-side step. No new env var. |
| **Async-by-default** | ✓ pass | `ignore.py` is pure-compute (allowed). The WS endpoint, the Redis subscriber, the publisher, and the indexer all stay `async`. No `time.sleep`, no blocking I/O introduced. |

**Phase 0 gate**: PASS (ADR-016 is required but deferred to `tasks.md` as the gating early task — per the Constitution this is the canonical pattern, matching ADR-013 in feature 009 and ADR-015 in feature 012).

## Project Structure

### Documentation (this feature)

```text
specs/013-mvp-closure/
├── plan.md                                    # This file (/speckit-plan output)
├── research.md                                # Phase 0 output
├── data-model.md                              # Phase 1 output
├── quickstart.md                              # Phase 1 output
├── contracts/
│   ├── codesensei_ignore_file.md              # File format + parser contract
│   ├── repos_response.md                      # RepoSummary/RepoDetail wire-shape addition
│   └── jobs_stream_ws.md                      # WS endpoint + Redis pub/sub contract
├── checklists/
│   └── requirements.md                        # Spec quality checklist (already complete)
└── tasks.md                                   # Phase 2 output (/speckit-tasks)
```

### Source Code (repository root)

```text
backend/
├── src/codesensei/
│   ├── indexing/
│   │   ├── ignore.py                          # NEW (parse_ignore_file + path_matches_any)
│   │   ├── chunker.py                         # MOD (iter_source_files accepts extra_skip_globs)
│   │   ├── service.py                         # MOD (load ignore spec, plumb patterns through)
│   │   ├── api.py                             # MOD (emit codesensei_ignore_patterns)
│   │   ├── schema.py                          # MOD (RepoSummary/RepoDetail extension)
│   │   └── models.py                          # MOD (ORM: codesensei_ignore_patterns column)
│   ├── jobs_stream/                           # NEW module
│   │   ├── __init__.py
│   │   ├── schema.py                          # InitFrame / ProgressFrame / CompleteFrame TypedDicts
│   │   ├── publisher.py                       # publish(redis, job_id, frame) → channel
│   │   └── router.py                          # WS /api/jobs/{job_id}/stream
│   ├── tasks.py                               # MOD (index_repo_job: publish progress + complete)
│   └── main.py                                # MOD (include jobs_stream.router)
├── alembic/versions/
│   └── 006_repos_codesensei_ignore.py         # NEW (down_revision=005_review_run_tokens)
└── tests/
    ├── unit/
    │   ├── test_codesensei_ignore.py          # NEW
    │   └── test_jobs_stream_publisher.py      # NEW
    └── integration/
        ├── test_indexing_endpoint.py          # MOD (+ test_index_honors_codesensei_ignore)
        └── test_jobs_stream_ws.py             # NEW

frontend/
├── src/
│   ├── composables/
│   │   └── useJobStream.ts                    # NEW (WS-first, polling fallback signal)
│   ├── api/
│   │   └── repos.ts                           # MOD (RepoEntry + codesensei_ignore_patterns)
│   └── pages/
│       ├── ReposPage.vue                      # MOD (wire useJobStream; render badge)
│       └── SettingsPage.vue                   # MOD (.codesensei-ignore help section)
└── (frontend nginx.conf inside Dockerfile may need WS-upgrade headers — verify during smoke)
```

**Structure Decision**: Backend + frontend mono-repo (existing CodeSensei layout). One new backend module (`jobs_stream/`) chosen over inlining into `indexing/api.py` because the WS endpoint is logically a TRANSPORT for `arq` job state — orthogonal to indexing-specific concerns. The publisher imports nothing from `indexing/`; the indexer imports nothing from `jobs_stream/` except `publisher.publish` at the call sites. This keeps the dependency arrow one-way (`tasks.py → jobs_stream.publisher`) and lets future job types (e.g. a review-batch job, deferred to 014+) reuse the same channel pattern.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| New JSONB column `codesensei_ignore_patterns` on `repos` (Constitution II hard trigger) | FR-014 says the `/repos` page badge must render after page reload. The patterns live in a file inside the source tree, which is wiped after indexing — so they have to be cached somewhere. The `repos` row is the natural cache key. | An ephemeral in-memory cache keyed by `repo_id` would not survive an api restart and would silently drift from the on-disk file. A separate table is over-modelled for one field. Returning the patterns only in the index-response payload (option B from research) breaks FR-014's "rendered on `/repos` page" intent on reload. |
| New WS transport on the FastAPI app (Constitution II soft trigger) | FR-007/008/009 require a real-time channel; polling at 2 s violates SC-002 ("within 1 s"). | Server-Sent Events would work but adds a third transport (existing polling stays as fallback regardless) for zero defence value. Long-poll would meet SC-002 only by tightening the interval, which is the same load profile as a coalesced WS. WS is the existing-stack-native answer (FastAPI ships `@app.websocket`, no new lib). |
