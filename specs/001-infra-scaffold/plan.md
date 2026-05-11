# Implementation Plan: Infrastructure Scaffold

**Branch**: `001-infra-scaffold` | **Date**: 2026-05-12 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/001-infra-scaffold/spec.md`

## Summary

Stand up the minimal `docker-compose`-orchestrated stack — `api` (FastAPI), `frontend` (Vue 3 + nginx), `postgres` (PostgreSQL 16 + pgvector), `redis` (queue broker) — so that `cp .env.example .env && docker compose up -d` reaches all-healthy state in ≤ 60 s on a clean Docker host. The backend exposes a `/healthz` endpoint that probes Postgres (including the `vector` extension) and Redis in parallel and returns a structured JSON envelope; the frontend renders three status badges driven by that endpoint. No business schema, no LLM/embedding adapters, no auth — pure infrastructural baseline that downstream feature specs build on.

## Technical Context

**Language/Version**: Python 3.12.x (backend); Node 22 LTS (frontend, build-stage only inside the Docker image — never on host)
**Primary Dependencies**:
- Backend: FastAPI ≥ 0.115, uvicorn[standard], SQLAlchemy 2.x async, asyncpg, alembic, redis (asyncio client), structlog, pydantic-settings. Lockfile via `uv`.
- Frontend: Vue 3.5+, Vite 6+, TypeScript 5.x. No router, no Pinia, no UI library at this stage.

**Storage**: PostgreSQL 16 + pgvector. Image `pgvector/pgvector:pg16`. Named volume `postgres_data`.
**Testing**: pytest + pytest-asyncio + httpx.AsyncClient. No frontend tests at this stage (Vite project ships an empty test slot for later).
**Target Platform**: Docker Engine 24+ on Linux/macOS/Windows hosts. No host-side runtime requirements.
**Project Type**: Web application (backend + frontend monorepo under `app/`).
**Performance Goals**: cold-start to all-healthy ≤ 60 s (SC-001); `/healthz` p95 latency ≤ 50 ms healthy; frontend first paint ≤ 1 s on localhost (SC-003).
**Constraints**: single `docker-compose up` (Constitution V); async-by-default for all I/O in FastAPI handlers (Constitution Tech-Stack §async); structured logs only — no `print()` in production paths (Constitution Workflow §3); host-port collisions resolvable via env vars without touching tracked files (SC-006).
**Scale/Scope**: single-developer self-hosted; ~150–300 LOC backend, ~50–150 LOC frontend at this scaffold stage. No multi-tenant, no auth.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| # | Principle | Status | Notes |
|---|---|---|---|
| I | Spec-Driven Development (NON-NEGOTIABLE) | ✅ PASS | `spec.md` ratified; this plan is the next mandated artefact. |
| II | ADR-Driven Architectural Decisions (NON-NEGOTIABLE) | ✅ PASS | Three implementation choices analysed below — none touches an ADR-mandated surface (DB engine / queue system / framework / AI provider / deploy shape / posting strategy). All three are implementation-level inside the already-ratified stack. No new ADRs required for this spec. |
| III | Pluggable AI Provider Boundaries | ✅ PASS (vacuous) | Scaffold introduces no LLM/embedding calls. Plan reserves directory shape `backend/src/codesensei/providers/` for the future `LLMProvider` / `EmbeddingProvider` adapters; nothing instantiated. |
| IV | Privacy & Credentials Discipline | ✅ PASS | `.env.example` ships placeholder-only values; `.env` already gitignored from bootstrap commit; healthcheck JSON never contains env values; no credentials reach the frontend. |
| V | Single-Command Deployment | ✅ PASS | Every component is a compose service; the only host-side step is `cp .env.example .env`; README documents the three-command smoke test. |

### ADR boundary analysis (the three implementation choices)

- **pgvector base image** — `pgvector/pgvector:pg16` (official upstream). Same database engine as ratified in ADR-004 (Postgres 16); choosing the official extension-bundled image is **implementation detail, NOT a database-engine change**. No ADR. Fallback documented in `research.md`: custom Dockerfile on `postgres:16-alpine` + manual extension install if the official image becomes unmaintained.
- **alembic migration style** — hand-written migrations under `backend/alembic/versions/`, one migration per logical schema change. `alembic revision --autogenerate` allowed as developer aid but never committed without human review. Workflow choice **within** the alembic stack ratified by ADR-005; no architectural surface touched. No ADR.
- **logging library** — `structlog`. Constitution Workflow §3 already mandates structured logs to stdout; choosing `structlog` over `loguru` is a library choice **within that mandate**, not a re-decision of the mandate. No ADR.

If Phase 1 design surfaces any item that does touch an ADR-mandated surface, planning HALTS and an ADR ships before continuing.

## Project Structure

### Documentation (this feature)

```text
specs/001-infra-scaffold/
├── plan.md                # this file (output of /speckit-plan)
├── spec.md                # already ratified
├── research.md            # Phase 0 output
├── data-model.md          # Phase 1 output
├── quickstart.md          # Phase 1 output
├── contracts/
│   └── healthz.md         # /healthz interface contract
├── tasks.md               # produced by /speckit-tasks (next phase)
└── checklists/
    └── requirements.md    # already produced by /speckit-specify
```

### Source Code (repository root = `app/`)

Selected: **Web application** layout (backend + frontend monorepo).

```text
app/
├── backend/
│   ├── pyproject.toml
│   ├── uv.lock
│   ├── Dockerfile
│   ├── alembic.ini
│   ├── alembic/
│   │   ├── env.py
│   │   └── versions/
│   │       └── 001_enable_pgvector.py     # only migration this spec ships
│   ├── src/
│   │   └── codesensei/
│   │       ├── __init__.py
│   │       ├── main.py                    # FastAPI app factory + uvicorn entry
│   │       ├── config.py                  # pydantic-settings env reader
│   │       ├── logging_config.py          # structlog setup
│   │       ├── db.py                      # async SQLAlchemy engine + session factory
│   │       ├── redis_client.py            # async redis client
│   │       ├── healthcheck.py             # /healthz route + parallel dependency probes
│   │       └── providers/                 # reserved (empty) for future adapter shapes
│   │           └── __init__.py
│   └── tests/
│       ├── conftest.py
│       ├── unit/
│       │   └── test_healthcheck_logic.py
│       └── integration/
│           └── test_healthz_endpoint.py
├── frontend/
│   ├── package.json
│   ├── pnpm-lock.yaml
│   ├── Dockerfile                         # multi-stage: node-builder → nginx-static
│   ├── nginx.conf                         # serves /, proxies /api/* to api:8000
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── index.html
│   └── src/
│       ├── main.ts
│       └── App.vue                        # calls /api/healthz, renders 3 status badges
├── docker-compose.yml
├── .env.example
├── .gitignore                             # already in repo; verify .env, backend/.venv excluded
├── README.md                              # updated with smoke-test
└── specs/                                 # already exists
```

**Structure Decision**: monorepo under `app/` with separate `backend/` and `frontend/` subtrees. Compose services build from `./backend` and `./frontend` respectively. Tests live alongside each subtree. The `app/` root is the docker-compose context.

## Phase 0 — Research

Output: [`research.md`](./research.md). Resolves eight implementation-level questions (pgvector image, dep managers, alembic async wiring, structlog config, healthcheck probe shape, frontend↔backend routing, Docker healthcheck commands). No `NEEDS CLARIFICATION` markers remain.

## Phase 1 — Design

Outputs:
- [`data-model.md`](./data-model.md) — empty business schema for this spec (only the pgvector extension migration).
- [`contracts/healthz.md`](./contracts/healthz.md) — `/healthz` interface contract.
- [`quickstart.md`](./quickstart.md) — operator-facing smoke-test guide.
- `CLAUDE.md` — updated agent-context pointer between `<!-- SPECKIT START -->` markers.

## Post-Design Constitution Re-check

Re-evaluated against Constitution v1.0.1 after Phase 1 deliverables:

| # | Principle | Post-design status | Note |
|---|---|---|---|
| I | Spec-Driven | ✅ PASS | All four planning artefacts present before any code is written. |
| II | ADR-Driven | ✅ PASS | No design artefact introduced a new architectural surface; the three boundary items resolved earlier remain implementation-level. |
| III | Pluggable AI | ✅ PASS (vacuous) | `backend/src/codesensei/providers/` directory reserved empty. |
| IV | Privacy | ✅ PASS | `.env.example` template in `quickstart.md` lists placeholder-only values; nothing in the design serialises env values into responses. |
| V | Single-Command Deploy | ✅ PASS | All four design files reference `docker-compose` as the sole orchestrator; no host-side steps introduced. |

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| Two language ecosystems (Python + Node) in the same repo | Mandated by ADR-002 (Vue frontend + FastAPI backend); not a choice this plan makes. | A single-language stack would violate ratified architecture. |
| Monorepo with two Dockerfiles instead of one | Backend and frontend have radically different build toolchains; combining them would either bloat the api image with Node or fight against Vite's static-output model. | A single Dockerfile would either need a multi-language base image (heavy) or skip the frontend (violates US3). |

No other complexity beyond what the ratified stack already implies.
