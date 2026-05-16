# Implementation Plan: PR Review MVP (diff-only, no retrieval)

**Branch**: `003-pr-review-mvp` | **Date**: 2026-05-17 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/003-pr-review-mvp/spec.md`

## Summary

End-to-end review pipeline that takes either a pasted unified diff or a GitHub PR URL, dispatches the diff to the configured `LLMProvider` (feature 002), parses a strictly-typed findings list out of the response, and renders it on a new `/review` page in the SPA. Synchronous request/response; no persistence; no retrieval/RAG. Hardens against oversized input (413) and malformed LLM output (502). Reuses the `LLMProvider` abstraction from feature 002 — this feature adds **zero** direct vendor SDK imports.

## Technical Context

**Language/Version**: Python 3.12+ (backend), TypeScript 5.7 + Vue 3.5 + Vite 6 (frontend)
**Primary Dependencies (backend)**: FastAPI ≥0.115, `pydantic` (BaseModel for request/response validation; comes with pydantic-settings), `httpx>=0.27` (GitHub diff fetch — already in stack), `structlog>=24.4` (logging — already in stack). Reuses `codesensei.providers.get_llm_provider()` from feature 002.
**Primary Dependencies (frontend)**: `vue-router@4` (NEW — single small dep, Vue ecosystem default for SPA routing; no new ADR per constitution §Stack which mandates Vue 3 + Vite but treats routing as accessory).
**Storage**: N/A — `FR-018` forbids any persistence in this feature. No new DB tables, no migrations, no Redis writes.
**Testing**: pytest + pytest-asyncio + `respx` (already a dev dep) for mocking GitHub HTTP; `AsyncMock` of `LLMProvider.chat` for review-pipeline unit tests; FastAPI `TestClient` for endpoint integration tests.
**Target Platform**: Linux container (already wired in docker-compose `api` service). No new compose services.
**Project Type**: Web service (`backend/` FastAPI + `frontend/` Vue SPA) — same layout as features 001/002.
**Performance Goals**: SC-001 — paste-to-rendered-findings ≤ 30 s for a typical (≤ 200-line) PR diff against a remote LLM provider. SC-004 — oversized rejection ≤ 1 s with no LLM call.
**Constraints**: synchronous endpoint (no `arq` queue this feature); server-side LLM call bounded by a chat-timeout shorter than the SPA's `fetch` default; max diff size enforced server-side; FR-018 zero-persistence; FR-019 no diff/finding bodies in logs.
**Scale/Scope**: Single-user, single-tenant local deployment. No concurrency limits beyond "UI disables Submit while in-flight" (US3-AS, edge case "double-click"). Anticipated request volume: a handful per minute peak (one developer reviewing PRs interactively).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Justification |
|-----------|:-----:|---------------|
| **I. Spec-Driven Development** | ✅ | This very plan exists; `spec.md` + `tasks.md` + `checklists/requirements.md` are present or imminent. No production code lands before `/speckit-tasks` approves a task list. |
| **II. ADR-Driven Architectural Decisions** | ✅ | No new database/queue/framework/provider/deploy decisions are introduced. Adding `vue-router` is a Vue-ecosystem accessory (constitution §Stack mandates Vue 3 + Vite; routing is an idiomatic accessory, not a "new infrastructural component"). LLM-output JSON-mode strategy is documented in `research.md` (R1) but is encapsulated **inside** existing adapters from ADR-003 — no contract change. GitHub-diff fetch uses `httpx` (already a stack dep), no new service. |
| **III. Pluggable AI Provider Boundaries** | ✅ | The review service imports **only** `codesensei.providers.get_llm_provider`. Zero direct imports of `openai` / `anthropic` / `ollama` in feature code. Model/temperature/timeout knobs go through the `LLMProvider.chat(...)` signature established in 002. Provider-specific JSON-mode wiring lives **inside** each adapter, not in the review service. |
| **IV. Privacy & Credentials Discipline** | ✅ | FR-018 forbids persistence of diff/PR URL/findings. FR-019 forbids logging diff/finding bodies — only metadata (request id, provider, payload bytes, finding count, error category). FR-011 forbids logging or surfacing the configured `GITHUB_TOKEN`. No new credential storage; reuses env-var pattern from feature 001. |
| **V. Single-Command Deployment** | ✅ | No new compose services. One new optional env var (`GITHUB_TOKEN`) added to `.env.example`; absence is allowed (only blocks Story 2's PR-URL mode, not the paste-diff mode). |

**Verdict**: PASS, no Complexity-Tracking entries needed.

## Project Structure

### Documentation (this feature)

```text
specs/003-pr-review-mvp/
├── plan.md              # This file
├── spec.md              # Already written (/speckit-specify)
├── research.md          # Phase 0 — written below
├── data-model.md        # Phase 1 — written below
├── quickstart.md        # Phase 1 — written below
├── contracts/
│   ├── api_review.md
│   ├── llm_prompt.md
│   └── github_diff_fetch.md
├── checklists/
│   └── requirements.md  # Already written
└── tasks.md             # Phase 2 (/speckit-tasks — separate command)
```

### Source Code (repository root)

```text
backend/
├── src/codesensei/
│   ├── review/                       # NEW package for this feature
│   │   ├── __init__.py
│   │   ├── schema.py                 # pydantic models: ReviewRequest / Finding / ReviewResult / ReviewError
│   │   ├── prompt.py                 # system+user prompt templates, JSON contract spelled out
│   │   ├── parser.py                 # strict parse of LLM output → list[Finding] (raises on malformed)
│   │   ├── service.py                # ReviewService: orchestrates provider call + parse, applies size limit
│   │   ├── github_diff.py            # httpx fetcher: PR URL → unified diff, auth/404 error mapping
│   │   └── errors.py                 # ReviewErrorCategory enum + HTTP-code mapping
│   ├── main.py                       # add POST /api/review router (existing app stays)
│   ├── config.py                     # add settings: REVIEW_MAX_DIFF_BYTES, REVIEW_LLM_TIMEOUT_S, GITHUB_TOKEN
│   └── providers/                    # UNCHANGED — feature 002 surface
└── tests/
    ├── unit/
    │   ├── test_review_schema.py     # pydantic round-trip + rejection of unknown severity
    │   ├── test_review_parser.py     # malformed JSON / wrong shape / bad severity → ReviewError(provider_malformed_output)
    │   ├── test_review_prompt.py     # prompt template snapshot — guards against accidental edits
    │   ├── test_review_service.py    # service with AsyncMock LLMProvider — happy + empty findings + provider error
    │   └── test_github_diff.py       # respx mocks for 200 / 401 / 404 / 5xx / malformed URL
    └── integration/
        └── test_review_endpoint.py   # POST /api/review — diff path + url path + 413 + 502 categories

frontend/
├── src/
│   ├── App.vue                       # mount <router-view/>; existing health badges move to HealthPage
│   ├── router.ts                     # NEW: vue-router with /  → HealthPage, /review → ReviewPage
│   ├── pages/
│   │   ├── HealthPage.vue            # carved out of current App.vue; UI unchanged
│   │   └── ReviewPage.vue            # NEW: textarea (diff) + input (PR URL) + Submit + findings list
│   ├── components/
│   │   ├── FindingsList.vue          # grouped-by-file rendering, severity badge, optional suggestion code block
│   │   └── SeverityBadge.vue         # blocker/major/minor/nit colour mapping
│   └── api/
│       └── review.ts                 # typed wrapper around POST /api/review + error-category → human-message map
└── tests/                            # none yet; smoke verified manually in browser per constitution §test-first scope
```

**Structure Decision**: Web-service layout already established in 001/002 — `backend/src/codesensei/` + `frontend/src/`. This feature adds **one new backend package** (`review/`) and **one new frontend page** (`/review`) plus minimal router infra. No top-level reshuffling.

## Phase 0 — Outline & Research

Unknowns extracted from Technical Context: see `research.md` (R1–R10), covering JSON-mode strategy per provider, diff-size budget, GitHub-diff fetch headers, vue-router decision, prompt template, timeout topology, validation library choice, error-category → HTTP mapping, retry policy on malformed output, and severity colour scheme.

## Phase 1 — Design & Contracts

Outputs:
- `data-model.md` — pydantic models, error enum, HTTP mapping table.
- `contracts/api_review.md` — `POST /api/review` request/response/error contract.
- `contracts/llm_prompt.md` — fixed prompt template + JSON output contract sent to the LLM.
- `contracts/github_diff_fetch.md` — GitHub REST diff-fetch contract (URL pattern, headers, response shape).
- `quickstart.md` — three demo flows: paste diff, paste PR URL, exceed size limit.

`CLAUDE.md` `<!-- SPECKIT START -->…<!-- SPECKIT END -->` block updated to point at this plan.

## Complexity Tracking

No constitutional violations to justify. Section intentionally empty.
