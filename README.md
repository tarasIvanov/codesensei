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

Open `http://localhost:5173` in a browser — the healthcheck dashboard shows live status of all components.

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
