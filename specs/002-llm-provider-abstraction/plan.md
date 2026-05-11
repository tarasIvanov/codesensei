# Implementation Plan: LLM and Embedding Provider Abstraction

**Branch**: `002-llm-provider-abstraction` | **Date**: 2026-05-12 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/002-llm-provider-abstraction/spec.md`

## Summary

Introduces the `codesensei.providers` package: two Python `Protocol`-style abstractions (`LLMProvider`, `EmbeddingProvider`) and three concrete adapters (OpenAI, Anthropic, Ollama). Factories `get_llm_provider()` / `get_embedding_provider()` resolve the configured adapter from env vars (`LLM_PROVIDER`, `EMBEDDING_PROVIDER`) lazily, normalize every upstream error to `ProviderError(provider, message, retryable)`, and surface a per-provider `ok | unconfigured | unreachable` probe under `/healthz.providers`. The Vue dashboard gains two badges. No SDK or network call happens on import; tests mock all outbound HTTP.

## Technical Context

**Language/Version**: Python 3.12 (backend), TypeScript / Vue 3 (frontend) — unchanged from 001
**Primary Dependencies**: `openai` ≥ 1.50, `anthropic` ≥ 0.40, `httpx` ≥ 0.27 (Ollama adapter + probes), existing FastAPI / structlog / pydantic-settings
**Storage**: none added — provider state is held in-memory per process; persisted secrets remain in env / `.env` per the existing settings layer
**Testing**: `pytest` + `pytest-asyncio` (already present) + `respx` ≥ 0.21 for mocking httpx, and `unittest.mock.AsyncMock` for the openai / anthropic SDK client surfaces. No live HTTP. CI must pass offline.
**Target Platform**: Linux containers under `docker compose`; same `api` and `frontend` containers from 001 — no new services
**Project Type**: web application (existing `backend/` + `frontend/`) — no new top-level layout
**Performance Goals**: factory resolution < 1 ms; `/healthz` total budget remains ≤ 100 ms additional vs. the 001 baseline (probes are key-presence checks plus at most one `GET /api/tags` to Ollama)
**Constraints**: zero outbound HTTP on import; zero outbound HTTP to paid endpoints during probes; vendor SDK exceptions MUST NOT escape adapter boundaries
**Scale/Scope**: 1 backend service, 1 frontend, 3 adapters, ~ 8 source files added, ~ 10 test files added, no schema changes

## Constitution Check

*Re-evaluated after Phase 1; both checks below are post-design.*

| # | Principle | Status | Notes |
|---|-----------|--------|-------|
| I | Spec-Driven Development | PASS | `spec.md` + this plan + tasks (next phase) cover the work; no architectural surface is being added without an artefact. |
| II | ADR-Driven Architectural Decisions | PASS | This feature *implements* ADR-003 (LLM/Embedding adapter contract). No new database schema, no new queue, no new web framework, no new deployment shape. No ADR amendment required. If ADR-003 currently lists model defaults that conflict with the assumptions in spec.md, a follow-up ADR PR may be needed — flagged but not blocking. |
| III | Pluggable AI Provider Boundaries | PASS — *this feature is the principle's foundation*. All vendor imports live behind adapter classes in `backend/src/codesensei/providers/`. The chat completion contract and the embedding contract live in `base.py`; nothing outside the package imports `openai` / `anthropic` / Ollama-HTTP types. |
| IV | Privacy & Credentials Discipline | PASS | API keys are read from env via the existing `Settings` (no new persistence path). The `/healthz` envelope exposes only an enum (`ok`/`unconfigured`/`unreachable`) — never the key, the host, or the upstream response. The `ProviderError.message` field is for server-side logs and the future `/review` 503 response; it is never echoed via `/healthz`. |
| V | Single-Command Deployment | PASS | No new docker service. Ollama is already an opt-in profile from 001. The feature changes one Dockerfile (backend dependencies grow by three SDKs) and zero compose services. `docker compose up` remains the only operator command. |

**Gate verdict**: all five PASS. Complexity tracking table is intentionally empty (no justified violation needed).

## Project Structure

### Documentation (this feature)

```text
specs/002-llm-provider-abstraction/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── checklists/
│   └── requirements.md  # Already created by /speckit-specify
├── contracts/
│   ├── llm_provider.md
│   ├── embedding_provider.md
│   ├── provider_error.md
│   └── healthz_v2.md
└── tasks.md             # Phase 2 — created by /speckit-tasks
```

### Source Code (repository root)

```text
backend/
├── pyproject.toml                              # +openai, +anthropic, +respx (dev), +httpx is already pulled by FastAPI's testing extras
├── src/codesensei/
│   ├── config.py                               # +LLM_MODEL, +EMBEDDING_MODEL, +OLLAMA_BASE_URL (optional, with sensible defaults)
│   ├── healthcheck.py                          # extend envelope with `providers.llm` + `providers.embedding`
│   └── providers/
│       ├── __init__.py                         # public exports: get_llm_provider, get_embedding_provider, ProviderError, ProviderState
│       ├── base.py                             # LLMProvider Protocol, EmbeddingProvider Protocol, ChatMessage TypedDict, ProviderState enum
│       ├── errors.py                           # ProviderError + classify_http_status() helper
│       ├── factory.py                          # config-driven get_llm_provider() / get_embedding_provider() (lazy, lru_cache-keyed by env values)
│       ├── probe.py                            # async probe_llm_provider() / probe_embedding_provider() — no paid calls
│       ├── openai_adapter.py                   # OpenAIChatProvider + OpenAIEmbeddingProvider (uses official openai SDK)
│       ├── anthropic_adapter.py                # AnthropicChatProvider (chat only); embedding factory raises on selection
│       └── ollama_adapter.py                   # OllamaChatProvider + OllamaEmbeddingProvider (httpx async client)
└── tests/
    ├── conftest.py                              # +mock_provider_probes fixture
    ├── unit/
    │   ├── test_provider_factory.py            # env-driven selection + invalid value rejection + Anthropic-embeddings rejection
    │   ├── test_provider_errors.py             # classify_http_status() truth table
    │   ├── test_openai_adapter.py              # mocked openai SDK — chat + embed happy + 503 + 401
    │   ├── test_anthropic_adapter.py           # mocked anthropic SDK — chat happy + 401 + 503
    │   └── test_ollama_adapter.py              # respx-mocked HTTP — chat + embed happy + ConnectError + 500
    └── integration/
        └── test_healthz_providers.py           # `/healthz` envelope shape with mocked provider probes

frontend/
└── src/
    └── App.vue                                  # +2 badges (llm, embedding) sourcing from envelope.providers
```

**Structure Decision**: existing web-application layout (`backend/` + `frontend/`). No top-level reshuffle. Provider package fills the empty `backend/src/codesensei/providers/` directory that 001 reserved.

## Complexity Tracking

*No constitutional violations to justify; table intentionally empty.*

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| — | — | — |
