# Feature Specification: LLM and Embedding Provider Abstraction

**Feature Branch**: `002-llm-provider-abstraction`
**Created**: 2026-05-12
**Status**: Draft
**Input**: User description: "Pluggable LLM and Embedding provider abstraction. Define LLMProvider and EmbeddingProvider Python protocols/interfaces in backend/src/codesensei/providers/. Implement three concrete adapter sets: OpenAI (chat + embeddings), Anthropic (chat only, fail gracefully on embeddings), Ollama (chat + embeddings via local HTTP). Selection driven by env vars LLM_PROVIDER / EMBEDDING_PROVIDER with lazy config-driven factories. Uniform error envelope (provider name + upstream message + retryable flag) so review-endpoint code does not branch on vendor SDK exception types. Extend /healthz with providers.llm / providers.embedding (ok / unconfigured / unreachable) without consuming API credits. Tests use mocked HTTP only."

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Config-driven provider selection (Priority: P1)

The operator deploys CodeSensei with a chosen LLM and embedding provider by setting `LLM_PROVIDER` and `EMBEDDING_PROVIDER` in the `.env` file (e.g. `LLM_PROVIDER=anthropic`, `EMBEDDING_PROVIDER=openai`). On the next `docker compose up`, the backend transparently uses those providers without any code change. Switching providers later requires only an env-var change and a restart — no code edits, no rebuild of unrelated modules.

**Why this priority**: This is the load-bearing capability of the feature. The entire downstream design of the `/review` endpoint (003+) depends on talking to providers through a single abstraction. Without P1, every future LLM-touching feature would import vendor SDKs directly and freeze the project on a single provider.

**Independent Test**: Start the stack with `LLM_PROVIDER=openai` and confirm a call to `get_llm_provider()` returns the OpenAI adapter; restart with `LLM_PROVIDER=anthropic` and confirm the Anthropic adapter is returned. Verified by unit tests of the factory plus a smoke check via the `/healthz` provider field reflecting the configured provider name.

**Acceptance Scenarios**:

1. **Given** `LLM_PROVIDER=openai` and `OPENAI_API_KEY` set, **When** the backend starts and a caller invokes the LLM provider factory, **Then** the OpenAI adapter is returned and configured for use.
2. **Given** `LLM_PROVIDER=anthropic` and `ANTHROPIC_API_KEY` set, **When** the backend starts, **Then** the Anthropic adapter is returned.
3. **Given** `LLM_PROVIDER=ollama` and the Ollama service reachable, **When** the backend starts, **Then** the Ollama adapter is returned.
4. **Given** `LLM_PROVIDER=mistral` (or any unknown value), **When** the backend starts, **Then** the factory raises a clear configuration error naming the value received and listing the accepted values.

---

### User Story 2 — Anthropic-embeddings combination rejected (Priority: P1)

When an operator misconfigures `EMBEDDING_PROVIDER=anthropic`, the backend refuses to start and tells them exactly why (Anthropic has no embeddings API) rather than failing later with a confusing vendor-specific error during the first real call. This protects against a hard-to-debug production incident where indexing silently fails halfway through a large repository.

**Why this priority**: Same P1 weight as US1 because the safety-net behavior is what makes the abstraction trustworthy. If misconfiguration only surfaces three RAG-pipeline layers deeper, the abstraction has failed its core promise.

**Independent Test**: Set `EMBEDDING_PROVIDER=anthropic` in `.env`, run `docker compose up`, observe that the `api` container fails health within `start_period` with a log line clearly stating that Anthropic does not support embeddings.

**Acceptance Scenarios**:

1. **Given** `EMBEDDING_PROVIDER=anthropic`, **When** the backend resolves the embedding factory, **Then** a configuration error is raised at first access naming the unsupported combination.
2. **Given** the configuration error from scenario 1, **When** an operator reads the log, **Then** the message names both the offending env var and a suggested fix (`openai` or `ollama`).

---

### User Story 3 — Uniform error envelope across providers (Priority: P2)

Whatever provider is selected, callers (the future `/review` endpoint, retry middleware, observability layer) handle a single typed exception that carries provider name, the upstream message, and a `retryable` flag. Callers never need to know about `openai.APIError`, `anthropic.APIStatusError`, or `httpx.ConnectError`.

**Why this priority**: P2 because no caller exists yet — but the contract must be stable before the feature is merged, otherwise 003 will have to either re-shape errors or leak vendor exceptions through the abstraction.

**Independent Test**: For each adapter, mock a transient upstream error (HTTP 503) and confirm a single `ProviderError` is raised with `retryable=True`; mock a permanent error (HTTP 400) and confirm `ProviderError(retryable=False)`. No vendor SDK exception types escape adapter code.

**Acceptance Scenarios**:

1. **Given** the OpenAI adapter and a mocked 503 response, **When** `chat(...)` is called, **Then** a `ProviderError(provider="openai", retryable=True)` is raised.
2. **Given** the Anthropic adapter and a mocked 401 unauthorized, **When** `chat(...)` is called, **Then** a `ProviderError(provider="anthropic", retryable=False)` is raised.
3. **Given** the Ollama adapter and a mocked connection refused, **When** `chat(...)` is called, **Then** a `ProviderError(provider="ollama", retryable=True)` is raised.

---

### User Story 4 — Provider readiness visible on the dashboard (Priority: P3)

Operators inspecting the existing healthcheck dashboard see two new badges — LLM and Embedding — next to the existing DB / Redis / pgvector indicators. The badge state reflects whether each provider is **ok** (configured + reachable), **unconfigured** (env vars missing), or **unreachable** (configured but probe failed, e.g. Ollama container down).

**Why this priority**: P3 because the underlying provider abstraction works regardless of UI; the badges are an operational quality-of-life improvement layered on top of US1–US3.

**Independent Test**: With `LLM_PROVIDER=openai` and a blank `OPENAI_API_KEY`, hit `GET /healthz` and confirm `providers.llm == "unconfigured"`; open the frontend and confirm the LLM badge is amber/red. Set the key and restart, then confirm the badge turns green.

**Acceptance Scenarios**:

1. **Given** all provider env vars correctly set, **When** the dashboard loads, **Then** LLM and Embedding badges render green alongside DB / Redis / pgvector.
2. **Given** `OPENAI_API_KEY` empty while `LLM_PROVIDER=openai`, **When** the dashboard loads, **Then** the LLM badge renders in the non-ok color with the text "unconfigured".
3. **Given** `LLM_PROVIDER=ollama` but the Ollama service stopped, **When** the dashboard loads, **Then** the LLM badge renders in the non-ok color with the text "unreachable".

---

### Edge Cases

- Probing must never charge the operator: OpenAI/Anthropic probes verify only that the API key is non-empty; Ollama probe issues a single `GET /api/tags` (free, local).
- A provider in `unconfigured` or `unreachable` state must not change the overall `/healthz` status from `ok` to `degraded` — overall status remains driven by DB/Redis/pgvector, since no caller in this feature actually consumes the provider yet. Provider states are informational.
- The factory must be lazy: importing `codesensei.providers` must not instantiate any SDK client or read any API key. First call to `get_llm_provider()` / `get_embedding_provider()` triggers construction.
- Whitespace and case in env values must not silently break selection. Selection compares lower-cased, trimmed values.
- Anthropic's lack of embeddings is enforced at factory-resolution time, not at first call — fail fast on startup-time misconfiguration, not in the middle of an indexing run.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST select an LLM adapter based on the `LLM_PROVIDER` env var with accepted values `openai`, `anthropic`, `ollama` (case-insensitive, trimmed).
- **FR-002**: System MUST select an embedding adapter based on the `EMBEDDING_PROVIDER` env var with accepted values `openai`, `ollama` (case-insensitive, trimmed).
- **FR-003**: System MUST reject `EMBEDDING_PROVIDER=anthropic` with a configuration error at the time of factory resolution; the message MUST name the unsupported combination and suggest `openai` or `ollama`.
- **FR-004**: System MUST reject any other unknown provider value with an error listing the accepted values for that role.
- **FR-005**: Provider factories MUST be lazy — importing the providers package or constructing the factory MUST NOT instantiate any HTTP client, read any API key, or touch the network.
- **FR-006**: Every adapter MUST normalize upstream errors into a single exception type (`ProviderError`) exposing `provider: str`, `message: str`, and `retryable: bool` attributes; no vendor SDK exception type may escape adapter code.
- **FR-007**: System MUST classify HTTP 5xx, connection errors, and timeouts as `retryable=True`; HTTP 4xx (other than 429) as `retryable=False`; HTTP 429 as `retryable=True`.
- **FR-008**: OpenAI adapter MUST support chat completions and embeddings via the official OpenAI Python SDK.
- **FR-009**: Anthropic adapter MUST support chat via the Anthropic Messages API; calling its embedding API MUST raise the configuration error from FR-003.
- **FR-010**: Ollama adapter MUST support chat and embeddings via the Ollama HTTP API at the URL configured via env var (default `http://ollama:11434`).
- **FR-011**: `/healthz` response MUST include a `providers` object with two fields `llm` and `embedding`, each containing one of the three string values `ok`, `unconfigured`, `unreachable`.
- **FR-012**: Provider probes MUST NOT call paid endpoints. OpenAI/Anthropic probes MUST only verify that the configured API key is non-empty. Ollama probe MUST be limited to `GET /api/tags`.
- **FR-013**: Provider state MUST NOT alter the overall `/healthz` `status` field; overall status remains driven by DB/Redis/pgvector probes only.
- **FR-014**: The Vue dashboard MUST render two additional badges — `llm` and `embedding` — using the same color/dot UX as the existing four, sourced from the new `providers` object.
- **FR-015**: All adapter tests MUST run without live HTTP — vendor SDK calls and outbound HTTP MUST be mocked. CI MUST be able to pass with no network access to OpenAI / Anthropic / Ollama hosts.
- **FR-016**: Factory selection MUST be re-evaluated only on process start; runtime `LLM_PROVIDER` changes have no effect until restart (consistent with the existing `Settings` `@lru_cache` pattern).

### Key Entities

- **LLMProvider** — abstract capability for chat completion. Holds provider identity and a chat method that accepts a list of messages and returns a single completion text (streaming deferred to 003+).
- **EmbeddingProvider** — abstract capability for embedding generation. Holds provider identity and an embed method that accepts a list of texts and returns one vector per text.
- **ProviderError** — the single normalized exception type any caller of either provider must be prepared to handle; carries `provider`, `message`, `retryable`.
- **ProviderProbeResult** — health-side value used by `/healthz`: one of three states (`ok`, `unconfigured`, `unreachable`).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An operator switches `LLM_PROVIDER` between the three accepted values and observes the dashboard reflect the change after a single `docker compose restart api`, with no code changes between switches.
- **SC-002**: When `EMBEDDING_PROVIDER=anthropic` is set, the misconfiguration surfaces within the first `start_period` of the `api` container, with a log line that names the unsupported combination and a suggested fix.
- **SC-003**: A `/healthz` request completes in under 100 ms additional latency compared to the 001-infra-scaffold baseline; provider probes do not introduce visible slowdown for the dashboard user.
- **SC-004**: The CI test suite passes with no outbound network access — confirmed by running tests in a network-disabled environment / sandbox.
- **SC-005**: The dashboard exposes six badges (db, redis, pgvector, llm, embedding, overall) using a consistent UX; a reviewer recognizing the original four can identify the two new badges without explanation.
- **SC-006**: When the `/review` endpoint is built in feature 003, its implementation imports nothing from `openai`, `anthropic`, or `httpx` directly — only `codesensei.providers`. Verified by `grep` over the 003 PR diff.

## Assumptions

- Existing env vars (`LLM_PROVIDER`, `EMBEDDING_PROVIDER`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`) from 001 are reused; no new env vars beyond optional `OLLAMA_BASE_URL` and per-provider `*_MODEL` overrides.
- Default model names are reasonable lower-tier code-review-suitable choices per provider (e.g. OpenAI `gpt-4o-mini` for chat / `text-embedding-3-small` for embeddings; Anthropic `claude-3-5-sonnet-latest` for chat; Ollama `llama3.1:8b` for chat / `nomic-embed-text` for embeddings). Exact defaults may be tuned during implementation.
- Streaming chat is **not** in scope for 002. The chat method returns the full completion text. Streaming may be added in a later iteration without changing the provider-selection contract.
- Internal retry logic is **not** in scope. Adapters classify errors and surface them; any retry middleware is a future feature consuming the `retryable` flag.
- Provider unconfiguration is treated as an informational state, not an outage. Overall `/healthz` status remains driven by DB/Redis/pgvector; provider misconfiguration is surfaced via badge state only.
- No new persisted entities — the feature is stateless beyond what is already in `Settings`.
- Out of scope (deferred to 003+): RAG ingestion, embedding storage in pgvector, the `/review` endpoint itself, frontend UI changes beyond the two new badges.
