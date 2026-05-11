# Phase 0 — Research: Infrastructure Scaffold

All `NEEDS CLARIFICATION` markers from `plan.md` resolved here. Each subsection: **Decision** → **Rationale** → **Alternatives considered**.

---

## 1. pgvector base image

**Decision**: `pgvector/pgvector:pg16` (official upstream image).

**Rationale**: official, actively maintained, ships pgvector pre-installed in a stock Postgres 16 image, so `CREATE EXTENSION vector` succeeds without custom build steps. Sized comparably to `postgres:16-alpine` after layer dedup.

**Alternatives considered**:
- `ankane/pgvector` — community fork, smaller user base, last release lag risk. Rejected as a hedge against single-maintainer drift.
- Custom Dockerfile on `postgres:16-alpine` + manual `pgvector` build — adds a multi-stage build with C toolchain, slows `docker compose build` for no functional gain at this stage. **Kept as fallback** if the upstream image ever stops being maintained.

---

## 2. Backend dependency management

**Decision**: `uv` for environment, install, and lockfile (`uv.lock`).

**Rationale**: already installed on the dev host (validated during spec-kit bootstrap); resolves Python dep graphs an order of magnitude faster than `pip-tools`; integrates with `pyproject.toml` natively (PEP 621); single binary, no virtualenv-manager indirection.

**Alternatives considered**:
- `pip-tools` (`requirements.in` → `requirements.txt` via `pip-compile`) — proven but slower; lockfile is less expressive than `uv.lock`.
- `poetry` — heavier; its `poetry.lock` format diverges from PEP standards; opinionated about project layout in ways that fight `src/` projects.

---

## 3. Frontend package manager

**Decision**: `pnpm` (lockfile `pnpm-lock.yaml`).

**Rationale**: content-addressable global store reduces disk usage and accelerates rebuilds inside the Docker build cache; strict `node_modules` layout catches accidental phantom-dependency reliance early; works cleanly in Vite 6 + Vue 3.5 ecosystems.

**Alternatives considered**:
- `npm` — universal, slower install in monorepos, less strict resolution.
- `yarn` (berry / classic) — strong on monorepos but unnecessary for a single-package frontend at this scale; PnP mode causes friction with some Vite plugins.

**Note**: pnpm is invoked only inside the frontend Docker build stage. Developers do NOT need pnpm on the host (Constitution Principle V).

---

## 4. alembic env.py async wiring

**Decision**: async-aware `env.py` using SQLAlchemy 2 `AsyncEngine`; `run_migrations_online()` wraps `engine.begin()` in `asyncio.run`, then calls `context.run_migrations()` inside a sync callback via `connection.run_sync(do_run_migrations)`.

**Rationale**: alembic itself is synchronous, but our SQLAlchemy engine is async (ADR-005). The standard pattern from the SQLAlchemy docs (`Asynchronous Migration` recipe) bridges the two without forking a separate sync engine just for migrations.

**Skeleton** (to land verbatim in `backend/alembic/env.py`):

```python
import asyncio
from sqlalchemy.ext.asyncio import async_engine_from_config
from alembic import context

def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=None)
    with context.begin_transaction():
        context.run_migrations()

async def run_migrations_online():
    connectable = async_engine_from_config(
        context.config.get_section(context.config.config_ini_section),
        prefix="sqlalchemy.",
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()

if context.is_offline_mode():
    raise RuntimeError("offline mode not supported for this project")
else:
    asyncio.run(run_migrations_online())
```

**Alternatives considered**:
- Maintain a parallel sync engine just for alembic — doubles connection configuration, divergence risk on URL/SSL/pool settings.

---

## 5. structlog configuration

**Decision**: JSON renderer to stdout, log level from `LOG_LEVEL` env var (default `INFO`), processor chain: `merge_contextvars` → `add_log_level` → `TimeStamper(fmt="iso", utc=True)` → `JSONRenderer()`. No file handler.

**Rationale**: Constitution Workflow §3 requires structured logs to stdout (NFR-5.2). JSON renderer pipes into any log aggregator unchanged. `merge_contextvars` lets request-scoped context (request ID, future user) propagate without explicit threading.

**Skeleton** (to land in `backend/src/codesensei/logging_config.py`):

```python
import logging, sys, structlog
def configure_logging(level: str = "INFO") -> None:
    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            timestamper,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, level)),
        cache_logger_on_first_use=True,
    )
    logging.basicConfig(stream=sys.stdout, level=level, format="%(message)s")
```

**Alternatives considered**:
- `loguru` — single-import ergonomics but lacks contextvar-based context propagation as a first-class primitive; harder to compose processor chains for future fields (request ID, span ID).
- stdlib `logging` with JSON formatter — works but verbose to configure and harder to add typed context.

---

## 6. Healthcheck probe semantics

**Decision**:
- **DB probe**: open async session, run `SELECT 1`; in the same session run `SELECT 1 FROM pg_extension WHERE extname = 'vector'` and require exactly one row. Failure on either step → `db: down` (and `extensions.vector: missing` if specifically that row was empty).
- **Redis probe**: `await redis.ping()` returning `b"PONG"` (or `"PONG"` depending on `decode_responses`) → `redis: ok`.
- **Concurrency**: probes execute in parallel via `asyncio.gather(db_probe(), redis_probe(), return_exceptions=True)`; any exception or False return → the corresponding component flagged in the JSON envelope.
- **Timeout**: total handler budget of **3 seconds** (`asyncio.wait_for(..., timeout=3.0)`); on timeout the still-pending probes flag `down`.

**Rationale**: parallel probes keep p95 close to the slowest dep, not the sum (SC-002: ≤ 5 s degraded response is satisfied with a 3 s budget). The pgvector extension check guards against a Postgres image that boots but didn't install the extension (edge case in spec). Total 3 s budget leaves margin for clock skew and Docker network latency on slow hosts.

**Alternatives considered**:
- Sequential probes — adds latency, no robustness gain.
- Skip `pg_extension` check — fragile to image regressions silently re-introducing the upstream `postgres:16` image.

---

## 7. Frontend → backend routing

**Decision**: nginx serves the Vite-built static SPA from `/`, and proxies `/api/*` to `http://api:8000/*` (Docker service-name DNS). The SPA calls `/api/healthz`; the api router prefixes its endpoints with `/api/`.

**Rationale**: avoids host-side CORS configuration for the scaffold (FR-015). Same-origin from the browser's perspective. Future feature specs that introduce websockets do the same: `/api/ws/*` proxied with `proxy_http_version 1.1` + Upgrade/Connection headers.

**nginx.conf snippet** (to land in `frontend/nginx.conf`):

```nginx
server {
  listen 80;
  root /usr/share/nginx/html;
  index index.html;

  location /api/ {
    proxy_pass http://api:8000/api/;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
  }

  location / {
    try_files $uri $uri/ /index.html;
  }
}
```

**Alternatives considered**:
- Configure CORS in FastAPI, frontend hits `api:8000` directly via host network — requires the frontend to know the api host port, which breaks SC-006 (port overrides should not need frontend rebuild).
- Single combined service (gunicorn + nginx in one image) — fights ratified two-service architecture.

---

## 8. Docker healthcheck commands

Per-service compose `healthcheck:` directives (Docker Compose v3+):

| Service | Test | Interval | Timeout | Retries | Start period |
|---|---|---|---|---|---|
| `api` | `curl -fsS http://localhost:8000/healthz \|\| exit 1` | 5s | 3s | 5 | 30s |
| `postgres` | `pg_isready -U $POSTGRES_USER -d $POSTGRES_DB` | 5s | 3s | 5 | 10s |
| `redis` | `redis-cli ping \| grep -q PONG` | 5s | 3s | 5 | 5s |
| `frontend` | `wget -qO- http://localhost/ >/dev/null` | 10s | 3s | 3 | 5s |

**Rationale**: `start_period` of 30 s on the api absorbs Postgres + pgvector boot time (edge case in spec). All probes use binaries already present in their respective official base images — no extra layers required.

**Alternatives considered**:
- Embed Python in the api healthcheck — adds a process-start cost; `curl` is faster and image-native.

---

## Constitution rechecked post-research

No research item ripples into an ADR-mandated surface. Constitution Check section in `plan.md` remains `PASS` across all five principles.
