# Feature Specification: Infrastructure Scaffold

**Feature Branch**: `001-infra-scaffold`
**Created**: 2026-05-11
**Status**: Draft
**Input**: User description: "Infrastructure scaffold for CodeSensei — bring up the minimal docker-compose stack with empty backend (FastAPI) and frontend (Vue 3 + Vite served by nginx) skeletons so all subsequent feature work has a running base to build against."

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Single-command developer onboarding (Priority: P1)

A developer who has cloned the CodeSensei repository for the first time wants to bring the entire stack up locally with no manual setup beyond cloning, copying the example environment file, and issuing one container-orchestration command. Within roughly a minute every service should reach a healthy state, with no intermediate prompts, host-side installs, or follow-up scripts.

**Why this priority**: this single-command deployment promise is the headline differentiator of CodeSensei against fiddly self-hosted alternatives, codified in Constitution Principle V. If onboarding requires any host-side build step, the product positioning collapses on day one.

**Independent Test**: clone the repo on a clean machine with only Docker installed; run `cp .env.example .env` and `docker compose up -d`; after ≤ 60 seconds, `docker compose ps` reports every service as `running (healthy)` without any further action.

**Acceptance Scenarios**:

1. **Given** a clean host with Docker Engine 24+ installed and no other CodeSensei artefacts, **When** the developer runs the three onboarding commands, **Then** every service container reports a healthy state within 60 seconds.
2. **Given** a host where the developer has previously run `docker compose down -v` (wiping volumes), **When** the developer runs `docker compose up -d` again, **Then** the stack reaches the same healthy state with no manual fixes required.
3. **Given** a host where one of the default host ports is already occupied by another process, **When** the developer overrides the corresponding `*_HOST_PORT` variable in `.env` and runs `docker compose up -d`, **Then** every service binds to the overridden ports and reaches a healthy state.

---

### User Story 2 — Backend healthcheck endpoint (Priority: P2)

A developer (or a future CI smoke test) wants a single HTTP endpoint that reports the connectivity status of the backend's downstream dependencies — the database (Postgres + pgvector) and the queue broker (Redis). The endpoint is used both as the container-level healthcheck for the api service and as the canonical "is everything wired up correctly?" probe for humans and automation.

**Why this priority**: without a deterministic health signal, US1 cannot verify itself ("are all services *actually* healthy?") and future CI jobs would need bespoke probes per dependency. This is the second-most-valuable slice because it makes US1 testable.

**Independent Test**: with the stack up, `curl http://localhost:8000/healthz` returns HTTP 200 and a JSON body whose top-level fields all read `ok`. When Postgres is stopped explicitly, the same call returns HTTP 503 and surfaces which component failed.

**Acceptance Scenarios**:

1. **Given** the full stack is running and Postgres and Redis are reachable, **When** any client calls the healthcheck endpoint, **Then** the response is HTTP 200 with a JSON envelope reporting `status: ok` and `ok` for each individual dependency.
2. **Given** the api container is running but Postgres has been stopped, **When** any client calls the healthcheck endpoint, **Then** the response is HTTP 503 with the failing dependency named in the JSON envelope.
3. **Given** the api container is running but Redis has been stopped, **When** any client calls the healthcheck endpoint, **Then** the response is HTTP 503 with Redis named as the failing dependency.

---

### User Story 3 — Frontend skeleton calling the API (Priority: P3)

A developer wants the frontend container to serve a minimal, browser-renderable page that exercises the full Vite-build → static-serve → SPA-to-API path end-to-end, so that subsequent UI feature work starts on a known-working pipeline rather than a blank slate.

**Why this priority**: the frontend pipeline (build step, container packaging, reverse proxy to the api) has its own failure modes independent of US1 and US2. Validating it now removes uncertainty later, but it is not blocking for any backend or infra work — hence P3.

**Independent Test**: visit the frontend URL in a browser; the page renders three status badges (overall, database, queue) reflecting the response of the healthcheck endpoint. `curl -I http://localhost:5173` returns HTTP 200 with a `text/html` content-type.

**Acceptance Scenarios**:

1. **Given** the full stack is running, **When** a developer visits the frontend URL in a browser, **Then** a page renders within 1 second showing three status indicators driven by the healthcheck response.
2. **Given** the api container is unreachable from the browser's network point of view, **When** the page loads, **Then** the indicators render in a clearly non-ok state with a brief explanatory message rather than the page failing to render at all.

---

### Edge Cases

- **Host port collisions** on 5432, 6379, 8000, or 5173: the stack must allow the developer to override each via environment variables before `docker compose up`, with documented defaults.
- **pgvector availability**: a stock Postgres 16 image does not ship the `vector` extension; the chosen base image must include it, and the init migration must be idempotent on repeated `docker compose down -v && up` cycles.
- **Healthcheck race during cold start**: Postgres takes several seconds to install the `vector` extension on first boot; the api container's healthcheck must tolerate a grace period of up to 30 seconds before reporting failure.
- **Empty `.env`**: a freshly copied `.env.example` contains no real credentials. The stack must still reach a healthy state with those blank values; nothing in the scaffold spec requires real API keys.
- **Repeated `docker compose up`** without `down`: a running stack should not be disturbed; the command must be idempotent.
- **Optional ollama profile**: the `ollama` service is defined but does NOT start by default; it must only come up when the developer explicitly opts in via `docker compose --profile ollama up`.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST provide a `docker-compose.yml` (or `compose.yaml`) at the repository root that declares the services needed for the MVP infrastructure baseline.
- **FR-002**: The system MUST include the following services in the default profile: an api service (backend), a frontend service, a database service (Postgres 16 with the pgvector extension), and a queue broker service (Redis).
- **FR-003**: The system MUST include an `ollama` service that is gated behind an opt-in profile and does NOT start by default.
- **FR-004**: The system MUST expose a backend HTTP endpoint at `/healthz` that returns HTTP 200 with a structured response declaring `ok` for every checked dependency when the database and queue broker are reachable, and HTTP 503 with the failing dependency named otherwise.
- **FR-005**: The system MUST configure the api container's compose-level `healthcheck` to use the `/healthz` endpoint as the probe.
- **FR-006**: The system MUST declare a `healthcheck` for every other service (database, queue broker, frontend) using probes appropriate to each technology.
- **FR-007**: The system MUST configure the api service to wait until the database and queue broker are healthy (`depends_on: service_healthy`) before starting.
- **FR-008**: The system MUST configure the frontend service to wait only until the api service has started (`depends_on: service_started`), so that the page itself loads even when the api is still warming up; the live `/healthz` call surfaces the runtime status.
- **FR-009**: The system MUST initialise alembic in the backend with one migration whose sole effect is to enable the `vector` extension in Postgres; no business tables are introduced by this spec.
- **FR-010**: The system MUST provide a `.env.example` file that enumerates every environment variable the stack reads, with safe placeholder values.
- **FR-011**: The system MUST allow the developer to override the host-side bound ports for every public service via environment variables, with sensible defaults that are unlikely to collide with common developer tools.
- **FR-012**: The system MUST be runnable end-to-end with `git clone … && cp .env.example .env && docker compose up -d` — no additional host-side installs or scripts.
- **FR-013**: The system MUST be idempotent across `docker compose down -v && docker compose up -d` cycles: every subsequent cold start reaches the same healthy state without manual intervention.
- **FR-014**: The frontend container MUST serve a minimal Vue 3 single-page application that, on load, calls `/healthz` and renders the per-dependency status visibly in the browser.
- **FR-015**: The frontend container MUST route browser calls to `/api/*` (or an equivalent prefix) to the api service via the in-container reverse proxy, so the developer does not have to configure CORS for the scaffold.
- **FR-016**: The README at the repository root MUST document the three-command smoke test and list the supported environment-variable overrides.
- **FR-017**: The system MUST emit a structured log line (per Constitution Workflow §3 "Structured logging") on api startup recording the resolved provider configuration (without credential values) and the result of each dependency check.
- **FR-018**: The api healthcheck implementation MUST tolerate up to 30 seconds of database boot-time before reporting persistent failure (start-period grace for Postgres + pgvector extension installation).

### Key Entities

- **`api` container**: the backend skeleton. Reads configuration from environment variables; exposes `/healthz`; runs the alembic migration on startup; owns the dependency check against the database and the queue broker.
- **`frontend` container**: the SPA skeleton. Serves statically-built Vue 3 assets; reverse-proxies `/api/*` to the api container; renders the healthcheck result on load.
- **`postgres` container**: PostgreSQL 16 with the pgvector extension available; persistent volume for data; init migration enables the `vector` extension on first boot.
- **`redis` container**: queue broker for the future arq worker; no workers spawned at this stage.
- **`ollama` container** *(optional, opt-in profile)*: local LLM service, defined for future use; not part of the default startup path.
- **`.env` / `.env.example`**: the single source of host-side configuration; documents every variable the stack reads.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On a 2024-era developer laptop, the elapsed time from issuing the orchestration "up" command to every service reporting healthy is no more than 60 seconds.
- **SC-002**: The backend healthcheck endpoint returns a fully-`ok` envelope (HTTP 200) when all dependencies are reachable, and a clearly-attributed failing envelope (HTTP 503) within 5 seconds of a dependency becoming unreachable.
- **SC-003**: The frontend URL returns HTTP 200 with HTML content and the page renders all three status indicators within 1 second of receiving the healthcheck response.
- **SC-004**: A `down -v` followed by a fresh `up` reaches the all-healthy state with the same timing characteristics as the first cold start (no manual fix-ups required).
- **SC-005**: The number of host-side steps required between cloning the repository and a fully-healthy stack is exactly three (clone, copy env file, orchestrate up). Any additional step is a violation of this success criterion.
- **SC-006**: A developer can override any of the four public host ports via environment variables and still reach the all-healthy state without editing any tracked file.

## Assumptions

- The developer has Docker Engine 24+ or Docker Desktop installed on macOS, Linux, or Windows; no host-side Python, Node.js, Postgres, or Redis runtime is required (per Constitution Principle V).
- A blank `.env` copied verbatim from `.env.example` is sufficient to reach the all-healthy state for this scaffold spec. Real credentials are not required until later feature specs (LLM provider integration, GitHub PAT-based PR fetching, bot-mode posting) introduce them.
- The frontend SPA at this stage is intentionally minimal — Vue 3 default project shell, a single root component, the healthcheck call, and the three status indicators. No client-side router, no state-management library, no UI component library. Subsequent UI features may add these via their own specs.
- The Redis container is configured but no arq worker is started in this spec. Workers come in a later spec; Redis is present so that subsequent specs can attach without re-touching the compose file's core shape.
- Pre-flight secret scrubbing on chunks (Constitution Principle IV) is deferred to the indexing-pipeline spec; this scaffold spec is intentionally credential-free.

## Out of Scope

Explicitly NOT part of this spec (each will land via its own future spec):

- The arq worker container and any task scheduling logic.
- The ollama container starting by default (it stays behind an opt-in profile).
- Any indexing pipeline, retrieval logic, LLM/embedding adapter implementation, settings UI, history UI, or PR-review UI.
- alembic migrations beyond enabling the `vector` extension; no business tables, no application schema.
- Production-grade nginx configuration, TLS termination, multi-host scaling, or reverse-proxy hardening.
- Authentication, authorisation, or multi-tenant separation (out of MVP per `_mvp_scope.md` §4 and Constitution scope).
- Encrypted-at-rest credential storage (Constitution Principle IV): real credentials are introduced in later specs and that spec ships the encryption.

## Constitution Alignment Notes

For the downstream `/speckit-plan` phase, three architectural decisions require new ADRs in `../_decision_log.md` BEFORE planning begins, per Constitution Principle II:

- **ADR-007** — pgvector base image (candidates: `pgvector/pgvector:pg16` upstream, `ankane/pgvector` community fork, a custom Dockerfile built on `postgres:16`).
- **ADR-008** — alembic migration style and directory layout (autogenerated migrations vs hand-written; whether migrations live under `backend/alembic/versions/` or another path).
- **ADR-009** — logging stack for the api service (`structlog` vs `loguru`), since Constitution Workflow §3 mandates structured logs and the choice between these two libraries shapes every subsequent backend log call.

`/speckit-plan` MUST gate its execution on these ADRs being recorded.

Constitution Check (preview for plan phase): Principle I (this spec itself satisfies the precondition), Principle II (three new ADRs required), Principle V (every component is a compose service, no host-side setup).
