# Quickstart — switching providers

Verifies the User Stories from `spec.md` against a running 001 stack with this feature merged. All commands are run from the repo root.

---

## Prerequisites

```bash
cp .env.example .env       # if not already present
docker compose up --build -d
```

Wait until all four services are `(healthy)`:

```bash
docker compose ps --format 'table {{.Service}}\t{{.Status}}'
```

---

## Scenario A — OpenAI (default)

`.env` (relevant rows):

```dotenv
LLM_PROVIDER=openai
EMBEDDING_PROVIDER=openai
OPENAI_API_KEY=sk-...
```

Verify:

```bash
curl -s http://localhost:8000/healthz | jq '.providers'
# {
#   "llm": "ok",
#   "embedding": "ok"
# }
```

Drop the key and restart `api`:

```bash
sed -i.bak 's/^OPENAI_API_KEY=.*/OPENAI_API_KEY=/' .env
docker compose restart api
curl -s http://localhost:8000/healthz | jq '.providers.llm'
# "unconfigured"
```

Open `http://localhost:5173` — the LLM badge is grey (`unconfigured`) and the rest stay green. Overall status remains `ok`.

---

## Scenario B — Anthropic chat + OpenAI embeddings

```dotenv
LLM_PROVIDER=anthropic
EMBEDDING_PROVIDER=openai
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
```

```bash
docker compose restart api
curl -s http://localhost:8000/healthz | jq '.providers'
# {
#   "llm": "ok",
#   "embedding": "ok"
# }
```

---

## Scenario C — Anthropic embeddings (must fail fast)

```dotenv
EMBEDDING_PROVIDER=anthropic
```

```bash
docker compose restart api
docker compose logs api | tail -20
```

Expected: a log line like `provider config rejected: EMBEDDING_PROVIDER=anthropic is not supported; accepted values: openai, ollama`. The container's healthcheck eventually fails (FastAPI app raises on first `get_embedding_provider()` call, which the `/healthz` handler invokes for the probe). Fix by setting `EMBEDDING_PROVIDER` to `openai` or `ollama` and restarting `api`.

---

## Scenario D — Ollama (offline / local)

```dotenv
LLM_PROVIDER=ollama
EMBEDDING_PROVIDER=ollama
```

Bring up Ollama via the opt-in profile:

```bash
docker compose --profile ollama up -d
docker compose exec ollama ollama pull llama3.1:8b
docker compose exec ollama ollama pull nomic-embed-text
docker compose restart api
curl -s http://localhost:8000/healthz | jq '.providers'
# {
#   "llm": "ok",
#   "embedding": "ok"
# }
```

Stop the Ollama service to demonstrate the `unreachable` state:

```bash
docker compose stop ollama
curl -s http://localhost:8000/healthz | jq '.providers'
# {
#   "llm": "unreachable",
#   "embedding": "unreachable"
# }
```

Dashboard shows two red badges; overall status is still `ok`.

---

## Smoke test summary

| Scenario | LLM badge | Embedding badge | Overall |
|----------|-----------|------------------|---------|
| A (OpenAI, key set) | green | green | ok |
| A' (OpenAI, key empty) | grey (`unconfigured`) | grey | ok |
| B (Anthropic + OpenAI) | green | green | ok |
| C (Anthropic embeddings) | container fails health | — | — |
| D (Ollama, both up) | green | green | ok |
| D' (Ollama stopped) | red (`unreachable`) | red | ok |
