---

description: "Task list for 001-infra-scaffold"
---

# Tasks: Infrastructure Scaffold

**Input**: Design documents from `/specs/001-infra-scaffold/`
**Prerequisites**: plan.md (✅), spec.md (✅), research.md (✅), data-model.md (✅), contracts/healthz.md (✅), quickstart.md (✅)

**Tests**: Selectively included. US2 `/healthz` gets unit + integration tests ordered before implementation. US1 (cold-start timing) and US3 (frontend) ship without tests in this spec — manual smoke test covers SC-001; no Vue test framework introduced yet.

**Organisation**: Tasks grouped by phase. Phases 1–2 are shared; Phase 3 implements US2 first (US1's success criterion needs the healthcheck to exist before it can be verified); Phase 4 polishes the compose orchestration that satisfies US1; Phase 5 ships US3; Phase 6 is polish.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: parallelisable (different files, no dependency on uncompleted prior task in the same phase)
- **[Story]**: US1 / US2 / US3 (omitted in Setup, Foundational, and Polish)
- Every task description includes exact file paths.

## Path Conventions

Monorepo under `app/`, structure per `plan.md`:
- Backend: `backend/src/codesensei/`, `backend/tests/`, `backend/alembic/`
- Frontend: `frontend/src/`, `frontend/`
- Compose / env: repo root (`app/`)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Repo-level scaffolding — files that aren't tied to a single story.

- [ ] T001 Create top-level directory layout: `backend/`, `backend/src/codesensei/`, `backend/src/codesensei/providers/`, `backend/tests/`, `backend/tests/unit/`, `backend/tests/integration/`, `backend/alembic/`, `backend/alembic/versions/`, `frontend/`, `frontend/src/`. Add `.gitkeep` only in `backend/src/codesensei/providers/` (intentionally empty per Constitution Principle III reservation).
- [ ] T002 [P] Write the initial `.env.example` shell at repo root listing every variable referenced by `docker-compose.yml` and the api: `LLM_PROVIDER`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `EMBEDDING_PROVIDER`, `DATABASE_URL`, `REDIS_URL`, `LOG_LEVEL`, `API_HOST_PORT`, `FRONTEND_HOST_PORT`, `POSTGRES_HOST_PORT`, `REDIS_HOST_PORT`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`. All values placeholder-only; no real credentials.
- [ ] T003 [P] Verify `.gitignore` at repo root excludes `.env`, `backend/.venv/`, `backend/__pycache__/`, `backend/.pytest_cache/`, `frontend/node_modules/`, `frontend/dist/`, `frontend/.vite/`. Add any missing lines.
- [ ] T004 Create the docker-compose skeleton at `docker-compose.yml` with the four services (`api`, `frontend`, `postgres`, `redis`) declared but with build contexts and healthchecks left as TODO placeholders (filled in Phase 3/4/5). Network: implicit default bridge. Named volume: `postgres_data`. Ollama service NOT yet added.

**Estimated effort**: 4 tasks · S (each ≤ 30 min).

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Backend and frontend skeletons that downstream story phases assume exist. Each must reach a "container builds and starts" state.

**⚠️ CRITICAL**: No user-story work begins until this phase is complete.

- [ ] T005 Create `backend/pyproject.toml` declaring the backend package `codesensei` (Python ≥ 3.12), pinning runtime deps (FastAPI ≥ 0.115, uvicorn[standard], SQLAlchemy 2.x, asyncpg, alembic, redis, structlog, pydantic-settings) and dev deps (pytest, pytest-asyncio, httpx, ruff). Project layout: `src/` (PEP 621 + setuptools or `uv` defaults).
- [ ] T006 Run `uv lock` from `backend/` to produce `backend/uv.lock`. Commit the lockfile.
- [ ] T007 [P] Write `backend/src/codesensei/__init__.py` (empty) and `backend/src/codesensei/main.py` containing a minimal FastAPI app factory: `def create_app() -> FastAPI` returning an app with no routes yet. `if __name__ == "__main__": uvicorn.run(create_app(), host="0.0.0.0", port=8000)`.
- [ ] T008 Write `backend/Dockerfile` (multi-stage: `uv` builder → slim `python:3.12-slim` runtime). Runtime stage MUST install `curl` via `apt-get` (required by the compose healthcheck per `research.md` §8). Entrypoint: `alembic upgrade head && uvicorn codesensei.main:create_app --factory --host 0.0.0.0 --port 8000`.
- [ ] T009 [P] Bootstrap frontend with `pnpm create vite@latest frontend -- --template vue-ts` (run once locally, not from within a task — adapt the generated `frontend/package.json`, `frontend/vite.config.ts`, `frontend/tsconfig.json`, `frontend/index.html`, `frontend/src/main.ts`, `frontend/src/App.vue` to match the scaffold's needs). Trim the default scaffolding to bare minimum — remove HelloWorld component, default styles, public assets beyond favicon.
- [ ] T010 [P] Write `frontend/Dockerfile` (multi-stage: `node:22-alpine` builder running `pnpm install --frozen-lockfile && pnpm build` → `nginx:1.27-alpine` runtime copying `dist/` into `/usr/share/nginx/html/`).
- [ ] T011 Update `docker-compose.yml` (from T004) to point `api.build` at `./backend` and `frontend.build` at `./frontend`. Both containers should now build and start (even though `api` will fail healthcheck — handled in Phase 3).

**Estimated effort**: 7 tasks · S–M (T005 + T008 are M, others S). Total ≈ 2–3 h.

**Checkpoint**: `docker compose build api frontend` succeeds; `docker compose up postgres redis` reaches healthy.

---

## Phase 3: User Story 2 — Backend Healthcheck Endpoint (Priority: P2, execution-order P1) 🎯 MVP

**Goal**: `GET /healthz` returns the 200/503 envelope per `contracts/healthz.md`, driven by parallel async probes against Postgres (including the `vector` extension) and Redis.

**Independent Test**: `pytest backend/tests/` is green. With `docker compose up api postgres redis` running, `curl -fsS localhost:8000/healthz | jq` returns `{"status":"ok","db":"ok","redis":"ok","extensions":{"vector":"ok"}}`. After `docker compose stop redis`, the same call returns HTTP 503 with `failing: ["redis"]`.

### Tests for User Story 2 (recommended; written FIRST so they fail before implementation lands)

- [ ] T012 [P] [US2] Write `backend/tests/conftest.py` providing two pytest fixtures: (a) `async_client` — `httpx.AsyncClient` wrapping the FastAPI app via `ASGITransport`; (b) `mock_probes` — monkeypatched async db/redis probe functions whose return values are parametrised per test. Mark all tests `asyncio_mode = "auto"`.
- [ ] T013 [P] [US2] Write `backend/tests/unit/test_healthcheck_logic.py` covering the envelope builder in isolation: all-ok inputs → 200 + `status: ok`; db-down → 503 + `failing: ["db"]`; redis-down → 503 + `failing: ["redis"]`; vector-missing → 503 + `failing: ["vector"]` and `extensions.vector: "missing"`; combined db+redis down → both names in `failing`.
- [ ] T014 [US2] Write `backend/tests/integration/test_healthz_endpoint.py` exercising the real FastAPI app via `async_client`: assert response status, content-type, and JSON shape across the healthy and three failure cases (db, redis, vector). Use `mock_probes` to inject the failure conditions — no real DB/Redis required for this integration test (those are covered by the manual smoke test under SC-001).
- [ ] T015 [US2] Run `pytest backend/tests/ -v` and confirm every test FAILS (no implementation exists yet). Commit-boundary marker: at this point only the test files exist for `/healthz`, satisfying the test-first ordering before implementation begins.

### Implementation for User Story 2

- [ ] T016 [P] [US2] Implement `backend/src/codesensei/config.py`: pydantic-settings model `Settings(BaseSettings)` reading `DATABASE_URL`, `REDIS_URL`, `LOG_LEVEL`, `LLM_PROVIDER`, `EMBEDDING_PROVIDER` from env with safe defaults. `get_settings()` cached via `@lru_cache`.
- [ ] T017 [P] [US2] Implement `backend/src/codesensei/logging_config.py` per `research.md` §5: structlog with `merge_contextvars` → `add_log_level` → `TimeStamper(fmt="iso", utc=True)` → `JSONRenderer()`. `configure_logging(level: str)` entrypoint. Emit one structured log line `event="logging.configured"` with `level` field on call.
- [ ] T018 [US2] Implement `backend/src/codesensei/db.py`: async SQLAlchemy `AsyncEngine` constructed from `settings.DATABASE_URL`; `async_sessionmaker` factory; `async def probe_db(session)` running `SELECT 1` and `SELECT 1 FROM pg_extension WHERE extname='vector'`, returning a typed result `{"db": "ok"|"down", "vector": "ok"|"missing"|"unknown"}`. On call MUST emit `event="probe.db"` structlog line with the result and duration_ms.
- [ ] T019 [P] [US2] Implement `backend/src/codesensei/redis_client.py`: async redis client factory from `settings.REDIS_URL`; `async def probe_redis(client)` awaiting `client.ping()`, returning `"ok"` on `PONG` else `"down"`. Emits `event="probe.redis"` structlog line.
- [ ] T020 [US2] Implement `backend/src/codesensei/healthcheck.py`: APIRouter with `GET /healthz`; runs `asyncio.gather(probe_db(), probe_redis())` wrapped in `asyncio.wait_for(timeout=3.0)`; on timeout flags unfinished probes as `down`. Builds the JSON envelope per `contracts/healthz.md` (status, db, redis, extensions.vector, failing). Returns HTTP 200 when all `ok`, HTTP 503 otherwise. Emits one structlog line `event="healthz"` with `status`, `db`, `redis`, `extensions.vector`, `duration_ms`.
- [ ] T021 [US2] Wire the router into the FastAPI app: in `backend/src/codesensei/main.py` `create_app()` factory, call `configure_logging(settings.LOG_LEVEL)`, register the healthcheck router under prefix `/api`, and also register the same router (or a thin alias route) at top-level `/healthz` so both compose-internal probes and the frontend's `/api/healthz` path resolve. Emit one structlog line `event="app.startup"` with `provider_config` (no credential values) per FR-017.
- [ ] T022 [US2] Initialise alembic in `backend/`: `cd backend && alembic init alembic`. Edit `backend/alembic.ini` to read DB URL from env (`sqlalchemy.url = %(DATABASE_URL)s`). Replace generated `backend/alembic/env.py` with the async wiring from `research.md` §4.
- [ ] T023 [US2] Hand-write `backend/alembic/versions/001_enable_pgvector.py` per `data-model.md` migration ledger (revision id `001_enable_pgvector`, down-revision None, `op.execute("CREATE EXTENSION IF NOT EXISTS vector")` in upgrade, `op.execute("DROP EXTENSION IF EXISTS vector")` in downgrade). Do NOT use `alembic revision --autogenerate` per migration policy in `quickstart.md`.
- [ ] T024 [US2] Add compose-level healthcheck to the `api` service in `docker-compose.yml` per `research.md` §8: `test: ["CMD", "curl", "-fsS", "http://localhost:8000/healthz"]`, interval 5s, timeout 3s, retries 5, start_period 30s. Add `depends_on: postgres: {condition: service_healthy}, redis: {condition: service_healthy}`.
- [ ] T025 [US2] Add compose-level healthchecks to `postgres` (`pg_isready -U $$POSTGRES_USER -d $$POSTGRES_DB`, start_period 10s) and `redis` (`redis-cli ping | grep -q PONG`, start_period 5s) per `research.md` §8.
- [ ] T026 [US2] Run `pytest backend/tests/ -v` — all tests from T012–T014 must now pass. Then `docker compose up -d postgres redis api` and `curl -fsS localhost:8000/healthz | jq` returns the ok envelope. Stop redis: `docker compose stop redis` → `curl` returns 503 with `failing: ["redis"]`.

**Estimated effort**: 15 tasks. T012–T015 S (test scaffolding). T016–T021 M (implementation core). T022–T023 S (alembic). T024–T026 S (compose wiring + verify). Total ≈ 5–7 h. **Suggested commit boundary**: one commit at the end of this phase ("backend healthcheck + alembic + tests + compose wiring") — first meaningful PR-ready chunk.

**Checkpoint**: US2 is fully functional and independently testable. `docker compose ps` shows `api`, `postgres`, `redis` all healthy; `/healthz` returns the spec envelope.

---

## Phase 4: User Story 1 — Single-Command Developer Onboarding (Priority: P1, execution-order P2)

**Goal**: Make `cp .env.example .env && docker compose up -d` reach all-healthy state in ≤ 60 s on a clean host, with every service correctly orchestrated.

**Independent Test**: On a fresh checkout, `cp .env.example .env && docker compose up -d` → `docker compose ps` shows every service (api, frontend, postgres, redis) `running (healthy)` within 60 seconds. `docker compose down -v && docker compose up -d` reaches the same state on the second cold start (SC-004). Overriding any of the four `*_HOST_PORT` env vars in `.env` re-binds without editing tracked files (SC-006).

### Implementation for User Story 1

- [ ] T027 [US1] Complete `docker-compose.yml`: parameterise host ports for every public service via `${VAR_NAME:-default}` (`API_HOST_PORT:-8000`, `FRONTEND_HOST_PORT:-5173`, `POSTGRES_HOST_PORT:-5432`, `REDIS_HOST_PORT:-6379`). Image references: `pgvector/pgvector:pg16` for postgres, `redis:7-alpine` for redis. Mount `postgres_data` named volume on `/var/lib/postgresql/data`. Add restart policies (`restart: unless-stopped`) on all four services.
- [ ] T028 [US1] Add the `ollama` service to `docker-compose.yml` under `profiles: ["ollama"]` so it does NOT start by default (FR-003). Image `ollama/ollama:latest`, volume for model cache, healthcheck via `ollama list`.
- [ ] T029 [P] [US1] Finalise `.env.example`: every variable referenced in the now-complete `docker-compose.yml` is present, every value is a placeholder (no real keys), defaults match the compose `${VAR:-default}` defaults so an empty `.env` works. Add explanatory comments per section.
- [ ] T030 [US1] Update `README.md` at repo root: add a "Quick start" section duplicating the three-command smoke test from `quickstart.md`; add the host-port-override table; document the optional `--profile ollama` invocation. Keep the existing "pre-MVP" status banner.
- [ ] T031 [US1] Run the SC-001 smoke test manually: `docker compose down -v && docker compose up -d`, time the all-healthy state. Document the observed time in `specs/001-infra-scaffold/quickstart.md` under a new "Observed cold-start times" section if it deviates materially from the 60 s target.

**Estimated effort**: 5 tasks · S–M. T027 + T028 M (compose wiring), others S. Total ≈ 1.5–2.5 h. **Suggested commit boundary**: one commit ("docker-compose orchestration + .env.example + README smoke-test"). Could be folded into the Phase 3 commit if Phase 3 lands the compose-level healthchecks at the same time — judgment call at implement time.

**Checkpoint**: US1 and US2 both functional. The full backend stack (minus frontend) reaches all-healthy via single command.

---

## Phase 5: User Story 3 — Frontend Skeleton Calling the API (Priority: P3)

**Goal**: A minimal Vue 3 page served by nginx that calls `/api/healthz` on load and renders three status badges.

**Independent Test**: `curl -I http://localhost:5173` returns HTTP 200 with `Content-Type: text/html...`. Browser visit to `http://localhost:5173` shows three labelled status badges driven by `/api/healthz`. With `docker compose stop api`, the badges render as down with a brief explanatory message (no white-screen-of-death).

### Implementation for User Story 3

- [ ] T032 [P] [US3] Write `frontend/nginx.conf` per `research.md` §7: `server { listen 80; root /usr/share/nginx/html; location /api/ { proxy_pass http://api:8000/api/; ... } location / { try_files $uri $uri/ /index.html; } }`. Copied into the runtime stage of `frontend/Dockerfile` (T010) at `/etc/nginx/conf.d/default.conf`.
- [ ] T033 [P] [US3] Trim `frontend/src/main.ts` to the minimum: `createApp(App).mount('#app')`. Remove the default Vue scaffolding imports.
- [ ] T034 [US3] Rewrite `frontend/src/App.vue` to: (a) on `onMounted`, call `fetch('/api/healthz')`; (b) parse the response and render three labelled status badges (`status`, `db`, `redis`) with simple inline styling (green for `ok`, red for `down`/`missing`, grey for `unknown` or pre-fetch); (c) on fetch error or non-2xx response, render badges as `down` with the error message visible. No router, no state library, no UI library.
- [ ] T035 [US3] Add the frontend service's compose-level healthcheck to `docker-compose.yml` per `research.md` §8 (`wget -qO- http://localhost/ >/dev/null`, start_period 5s). Add `depends_on: api: {condition: service_started}` (NOT `service_healthy` — frontend must load even when api is warming up, per FR-008).
- [ ] T036 [US3] Run end-to-end smoke: `docker compose up -d`, then `curl -I http://localhost:5173` returns 200 / text/html. Open in a browser, verify three badges. Stop api: `docker compose stop api` → badges render down with error.

**Estimated effort**: 5 tasks · S–M. T034 is M, others S. Total ≈ 2–3 h. **Suggested commit boundary**: one commit ("frontend SPA shell + nginx proxy + status badges").

**Checkpoint**: All three user stories functional. The full `docker compose up -d` flow satisfies every SC from the spec.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Tidy-up that does not belong to any single story but matters for the next feature spec.

- [ ] T037 [P] Configure `ruff` for the backend: add `[tool.ruff]` and `[tool.ruff.lint]` blocks to `backend/pyproject.toml` (target `py312`, enable `E`, `F`, `I`, `B`, `UP`, `ASYNC` rule families). Run `ruff check backend/` and fix any findings.
- [ ] T038 [P] Configure `eslint` placeholder for the frontend: minimal `frontend/.eslintrc.cjs` extending `eslint:recommended` + `plugin:vue/vue3-recommended`; `package.json` `scripts.lint` runs `eslint src/`. No tight enforcement at this stage — placeholder for future UI specs.
- [ ] T039 Idempotency verification: run `docker compose down -v && docker compose up -d` twice in succession; confirm both runs reach all-healthy within 60 s with no manual intervention (SC-004).
- [ ] T040 Update `CLAUDE.md` SPECKIT block to point at this feature's `tasks.md` as the active implementation reference (already at `plan.md` and `spec.md` — append `tasks.md`).
- [ ] T041 Final README polish: ensure the three-command smoke test renders correctly on GitHub (no broken backticks); add a one-line link to `specs/001-infra-scaffold/spec.md` for traceability.

**Estimated effort**: 5 tasks · S each. Total ≈ 1–1.5 h. **Suggested commit boundary**: one commit ("polish: ruff + eslint + README + agent-context").

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)** → starts immediately, no dependencies.
- **Phase 2 (Foundational)** → depends on Phase 1; blocks every story.
- **Phase 3 (US2 — Backend healthcheck)** → depends on Phase 2. **Must complete before Phase 4** (US1's success criterion needs the healthcheck endpoint to exist).
- **Phase 4 (US1 — Single-command onboarding)** → depends on Phase 3.
- **Phase 5 (US3 — Frontend)** → depends on Phase 2 only. **Can run in parallel with Phases 3+4** if developer capacity allows, since the frontend code is independent of backend implementation; only the *integration smoke test* (T036) requires Phase 3/4 done.
- **Phase 6 (Polish)** → depends on Phases 3+4+5.

### Within Each Phase

- Tasks marked `[P]` may run in parallel (different files, no internal dependency).
- Test tasks in Phase 3 (T012–T015) MUST land before their implementation counterparts (T016–T026) — see Constitution Workflow §3, test-first recommended.

### Parallel Opportunities

- T002 + T003 in Phase 1 (env-example and gitignore are independent files).
- T007 + T009 + T010 in Phase 2 (backend skeleton, frontend bootstrap, frontend Dockerfile are independent subtrees).
- T012 + T013 + T016 + T017 + T019 in Phase 3 (test fixtures, unit tests, config, logging, redis client all touch different files; no shared state).
- T032 + T033 in Phase 5 (nginx config and `main.ts` independent).
- T037 + T038 in Phase 6 (lint configs are per-subtree, independent).

---

## Implementation Strategy

### MVP First (Phases 1 + 2 + 3 + 4)

Complete Phases 1 → 2 → 3 → 4 in order. At the end of Phase 4 the entire backend infra slice (US1 + US2) is functional via single command. Frontend (US3) is the next increment, not the MVP itself.

### Commit Boundaries

Per memory rule (commit-granularity): the spec-kit artefacts (spec, plan, research, data-model, contracts, tasks, checklist) are NOT committed individually. During implementation, suggested commits:

1. **End of Phase 2** (foundational): "scaffold: backend + frontend skeletons + Dockerfiles" — meaningful but breakable-out point.
2. **End of Phase 3** (US2): "feat(api): healthcheck endpoint + alembic + pgvector migration + tests" — first PR-ready chunk.
3. **End of Phase 4** (US1): "feat(infra): docker-compose orchestration + .env.example + smoke-test README" — second PR-ready chunk.
4. **End of Phase 5** (US3): "feat(frontend): Vue/Vite shell + nginx proxy + status badges" — third chunk.
5. **End of Phase 6** (polish): "chore: ruff + eslint + idempotency check" — final polish.

Single PR `001-infra-scaffold` → `main` carries all five commits. Each commit message includes the required `Constitution Check: …` line per Governance.

### Parallel Team Strategy (single-developer note)

Solo project; parallelism is only across files within a single sitting. The `[P]` markers above guide which subtasks can be edited in any order within the same phase, not which can be assigned to different developers.

---

## Notes

- Tests are written for the `/healthz` surface only; US1 timing and US3 UI are covered by manual smoke tests in `quickstart.md`. Adding browser-test infrastructure (Playwright / Vitest-DOM) is out of scope for this spec.
- Every callable function added in Phase 3 emits a structlog line per Constitution Workflow §3 — folded into the same task rather than split out.
- The backend Dockerfile installs `curl` per the compose healthcheck dependency; do not switch to `wget` or python-based probes without revisiting `research.md` §8.
- Migrations stay hand-written per `quickstart.md`; if a developer uses `alembic revision --autogenerate` as a starting point during the implement phase, the generated file must be reviewed and rewritten before commit.
- No `print()` calls anywhere in `backend/src/` — Constitution Workflow §3.
