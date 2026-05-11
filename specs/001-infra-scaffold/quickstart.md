# Quickstart: Infrastructure Scaffold

Operator-facing smoke test for the `001-infra-scaffold` feature once implemented. Mirrors the README section but kept in-spec for archival traceability.

## Prerequisites

- Docker Engine 24+ (or Docker Desktop) on Linux, macOS, or Windows.
- Nothing else. No Python, no Node, no Postgres, no Redis on the host (Constitution Principle V).

## Smoke test (three commands)

```bash
git clone git@github.com:tarasIvanov/codesensei.git
cd codesensei
cp .env.example .env
docker compose up -d
```

Within 60 seconds (SC-001) every service should be reported `running (healthy)` by:

```bash
docker compose ps
```

## Verification

```bash
# Healthy backend (HTTP 200 + ok envelope)
curl -fsS http://localhost:8000/healthz | jq

# Frontend serves HTML (HTTP 200, text/html)
curl -I http://localhost:5173
```

Browser visit to `http://localhost:5173` shows three status badges (overall, db, redis) rendered from the `/api/healthz` response.

## Host-port overrides

If any default host port collides with another local process, override via `.env` (no tracked file is edited):

| Variable | Default | Service |
|---|---|---|
| `API_HOST_PORT` | `8000` | `api` |
| `FRONTEND_HOST_PORT` | `5173` | `frontend` |
| `POSTGRES_HOST_PORT` | `5432` | `postgres` |
| `REDIS_HOST_PORT` | `6379` | `redis` |

Example: append `API_HOST_PORT=18000` to `.env` and re-run `docker compose up -d`. The `/healthz` endpoint then lives at `http://localhost:18000/healthz`. The internal container-to-container address (`api:8000`) is unaffected.

## Optional local-LLM (ollama) profile

The `ollama` service is defined in `docker-compose.yml` but NOT in the default profile. To bring it up:

```bash
docker compose --profile ollama up -d
```

Subsequent feature specs (LLM provider integration) will wire it into the api service.

## Reset / idempotent cold start

```bash
docker compose down -v   # wipes postgres_data volume
docker compose up -d     # recreates everything; pgvector extension is re-installed on first migration
```

This sequence must succeed without manual fixes (SC-004).

## Migration policy

- Migrations live in `backend/alembic/versions/`.
- Hand-written by default. `alembic revision --autogenerate` is allowed during development as a starting point but its output is **never** committed without human review.
- One logical schema change per migration.
- The api container's entrypoint runs `alembic upgrade head` before launching uvicorn — operators do NOT run alembic manually.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `api` healthcheck stays unhealthy past 60 s | Postgres image without pgvector → `vector` extension query fails | Confirm the image tag is `pgvector/pgvector:pg16`, not stock `postgres:16`. |
| `frontend` shows blank page | Vite build failed silently inside the Docker build stage | `docker compose build --no-cache frontend` and read the build log. |
| Port collision message at `docker compose up` | Another local service holds that port | Override the relevant `*_HOST_PORT` variable in `.env`. |
| `db: down` on `/healthz` despite Postgres being up | `DATABASE_URL` malformed in `.env` | Check `.env` matches `.env.example` placeholders; the api logs the resolved URL host (not credentials) at startup. |
