# Implementation Plan: UX polish — drop Recent row, reformat tokens, write README

**Branch**: `014-ux-polish-and-readme` | **Date**: 2026-05-21 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/014-ux-polish-and-readme/spec.md`

## Summary

Three small surface-only changes bundled as one PR. (1) Drop the per-call token/cost line from `/review`. (2) Shorten the `/history/<id>` token line to a single total + cost. (3) Add an "Embedding tokens" row to each `/repos` card sourced from a read-time `SUM(code_chunks.token_count) GROUP BY repo_id` aggregate (no new column). Also remove the duplicate "Recent:" chip strip from `/review` (the `<datalist>` autocomplete covers the same UX). Rewrite `README.md` to a defence-grade project intro with thesis context, three differentiators per ADR-011, 5-step quick start, brief architecture, features overview, docs map.

## Technical Context

**Language/Version**: Python 3.12 (backend), TypeScript 5.7 + Vue 3.5 (frontend)
**Primary Dependencies**: FastAPI, SQLAlchemy 2.x async, asyncpg, structlog, pydantic 2; vue-router 4, Vite 6, Tailwind v4 in-tree primitives.
**Storage**: PostgreSQL 16 with pgvector (existing). NO schema change. New aggregate query reads existing `code_chunks.token_count` column (introduced in feature 005 / ADR-007).
**Testing**: pytest + pytest-asyncio (existing) — one new unit-test file for the aggregate. No frontend Vitest in scope; manual smoke via `quickstart.md`.
**Target Platform**: docker-compose self-hosted stack (api + worker + frontend + postgres + redis + optional ollama).
**Project Type**: web application (FastAPI backend + Vue SPA).
**Performance Goals**: aggregate query cost O(N chunks) but executed once per `GET /api/repos` call against a btree index on `code_chunks.repo_id` — negligible at thesis scale (≤ 5 000 chunks per repo per ADR-007 cap). Single SQL `GROUP BY` for all repos in one shot, not N+1.
**Constraints**: zero DB schema change, zero new env var, zero new compose service. Backward-compat: `embedding_token_count` is optional on the frontend type so pre-feature responses without it default to 0 (defensive).
**Scale/Scope**: thesis-demo workload — ≤ 1 active index, ≤ 50 repos.

## Constitution Check

| Principle | Verdict | Note |
|-----------|---------|------|
| **I. Spec-Driven** | ✓ pass | spec.md authored and checklist 16/16 PASS before this plan. tasks.md follows. |
| **II. ADR-Driven** | ✓ pass | NO hard trigger. Pure UI/UX + docs + read-time SQL aggregate. No DB schema change, no engine/queue/framework/provider/topology/transport change. No ADR required. |
| **III. Pluggable AI Providers** | ✓ pass | No LLM/embedding adapter touched. |
| **IV. Privacy & Credentials** | ✓ pass | No new credential surface. No new persisted field. Aggregate sums non-secret integers. |
| **V. Single-Command Deploy** | ✓ pass | No new docker-compose service, no new env var, no host-side step. README quick-start unchanged in spirit. |
| **Async-by-default** | ✓ pass | New `get_embedding_token_counts` is `async def`; uses existing async sessionmaker. |

**Phase 0 gate**: PASS.

## Project Structure

### Documentation (this feature)

```text
specs/014-ux-polish-and-readme/
├── plan.md                              # This file
├── research.md                          # Phase 0 output
├── data-model.md                        # Phase 1 output
├── quickstart.md                        # Phase 1 output
├── contracts/
│   └── repos_response_token_count.md    # /api/repos response shape addition
├── checklists/
│   └── requirements.md                  # 16/16 PASS
└── tasks.md                             # Phase 2 output (/speckit-tasks)
```

### Source Code (repository root)

```text
backend/
├── src/codesensei/
│   └── indexing/
│       ├── store.py                     # MOD (+ get_embedding_token_counts aggregate)
│       └── service.py                   # MOD (list_repos enriches with aggregate)
└── tests/
    └── unit/
        └── test_indexing_aggregates.py  # NEW (sum/zero/empty cases)

frontend/
├── src/
│   ├── api/
│   │   └── repos.ts                     # MOD (+ embedding_token_count field)
│   ├── components/
│   │   └── RepoList.vue                 # MOD (+ Embedding tokens dl row + formatThousands)
│   └── pages/
│       ├── ReviewPage.vue               # MOD (drop tokenLine span + helpers + Recent chip strip)
│       └── HistoryDetailPage.vue        # MOD (rewrite formatTokenLine to total-only shape)

README.md                                # REWRITE (thesis-grade)
```

**Structure Decision**: Existing CodeSensei mono-repo. No new top-level directories. The aggregate helper lives in `indexing/store.py` (where the other CRUD aggregates live); the enrichment seam is `IndexingService.list_repos`, which already produces the response dict. Two surface seams keep the change contained.

## Complexity Tracking

No constitutional violations. No DB schema change. Single new SQL aggregate is a textbook `GROUP BY` against an existing index. Frontend deltas are surgical: two helpers added, three helpers/blocks removed.
