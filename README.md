# CodeSensei — Self-hosted AI Code Reviewer

> Defence-grade Pull Request reviewer that runs entirely on the operator's hardware.
> Deep AST-RAG indexing + git-temporal context + air-gappable local LLM.

---

## Дипломна робота / Thesis context

Це випускна кваліфікаційна робота бакалавра. Автор — **Тарас Іванов**. Спеціальність 121, ІПЗ. Мета — побудувати self-hosted альтернативу хмарним сервісам типу CodeRabbit / Greptile, що:

- виконує повноцінний AI-ревʼю Pull Request-ів;
- може працювати **air-gapped** (без виходу в мережу) на власному обладнанні через Ollama;
- комбінує persistent **AST-RAG index** репозиторію (tree-sitter + pgvector + HNSW) з **темпоральним аналізом** (`git log -L` по змінених рядках);
- розгортається однією командою `docker compose up`.

Project goal in one sentence: replace cloud PR-review services with a single-command self-hosted stack that combines deep RAG indexing and git-history-aware analysis, without sending source code to third-party clouds unless the operator opts in.

---

## Three differentiators (per ADR-011)

1. **Self-hosted, air-gappable LLM.** Pluggable provider layer (`LLMProvider` adapter contract, ADR-003) ships with three implementations: `OpenAI` and `Anthropic` (cloud opt-in) plus `Ollama` (local, runs inside the compose stack — no outbound network). Operator picks per-deployment via `/settings` without editing source.
2. **Persistent AST-RAG index.** Whole repositories — not just diffs — are AST-chunked via tree-sitter (Python / TypeScript / JavaScript / Markdown supported), embedded, and stored in PostgreSQL + pgvector with HNSW index for cosine similarity (ADR-004). Reviews retrieve overlap chunks + vector top-K context that gets included in the prompt.
3. **Git-based temporal analysis.** For every modified line range in a PR, the reviewer runs `git log -L <range>:<file>` against an in-container clone cache and surfaces the 5–10 most recent commits that touched the same window. Hotspot windows (>10 changes in 90 days) get a severity bump. No vectorisation of history required.

---

## Quick start

Requirements: Docker + Docker Compose (≥ v2). Host needs ports 5173 (SPA), 8000 (API), 5432 (Postgres), 6379 (Redis) free — adjust via `*_HOST_PORT` env vars if needed.

```bash
git clone git@github.com:tarasIvanov/codesensei.git
cd codesensei/app
cp .env.example .env                 # adjust keys / port overrides as needed (MASTER_KEY auto-generates on first run)
docker compose up --build -d         # pulls images, builds, starts api + worker + frontend + postgres + redis
open http://localhost:5173/settings  # configure provider keys (OpenAI / Anthropic / Ollama) + GitHub PAT
```

Submit a PR URL on `/review` to produce a review. Local Ollama profile is opt-in: `docker compose --profile ollama up -d`.

`docker compose down -v` wipes the database (chunks + history). Without `-v`, persisted state survives a restart.

---

## Architecture brief

CodeSensei is a single-stack monorepo with a FastAPI backend, a Vue 3 SPA, and a PostgreSQL + Redis data plane, all orchestrated via `docker-compose`. The API exposes `/review`, `/index`, `/repos`, `/reviews`, `/jobs`, `/settings`, `/healthz`; the worker runs long-running indexing jobs via the `arq` queue on Redis; the frontend talks to the API through an nginx reverse proxy inside the `frontend` container, which forwards WebSocket upgrades for the live indexing-progress stream.

**Stack**:

- **Backend** — Python 3.12, FastAPI, SQLAlchemy 2.x async, asyncpg, alembic, arq + Redis, pgvector, structlog, tree-sitter, tiktoken, openai / anthropic / httpx SDKs.
- **Frontend** — Vue 3.5, Vite 6, TypeScript 5.7, vue-router 4, Tailwind v4 with in-tree primitives (no external UI lib).
- **Data** — PostgreSQL 16 + pgvector (HNSW), Redis 7 (arq queue + WebSocket pub/sub channel), encrypted-at-rest credentials (Fernet, keyed on `MASTER_KEY` auto-provisioned per ADR-014).
- **AI providers** — OpenAI default (`gpt-4o-mini` chat + `text-embedding-3-small` embed), Anthropic (`claude-3-5-sonnet-latest`), Ollama (any chat + `BAAI/bge-m3` via sentence-transformers for embeddings).

---

## Features at a glance

- **PR review** — paste a GitHub PR URL on `/review` → structured findings grouped by file with severity-coloured pills (`blocker` / `major` / `minor` / `nit`), suggested fixes inline, dismissible per-finding before posting.
- **Bot-mode posting** — one-click "Post to GitHub" publishes the review back as a native PR review with inline comments via a separate bot PAT (ADR-006).
- **Repository indexing** — index any public HTTPS repository or locally-mounted directory. Sync for ≤200 source files, async via `arq` for larger repos. Atomic chunk-swap on re-index. Honours a project-local `.codesensei-ignore` file (gitignore-like syntax, hard caps 4 KB / 200 patterns).
- **Live progress** — WebSocket stream `/api/jobs/{id}/stream` pushes `init` → `progress` → `complete` frames from the worker via Redis pub/sub. Graceful polling fallback at 2 s interval if the WS handshake fails.
- **Review history** — every successful run lands in `review_runs` + `review_findings` with verdict, findings, provider, elapsed_ms, token counts, cost estimate, per-finding temporal context. `/history` lists the 50 newest with verdict filter chips; detail view replays without a fresh LLM call. Auto-prune at 1000 rows.
- **Token + cost tracking** — every LLM call surfaces `prompt_tokens` / `completion_tokens` / `cost_usd` on the wire and persists them on the `review_runs` row. Pricing table (`backend/src/codesensei/review/pricing.py`) is a single dict of `(provider, model) → (in $/1M, out $/1M)`; updates flow through PR review.
- **Settings UI** — switch active providers, manage API keys + model overrides, test the GitHub PAT with one click. Master encryption key auto-provisions on first boot (ADR-014); operator never sees a "set MASTER_KEY" prompt.
- **Welcome page** — `/welcome` carries a four-step setup walkthrough that self-marks each step done as the operator completes it.

---

## Project documentation map

The project is **spec-driven**. Every non-trivial subsystem has a spec → plan → tasks → research artefact set:

- `_decision_log.md` — Architecture Decision Records (ADR-001 through ADR-016). Every database, queue, framework, provider, or transport choice has a justification entry here.
- `_mvp_scope.md` — MUST / NICE-TO-HAVE / OUT-OF-SCOPE breakdown for the bachelor-thesis defence.
- `_requirements.md` — original Notion-style requirements draft (pre-scope).
- `specs/<NNN-feature>/` — per-feature artefacts:
  - `spec.md` — user stories, functional requirements, success criteria.
  - `plan.md` — technical context, Constitution check, project structure.
  - `research.md` — implementation decisions + rationale.
  - `data-model.md` — entities, persistence shape.
  - `contracts/` — wire-shape contracts for endpoints + modules.
  - `tasks.md` — executable task list (T001…).
  - `quickstart.md` — manual smoke-test walkthrough.
- `.specify/memory/constitution.md` — project Constitution: five core principles (Spec-Driven, ADR-Driven, Pluggable Providers, Privacy & Credentials, Single-Command Deploy) plus quality gates.
- `_bootstrap_prompt.md` — meta-contract of the first development session.

For a deep dive into any architectural decision (e.g. "why pgvector over Qdrant?", "why arq over Celery?", "why JSONB for temporal context?") start with `_decision_log.md` and follow the ADR number into the referenced feature spec.

---

## Port overrides

| Service   | Env var               | Default |
|-----------|-----------------------|---------|
| API       | `API_HOST_PORT`       | 8000    |
| Frontend  | `FRONTEND_HOST_PORT`  | 5173    |
| Postgres  | `POSTGRES_HOST_PORT`  | 5432    |
| Redis     | `REDIS_HOST_PORT`     | 6379    |
| Ollama    | `OLLAMA_HOST_PORT`    | 11434   |

---

## License

Educational use — bachelor thesis project. Not yet open-source-licensed; licensing terms will be decided after thesis defence.

---

## Contact

Questions / feedback — `ivanov.dmytro.ua@gmail.com` (project author).
