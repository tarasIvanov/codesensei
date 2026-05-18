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

Open `http://localhost:5173` in a browser — the SPA shows four pages styled with a Tailwind v4 design system (light/dark theme follows the OS, override persists in `localStorage`):

- `/` — live status of every component (db, redis, pgvector, LLM provider, embedding provider, worker) with severity-coloured dots and hover tooltips carrying the last error string.
- `/review` — paste a GitHub PR URL → structured findings grouped by file in collapsible cards with severity-coloured pills (`blocker`/`major`/`minor`/`nit`). Optionally pick an indexed repository to enable RAG-augmented review (the response then surfaces the files that contributed retrieved context). Findings against an indexed repository also carry a collapsible "History (N changes)" block listing the recent commits that touched the same line range (driven by `git log -L` against an in-container clone cache); high-volatility locations are flagged with a small inline "N changes" badge next to the severity pill. One-click "Post to GitHub" publishes the review back to the PR as a native review with inline comments via `POST /api/review/post` (uses the `codesensei-bot` PAT from `/settings`). Async-action feedback (review submit, post-to-GitHub, retries) is surfaced through toast notifications. See [`specs/003-pr-review-mvp/quickstart.md`](specs/003-pr-review-mvp/quickstart.md) for the original diff-only flow, [`specs/005-rag-indexing/quickstart.md`](specs/005-rag-indexing/quickstart.md) for the RAG flow, [`specs/006-pr-review-posting/quickstart.md`](specs/006-pr-review-posting/quickstart.md) for the GitHub-posting flow, [`specs/007-ui-tailwind-polish/quickstart.md`](specs/007-ui-tailwind-polish/quickstart.md) for the UI polish smoke walkthrough, and [`specs/008-git-temporal-analysis/quickstart.md`](specs/008-git-temporal-analysis/quickstart.md) for the git-temporal-analysis smoke walkthrough.
- `/repos` — index a public HTTPS repository or a locally mounted directory; chunks live in pgvector (HNSW + cosine). Sync for ≤200 source files; async via the arq queue for larger repos. Re-indexing replaces chunks atomically. Rows expand in place to reveal chunk count, last indexing error, and per-repo actions.
- `/settings` — switch active LLM/embedding provider, manage API keys and model overrides without editing `.env`. Credentials are stored encrypted at rest (Fernet, keyed on `MASTER_KEY`). A "Test connection" button next to the GitHub PAT field runs a read-only probe of `GET https://api.github.com/user` via `GET /api/settings/test/github` and surfaces the resolved GitHub login inline without touching settings state. See [`specs/004-ops-quality-polish/quickstart.md`](specs/004-ops-quality-polish/quickstart.md).

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
