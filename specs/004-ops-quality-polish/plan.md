# Implementation Plan: Ops & Quality Polish (queue, settings UI, prompt tune)

**Branch**: `004-ops-quality-polish` | **Date**: 2026-05-17 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/004-ops-quality-polish/spec.md`

## Summary

Three orthogonal concerns bundled into one delivery cycle, sharing no business logic but together hardening the product surface before RAG work begins in 005:

1. **arq + worker container** — new `worker` compose service running an arq worker process; a single `ping_job` proves the queue is alive; `POST /api/jobs/ping` enqueues, `GET /api/jobs/{id}` polls; a new `worker` badge on `/healthz` reports liveness without flipping overall status.
2. **Settings UI** — new `/settings` SPA page; `POST /api/settings` persists provider/model/key choices in a new `app_settings` table; API keys are encrypted at rest with Fernet keyed by `MASTER_KEY`; `GET /api/settings` redacts secrets to their last four characters; the provider factory consults persisted settings before falling back to env vars.
3. **Prompt tune** — `review/prompt.py` system message gains a "blocker tier" rule (hardcoded secrets, SQL injection, eval/exec, RCE), a line-number anchor instruction, and one few-shot example; the snapshot test in `tests/unit/test_review_prompt.py` is updated.

Two new ADRs are required before implementation (per Constitution §II): **ADR-007** confirming `arq` as the async queue (closes the TBD in ADR-005), and **ADR-008** for the encrypted-settings storage strategy.

## Technical Context

**Language/Version**: Python 3.12+ backend, TypeScript 5.x + Vue 3.5 + Vite 6 frontend (unchanged from 001/002/003).
**Primary Dependencies (new)**:
- `arq>=0.26` — async Redis-backed task queue (declared in Constitution §Stack since v1.0.0; this feature actually adds it).
- `cryptography>=44` — provides `Fernet` for symmetric encryption-at-rest of stored credentials.
**Primary Dependencies (existing)**: FastAPI ≥0.115, `sqlalchemy[asyncio]>=2.0`, `asyncpg>=0.30`, `alembic>=1.14`, `redis>=5.2`, `structlog>=24.4`, `pydantic-settings>=2.6`. Frontend reuses `vue-router` from 003.
**Storage**:
- **New table** `app_settings (key text PK, value text, is_secret bool, updated_at timestamptz)` via a new alembic revision `002_app_settings`.
- **Redis** carries arq's queue + job-result keys (auto-TTL — no new persistent state for jobs).
**Testing**: pytest + pytest-asyncio (existing) + `arq.testing` helpers for in-process worker simulation. No new dev deps.
**Target Platform**: Linux containers (existing compose stack), plus one new `worker` service reusing `codesensei-api:dev` image.
**Project Type**: Web service (backend + SPA) — same layout as 001/002/003.
**Performance Goals**:
- SC-001 — ping job round-trip ≤ 5 s.
- SC-002 — worker liveness signal flips within 5 s of container stop.
- SC-006 — re-running demo PR yields line numbers within ±1 of file lines.
**Constraints**:
- New `worker` service uses the **same** `redis` container that's already in compose; no new infra.
- `MASTER_KEY` must be present before any credential write succeeds (FR-014).
- `POST /api/review` stays synchronous — queue is **not** in its path this feature.
**Scale/Scope**: Single-tenant, single-user. One concurrent worker process; arq's default in-process pool. No high-availability story.

## Constitution Check

*GATE: Must pass before Phase 0. Re-checked after Phase 1.*

| Principle | Status | Justification |
|-----------|:-----:|---------------|
| **I. Spec-Driven Development** | ✅ | Spec, plan, tasks, checklists all live under `specs/004-ops-quality-polish/`. No production code until tasks approved. |
| **II. ADR-Driven Architectural Decisions** | ⚠️ → ✅ on landing | Two new ADRs land **before** implementation: (a) **ADR-007: Async task queue = arq + Redis** confirms the TBD in ADR-005's "Open decisions" footnote; (b) **ADR-008: App settings persisted in `app_settings` table, credentials encrypted at rest with Fernet + env-supplied `MASTER_KEY`**. Both files added in Phase 0 alongside `research.md`. |
| **III. Pluggable AI Provider Boundaries** | ✅ | Settings UI writes/reads through the existing `LLMProvider` / `EmbeddingProvider` factory contract from 002. The factory's `lru_cache` gets a new layer that consults `app_settings` before falling back to env vars. **No new direct imports** of `openai` / `anthropic` / `ollama` anywhere outside their adapters. The Settings form is config, not code: changing the active provider is a single `POST /api/settings`, never a code change. |
| **IV. Privacy & Credentials Discipline** | ✅ | Constitution-exact match: "API keys ... MUST be stored either encrypted-at-rest in the database or in environment variables" — Fernet-encrypted column. FR-011 forbids returning full secrets from any endpoint; FR-022 forbids logging them. Master key is env-only, never serialised. |
| **V. Single-Command Deployment** | ✅ | One new compose service (`worker`), built from the same Dockerfile as `api`, command-overridden. One new env-var (`MASTER_KEY`) added to `.env.example` with empty default; absence is allowed but blocks credential **writes** (reads of non-secret settings still work). No host-side install required. |

**Verdict**: PASS with the binding requirement that ADR-007 and ADR-008 land in this feature's PR alongside `research.md`. No Complexity-Tracking entries required (encrypted-settings persistence is the constitution's prescribed pattern, not a deviation).

## Project Structure

### Documentation (this feature)

```text
specs/004-ops-quality-polish/
├── plan.md                  # This file
├── spec.md                  # Already written
├── research.md              # Phase 0 — written below (R1–R10)
├── data-model.md            # Phase 1
├── quickstart.md            # Phase 1
├── contracts/
│   ├── api_jobs.md          # POST /api/jobs/ping + GET /api/jobs/{id}
│   ├── api_settings.md      # GET/POST /api/settings (redacted reads + secret writes)
│   ├── healthz_worker.md    # New `worker` field in the healthz envelope
│   └── llm_prompt_v2.md     # Frozen SYSTEM template after tuning (delta from 003's contract)
├── checklists/
│   └── requirements.md      # Already written, 16/16 PASS
└── tasks.md                 # Phase 2 (/speckit-tasks)
```

### Source Code (repository root)

```text
backend/
├── src/codesensei/
│   ├── tasks/                              # NEW — arq worker + jobs
│   │   ├── __init__.py
│   │   ├── worker.py                       # arq WorkerSettings entrypoint
│   │   ├── ping.py                         # ping_job(ctx) → ISO timestamp
│   │   ├── enqueue.py                      # async client used by FastAPI
│   │   └── api.py                          # POST /api/jobs/ping + GET /api/jobs/{id}
│   ├── settings_store/                     # NEW — db-backed settings + Fernet
│   │   ├── __init__.py
│   │   ├── crypto.py                       # Fernet wrap + MASTER_KEY load
│   │   ├── models.py                       # AppSetting SQLAlchemy model
│   │   ├── store.py                        # async get/set/delete/all (redacted vs raw)
│   │   └── api.py                          # GET /api/settings + POST /api/settings
│   ├── providers/factory.py                # PATCH — consult settings_store before env
│   ├── healthcheck.py                      # PATCH — add probe_worker(); envelope adds `worker`
│   ├── review/prompt.py                    # PATCH — new SYSTEM with blocker rule + few-shot
│   ├── main.py                             # PATCH — include tasks/api + settings_store/api routers
│   └── config.py                           # PATCH — settings field MASTER_KEY (default "")
├── alembic/versions/
│   └── 002_app_settings.py                 # NEW migration (1 table)
└── tests/
    ├── unit/
    │   ├── test_settings_crypto.py         # Fernet round-trip + bad-key behaviour
    │   ├── test_settings_store.py          # async CRUD with redaction
    │   ├── test_tasks_ping.py              # ping_job pure-function test
    │   └── test_review_prompt.py           # UPDATE — new SYSTEM snapshot + few-shot pin
    └── integration/
        ├── test_jobs_endpoint.py           # enqueue + poll + 404 unknown id
        ├── test_settings_endpoint.py       # GET (redacted) + POST (encrypted) + invalid provider rejected
        └── test_healthz_worker.py          # worker badge ok/down; never gates overall

frontend/
├── src/
│   ├── pages/
│   │   ├── HealthPage.vue                  # PATCH — render new `worker` badge
│   │   └── SettingsPage.vue                # NEW — form + Save
│   ├── api/settings.ts                     # NEW — typed wrapper
│   ├── router.ts                           # PATCH — add /settings route
│   └── App.vue                             # PATCH — Settings link in topnav

docker-compose.yml                           # PATCH — add `worker` service (same image as api)
.env.example                                 # PATCH — add MASTER_KEY=
../_decision_log.md                          # PATCH — append ADR-007 + ADR-008
```

**Structure Decision**: Same web-app layout. Three small new packages under `backend/src/codesensei/` keep concerns isolated (`tasks/`, `settings_store/`, plus the existing `review/` getting a small patch). Frontend adds one page + one API wrapper. One new alembic migration. One new compose service. **No top-level reshuffling.**

## Phase 0 — Outline & Research

See [research.md](./research.md). Resolves R1–R10:

- R1 arq version & worker invocation pattern
- R2 ADR-007 confirms arq+Redis (closes ADR-005 TBD)
- R3 Fernet vs alternatives (NaCl/age/libsodium) for credentials-at-rest
- R4 `MASTER_KEY` format, generation, missing-key behaviour
- R5 Whitelisted `app_settings` keys (no free-form blob storage)
- R6 Factory-cache invalidation strategy after `POST /api/settings`
- R7 Worker liveness probe — `arq.health` Redis key pattern
- R8 Job-result TTL default (1 hour)
- R9 ADR-008 documents the persistence + encryption choice
- R10 Prompt-tune delta strategy and snapshot-test update plan

## Phase 1 — Design & Contracts

Outputs:
- `data-model.md` — `AppSetting`, `PingJob`/`JobResult`, `WorkerProbeResult`, settings keys whitelist, redaction policy.
- `contracts/api_jobs.md` — POST/GET wire shapes + error categories.
- `contracts/api_settings.md` — request/response, redaction examples, validation rejection echoes (e.g. `EMBEDDING_PROVIDER=anthropic` → re-uses 002's exact message).
- `contracts/healthz_worker.md` — new `worker` field in the existing healthz envelope; does not affect `failing[]` or overall `status`.
- `contracts/llm_prompt_v2.md` — frozen new SYSTEM string + the single few-shot example block; supersedes 003's `llm_prompt.md` for the SYSTEM section only (USER template + parser contract unchanged).
- `quickstart.md` — 4 scenarios: ping-job round-trip, settings save & immediate provider switch, demo PR re-run with calibrated severities, worker-down badge demo.

`CLAUDE.md` `<!-- SPECKIT START -->…<!-- SPECKIT END -->` block updated to point at 004's plan.

## Complexity Tracking

No constitutional violations to justify. Two new ADRs document additive choices, not deviations.
