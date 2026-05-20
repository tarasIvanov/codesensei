# Implementation Plan: Token usage + cost estimate per review

**Branch**: `012-tokens-cost` | **Date**: 2026-05-21 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/012-tokens-cost-estimate/spec.md`

## Summary

Every successful `POST /api/review` now reports `prompt_tokens`, `completion_tokens`, and `cost_usd`. The same triple is persisted alongside each review run (via three nullable columns on `review_runs`) so `GET /api/reviews/{id}` replays it without any LLM round-trip. The cost is derived from a code-internal `(provider, model) → (in_price, out_price)` table keyed in USD per 1M tokens. Provider adapters surface usage via a per-instance `_last_usage: ChatUsage | None` attribute that the service layer reads via duck-typing, keeping the public `LLMProvider` Protocol surface unchanged. The frontend renders one extra muted line under the existing `provider · elapsed_ms` line on both `/review` and `/history/<id>` via a shared `formatTokenLine()` helper.

## Technical Context

**Language/Version**: Python 3.12 (backend), TypeScript 5.7 + Vue 3.5 (frontend)
**Primary Dependencies**: FastAPI, SQLAlchemy 2.x async, asyncpg, alembic, openai SDK ≥ 1.50, anthropic SDK ≥ 0.40, httpx (Ollama), pydantic 2; vue-router 4, Vite 6, Tailwind v4 in-tree primitives
**Storage**: PostgreSQL 16 with pgvector (existing). Adds 3 nullable columns to `review_runs`: `prompt_tokens INTEGER NULL`, `completion_tokens INTEGER NULL`, `cost_usd NUMERIC(10, 6) NULL`.
**Testing**: pytest + pytest-asyncio (existing), respx for HTTP mocks. No frontend Vitest in scope; manual smoke via quickstart.md.
**Target Platform**: docker-compose-deployed self-hosted stack (api + worker + frontend + postgres + redis + optional ollama).
**Project Type**: web application (FastAPI backend + Vue SPA).
**Performance Goals**: zero added LLM round-trips (cost is computed from the already-present usage payload); the new fields cost O(1) per review.
**Constraints**: must keep the `LLMProvider` Protocol surface unchanged (Principle III — adapter contract is the boundary); persist failure path stays best-effort (matches feature 009).
**Scale/Scope**: thesis-demo workload — ≤ 1 000 persisted runs (existing LRU cap), ≤ 50 reviews/day.

## Constitution Check

| Principle | Verdict | Note |
|-----------|---------|------|
| **I. Spec-Driven** | ✓ pass | spec.md authored and validated before this plan. tasks.md will follow before any production code. |
| **II. ADR-Driven** | ⚠️ HARD TRIGGER | Adding 3 columns to `review_runs` IS a DB schema change. **ADR-015 REQUIRED** in `_decision_log.md` BEFORE any production code. ADR-015 shape is fully described in `research.md` → §Decision: ADR-015 contents. tasks.md MUST place ADR-015 drafting as an early task (Phase 1 Setup), NOT polish. |
| **III. Pluggable AI Providers** | ✓ pass | Adapter contract (`LLMProvider.chat() -> str`) is unchanged. The new `_last_usage` attribute is implementation detail of concrete adapters, read by the service layer via `getattr(provider, "_last_usage", None)`. Tests that mock `chat()` continue to pass without modification. |
| **IV. Privacy & Credentials** | ✓ pass | Tokens and cost are not secrets. Pricing constants live in source control. No new credential is introduced. The cost field is explicitly labelled an estimate (FR-012) and computed locally from observed usage; no external pricing service is called. |
| **V. Single-Command Deploy** | ✓ pass | No new docker-compose service, no new env var. Alembic auto-applies the migration on container startup. |
| **Async-by-default** | ✓ pass | The new code path is async-clean: no new I/O is introduced (usage is read from the SDK response already in scope; cost computation is pure). Provider adapters remain `async def chat(...) -> str`. |

**Phase 0 gate**: PASS (ADR-015 is required but deferred to tasks.md as the gating early task — per the Constitution this is the canonical pattern, matching ADR-013 in feature 009).

## Project Structure

### Documentation (this feature)

```text
specs/012-tokens-cost-estimate/
├── plan.md                                    # This file (/speckit-plan output)
├── research.md                                # Phase 0 output
├── data-model.md                              # Phase 1 output
├── quickstart.md                              # Phase 1 output
├── contracts/
│   ├── review_result.md                       # ReviewResult wire-shape addition
│   ├── reviews_history_endpoints.md           # /api/reviews/{id} wire-shape addition
│   └── pricing_module.md                      # backend/src/codesensei/review/pricing.py contract
├── checklists/
│   └── requirements.md                        # Spec quality checklist (already complete)
└── tasks.md                                   # Phase 2 output (/speckit-tasks)
```

### Source Code (repository root)

```text
backend/
├── src/codesensei/
│   ├── providers/
│   │   ├── base.py                            # MOD: + ChatUsage dataclass
│   │   ├── openai_adapter.py                  # MOD: populate _last_usage
│   │   ├── anthropic_adapter.py               # MOD: populate _last_usage
│   │   └── ollama_adapter.py                  # MOD: populate _last_usage (best-effort)
│   ├── review/
│   │   ├── schema.py                          # MOD: + 3 optional fields on ReviewResult
│   │   ├── pricing.py                         # NEW
│   │   └── service.py                         # MOD: read usage, compute cost, plumb into ReviewResult + _persist_run
│   └── reviews_history/
│       ├── models.py                          # MOD: + 3 ORM columns
│       ├── schema.py                          # MOD: + 3 fields on ReviewRunSummary + ReviewRunDetail
│       └── store.py                           # MOD: insert_run kwargs + _row_to_* emitters
├── alembic/versions/
│   └── 005_review_run_tokens.py               # NEW (down_revision=004_review_history)
└── tests/
    ├── unit/
    │   ├── test_review_pricing.py             # NEW
    │   └── test_provider_usage.py             # NEW
    └── integration/
        └── test_reviews_history_endpoint.py   # MOD: round-trip the 3 new fields

frontend/
├── src/
│   ├── api/
│   │   ├── review.ts                          # MOD: + 3 fields on ReviewResult type
│   │   └── reviews.ts                         # MOD: + 3 fields on ReviewRunDetail + ReviewRunSummary
│   └── pages/
│       ├── ReviewPage.vue                     # MOD: render token line under provider · ms
│       └── HistoryDetailPage.vue              # MOD: render same token line from persisted data
```

**Structure Decision**: Backend + frontend mono-repo (existing CodeSensei layout). No new top-level directories. The `pricing.py` module lives inside `review/` because it is review-scoped data; if a future feature needs cost outside `/review` (unlikely for thesis scope), it can be lifted to `codesensei/pricing.py`.

## Complexity Tracking

No constitutional violations require justification. The plan adds three nullable columns and one helper module — both well-trodden patterns in the codebase (compare feature 009's `review_runs` introduction with two tables + one index).
