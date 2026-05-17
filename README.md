# CodeSensei

Self-hosted AI Code Reviewer with persistent RAG indexing over the entire repository, deployed via a single `docker-compose up`.

> **Status:** pre-MVP — infrastructure scaffold deployed; feature implementation in progress.

Bachelor thesis project, KPI FAM (спеціальність 121, ІПЗ, 2026). Codename per ADR-001.

## Quick Start

```bash
cp .env.example .env          # adjust keys / port overrides as needed
docker compose up --build -d  # pull images, build, start all services
curl http://localhost:8000/healthz  # should return {"status":"ok",...}
```

Open `http://localhost:5173` in a browser — the SPA shows three pages:

- `/` — live status of every component (db, redis, pgvector, LLM provider, embedding provider, worker).
- `/review` — paste a GitHub PR URL → structured findings rendered grouped by file. End-to-end demo of the LLM provider abstraction. See [`specs/003-pr-review-mvp/quickstart.md`](specs/003-pr-review-mvp/quickstart.md) for scenarios.
- `/settings` — switch active LLM/embedding provider, manage API keys and model overrides without editing `.env`. Credentials are stored encrypted at rest (Fernet, keyed on `MASTER_KEY`). See [`specs/004-ops-quality-polish/quickstart.md`](specs/004-ops-quality-polish/quickstart.md).

### Port overrides

| Service   | Env var               | Default |
|-----------|-----------------------|---------|
| API       | `API_HOST_PORT`       | 8000    |
| Frontend  | `FRONTEND_HOST_PORT`  | 5173    |
| Postgres  | `POSTGRES_HOST_PORT`  | 5432    |
| Redis     | `REDIS_HOST_PORT`     | 6379    |
| Ollama    | `OLLAMA_HOST_PORT`    | 11434   |

Ollama service is opt-in: `docker compose --profile ollama up`.

---

See [`_bootstrap_prompt.md`](_bootstrap_prompt.md) for the meta-contract of the first development session.
