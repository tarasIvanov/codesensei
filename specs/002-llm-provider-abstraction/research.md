# Phase 0 — Research: Provider Abstraction Implementation Decisions

Resolves every NEEDS-CLARIFICATION from `plan.md > Technical Context` and pins concrete library and pattern choices for the three adapters, the factory, the probes, and the test rigging.

---

## R1. HTTP-mocking library for adapter tests

**Decision**: `respx ≥ 0.21` for everything that goes out via `httpx` (the Ollama adapter, the Ollama probe). `unittest.mock.AsyncMock` for the OpenAI and Anthropic SDK surfaces (those SDKs do not call `httpx` directly in a way that respx hooks cleanly into when used through their high-level clients).

**Rationale**: respx is the de-facto async httpx-mocking library, integrates with `pytest` markers, and lets us assert request URLs/headers without spinning a real server. For the official OpenAI and Anthropic SDKs, intercepting at the SDK-client method level (`AsyncOpenAI.chat.completions.create`, `AsyncAnthropic.messages.create`) keeps tests stable across vendor SDK version bumps — those interfaces are far more stable than the underlying HTTP wire formats.

**Alternatives considered**:
- `pytest-httpx` — works but the API is slightly noisier and assertion ergonomics are worse than respx for the multi-request Ollama probe.
- VCR-style cassettes (`pytest-recording`) — overkill for the scope; cassettes need refreshing and bring real responses into git.
- Hand-rolled `httpx.MockTransport` — viable but duplicates respx with no upside.

---

## R2. OpenAI SDK version + async surface

**Decision**: `openai ≥ 1.50`, use `AsyncOpenAI` client; chat via `client.chat.completions.create(...)`; embeddings via `client.embeddings.create(...)`.

**Rationale**: the 1.x SDK has a stable async client, official streaming support (deferred but contract-compatible), and per-call timeout overrides. ≥ 1.50 pins us after the breaking changes around tool-call shape stabilized.

**Alternatives considered**:
- Direct httpx-against-the-REST-endpoint — loses the SDK's retry/error-mapping surface, more wire-format maintenance.
- Pinning to a single 1.x.y — too tight; 1.50+ as a floor lets `uv` resolve a current minor without forcing churn.

---

## R3. Anthropic SDK version + async surface

**Decision**: `anthropic ≥ 0.40`, use `AsyncAnthropic` client; chat via `client.messages.create(...)`; **no embedding path** — embedding factory raises before any SDK touch.

**Rationale**: ≥ 0.40 ships a stable async client and the modern Messages API shape. The Anthropic adapter's `embed()` method is explicitly absent; the embedding factory's role is to enforce that absence at config-resolution time so the failure mode is "container fails health" not "indexing run dies after 500 chunks".

**Alternatives considered**:
- Implementing a "fake" embedding method that always raises at call time — violates FR-003 (fail fast at config resolution).
- Falling back to OpenAI embeddings when Anthropic is picked for embeddings — silently violates operator intent; explicit configuration error is the better UX.

---

## R4. Ollama client choice

**Decision**: plain `httpx.AsyncClient` against the Ollama HTTP API (`POST /api/chat`, `POST /api/embeddings`, `GET /api/tags`). Base URL defaults to `http://ollama:11434` (the compose-internal hostname), overridable via `OLLAMA_BASE_URL`.

**Rationale**: Ollama's HTTP API is small and well-documented; a dedicated client SDK adds dependency surface for no benefit. `httpx` is already transitively present (FastAPI's testing extras pull it; the codebase already uses it in tests via `ASGITransport`).

**Alternatives considered**:
- `ollama-python` official SDK — pulls in extra deps and provides no value for three endpoints.
- `aiohttp` — fine but introduces a second async HTTP stack alongside `httpx`; not worth the cognitive overhead.

---

## R5. Default model names per provider

**Decision**:

| Role | OpenAI | Anthropic | Ollama |
|------|--------|-----------|--------|
| chat | `gpt-4o-mini` | `claude-3-5-sonnet-latest` | `llama3.1:8b` |
| embedding | `text-embedding-3-small` | *(not supported — config error)* | `nomic-embed-text` |

Per-provider overrides via env vars `LLM_MODEL` and `EMBEDDING_MODEL` (single pair; the active provider consumes them). If unset, the active provider falls back to its own default.

**Rationale**: small/mid-tier models that fit code-review prompts (15–30 k token contexts), are inexpensive on the cloud providers, and run on consumer hardware for Ollama. `text-embedding-3-small` (1536 dims) is the documented OpenAI default for ADR-004's HNSW index sizing. `nomic-embed-text` (768 dims) is the most-pulled Ollama embedding model and aligns dimensionality-wise with `bge-small`-class indexing budgets.

**Alternatives considered**:
- `gpt-4o` full / `claude-3-opus-latest` — overspec for the thesis budget; reserved for a future quality knob.
- Per-provider model env vars (`OPENAI_LLM_MODEL`, `ANTHROPIC_LLM_MODEL`, …) — adds five vars where one pair suffices since exactly one provider per role is active.
- Splitting embedding model per provider — same simplification reason.

---

## R6. Error-classification truth table

**Decision**: `classify_http_status(code: int) -> bool` (retryable flag), wrapping the rule below.

| Upstream signal | `retryable` |
|-----------------|-------------|
| `httpx.ConnectError`, `httpx.ReadTimeout`, `httpx.WriteTimeout`, `httpx.PoolTimeout` | `True` |
| HTTP 500-599 | `True` |
| HTTP 429 | `True` |
| HTTP 408 | `True` |
| HTTP 400-499 (other) | `False` |
| Vendor SDK auth error (e.g. `openai.AuthenticationError`) | `False` |
| Vendor SDK rate-limit error (e.g. `openai.RateLimitError`) | `True` |
| Unknown / unmapped exception | `False` (caller handles as terminal) |

**Rationale**: aligns with the conventional "5xx + 408 + 429 are transient" mapping; explicit-unknown-as-non-retryable prevents a buggy adapter from causing infinite retries downstream. The vendor-SDK row is implemented by mapping the SDK's typed exception classes through the same predicate.

**Alternatives considered**:
- Treating all SDK exceptions as retryable — risks runaway retry storms on permanent auth failures.
- Letting the caller decide via the raw status code — pushes vendor-specific knowledge across the abstraction boundary (violates Principle III).

---

## R7. Probe design (no API credit consumption)

**Decision**: probe semantics per provider:

| Provider | LLM probe | Embedding probe |
|----------|-----------|-----------------|
| OpenAI | `bool(api_key)` only — emit `ok` if non-empty, `unconfigured` otherwise | same |
| Anthropic | `bool(api_key)` only — emit `ok` / `unconfigured` | *factory rejects this path; if it were reached, `unconfigured` is returned* |
| Ollama | `GET {base_url}/api/tags` with 2 s timeout. 200 → `ok`. Connect/timeout/non-200 → `unreachable`. | same |

`ok` does **not** mean the upstream credential is valid (we never verify against the upstream paid endpoint); it means *we have enough configuration to attempt a call*. Real auth failures will surface on the first `/review` invocation, not during `/healthz`.

**Rationale**: probing must not cost money or rate-limit budget; FR-012. The Ollama path can afford a real reachability check because the endpoint is free and local. The "we never validate credentials in the probe" trade-off is documented up front so operators do not interpret a green badge as authoritative.

**Alternatives considered**:
- Probing OpenAI's `GET /v1/models` — costs ~ nothing, but still chargeable on some org plans, and would leak the API key onto the wire on every dashboard refresh. Rejected.
- Probing Anthropic's `GET /v1/models` — same trade-off; rejected.
- Probing Ollama with `POST /api/generate` for a one-token completion — burns local compute; rejected.

---

## R8. Lazy factory pattern

**Decision**: each factory is a module-level function wrapped with `functools.lru_cache(maxsize=1)`. The function reads the live `Settings()` at first call, performs validation, and constructs the chosen adapter (which itself does not connect to anything yet — adapters lazily instantiate their underlying SDK client on first `chat()` / `embed()` call).

```python
@lru_cache(maxsize=1)
def get_llm_provider() -> LLMProvider: ...
```

**Rationale**: matches the existing `get_settings()` pattern in `config.py` for consistency. Lazy SDK-client construction inside adapters (e.g. `AsyncOpenAI(api_key=...)` deferred to first call) guarantees that simply importing the package does no I/O — satisfies FR-005 and prevents `import codesensei.providers` from crashing on missing keys.

**Alternatives considered**:
- Module-level singletons created at import time — violates FR-005 (eager construction).
- Dependency-injection via FastAPI `Depends` — heavier; non-FastAPI callers (CLI, background workers in future) would still want a factory function, so the function shape is the right primitive.

---

## R9. Config additions

**Decision**: extend `Settings` with three optional fields:

| Field | Default | Notes |
|-------|---------|-------|
| `llm_model: str` | `""` (provider picks its default) | populated from `LLM_MODEL` env |
| `embedding_model: str` | `""` (provider picks its default) | populated from `EMBEDDING_MODEL` env |
| `ollama_base_url: str` | `http://ollama:11434` | populated from `OLLAMA_BASE_URL` env |

Add the three rows to `.env.example` under a new `# === Provider tuning (optional) ===` section. Existing keys (`LLM_PROVIDER`, `EMBEDDING_PROVIDER`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`) are reused unchanged.

**Rationale**: keeps the operator surface small (single model knob per role) while letting power users override per-provider defaults. The `ollama_base_url` field lets non-compose deployments point at a host-Ollama instance without code edits.

**Alternatives considered**:
- Per-provider model env vars — see R5 alternatives.
- A nested `providers.openai.model` YAML config — premature; CodeSensei does not have a YAML config layer yet (ADR-006 may add one later). Env-only for now.

---

## R10. Test rigging — `no_network` discipline

**Decision**: a `conftest.py` autouse fixture sets `respx.MockRouter(assert_all_called=False)` for every test in `tests/`, and a session-scoped check asserts that no test makes an unintercepted `httpx` call. SDK-level mocks (`AsyncMock` for `AsyncOpenAI` / `AsyncAnthropic`) are constructed per test via small helpers in `tests/conftest.py`.

**Rationale**: SC-004 requires the suite to pass with no outbound network access. Autouse + assertion-on-unintercepted-call makes the rule mechanical: a test that accidentally hits a real network endpoint fails loudly, not silently.

**Alternatives considered**:
- `pytest-socket` to block AF_INET globally — works but interferes with the existing `httpx.ASGITransport` in-process tests. Per-test respx is more surgical.

---

## Summary of decisions

| ID | Decision | Touchpoint |
|----|----------|------------|
| R1 | `respx` + `AsyncMock` | `tests/` |
| R2 | `openai ≥ 1.50`, `AsyncOpenAI` | `openai_adapter.py` |
| R3 | `anthropic ≥ 0.40`, `AsyncAnthropic`, no embedding | `anthropic_adapter.py`, `factory.py` |
| R4 | `httpx.AsyncClient` for Ollama, default URL `http://ollama:11434` | `ollama_adapter.py`, `probe.py` |
| R5 | Defaults: `gpt-4o-mini`, `text-embedding-3-small`, `claude-3-5-sonnet-latest`, `llama3.1:8b`, `nomic-embed-text` | adapter modules |
| R6 | `classify_http_status` truth table | `errors.py` |
| R7 | Key-presence probes for OpenAI/Anthropic; `GET /api/tags` for Ollama | `probe.py` |
| R8 | `lru_cache(maxsize=1)` module-level factories | `factory.py` |
| R9 | New env vars: `LLM_MODEL`, `EMBEDDING_MODEL`, `OLLAMA_BASE_URL` | `config.py`, `.env.example` |
| R10 | Autouse `respx` + no-network discipline | `tests/conftest.py` |

No NEEDS-CLARIFICATION items remain.
