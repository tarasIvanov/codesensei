# Phase 1 — Data Model: Provider Abstraction

No persisted entities — the feature is stateless. The "data model" captured here is the **in-process type contract** between adapter callers, the factory, the probe layer, and the `/healthz` envelope.

---

## Entities

### `ChatMessage` (TypedDict)

| Field | Type | Notes |
|-------|------|-------|
| `role` | `Literal["system", "user", "assistant"]` | mirrors the lowest-common-denominator across the three SDKs |
| `content` | `str` | plain text; image / tool parts are deferred |

A list of `ChatMessage` is the input to every `LLMProvider.chat(...)` call.

### `LLMProvider` (Protocol)

| Member | Signature | Behavior |
|--------|-----------|----------|
| `name` | `str` (class attribute) | one of `"openai"`, `"anthropic"`, `"ollama"` |
| `chat` | `async def chat(messages: list[ChatMessage], *, model: str \| None = None, max_tokens: int = 1024, temperature: float = 0.2) -> str` | returns the full completion text. Raises `ProviderError`. |

### `EmbeddingProvider` (Protocol)

| Member | Signature | Behavior |
|--------|-----------|----------|
| `name` | `str` (class attribute) | one of `"openai"`, `"ollama"` |
| `embed` | `async def embed(texts: list[str], *, model: str \| None = None) -> list[list[float]]` | returns one vector per input text. Raises `ProviderError`. |

### `ProviderError` (Exception)

| Field | Type | Notes |
|-------|------|-------|
| `provider` | `str` | name of the originating adapter |
| `message` | `str` | upstream-supplied human-readable detail; safe for server-side logs; never echoed to `/healthz` |
| `retryable` | `bool` | per the classification table in `research.md > R6` |

Inheritance: extends `Exception`. Constructor signature `ProviderError(provider, message, *, retryable)`.

### `ProviderState` (Enum)

| Variant | String value | Meaning |
|---------|--------------|---------|
| `OK` | `"ok"` | configuration present; for Ollama, `GET /api/tags` succeeded |
| `UNCONFIGURED` | `"unconfigured"` | required env var (API key / URL) missing or empty |
| `UNREACHABLE` | `"unreachable"` | Ollama-only — configured but `GET /api/tags` failed or timed out |

The string values appear verbatim in the `/healthz` envelope and in the Vue badge text.

### `ProviderProbeResult` (frozen dataclass)

| Field | Type | Notes |
|-------|------|-------|
| `state` | `ProviderState` | the resolved state |
| `provider` | `str \| None` | which provider was probed (e.g. `"openai"`); `None` if no provider configured at all |

### `HealthzEnvelope` (extension)

The existing envelope from 001 (`status`, `db`, `redis`, `extensions.vector`, optional `failing`) gains one new field:

```text
providers:
  llm: "ok" | "unconfigured" | "unreachable"
  embedding: "ok" | "unconfigured" | "unreachable"
```

`status` (overall) is **not** affected by provider states (FR-013). `failing[]` is **not** extended with provider names — provider readiness is informational.

---

## Relationships

```text
get_llm_provider()  ──returns──▶  LLMProvider (concrete adapter)
get_embedding_provider()  ──returns──▶  EmbeddingProvider (concrete adapter)

adapter.chat() / adapter.embed()  ──raises──▶  ProviderError

probe_llm_provider()  ──returns──▶  ProviderProbeResult
probe_embedding_provider()  ──returns──▶  ProviderProbeResult

healthcheck.build_envelope(..., llm_probe, embedding_probe)
  ──reads──▶  ProviderProbeResult.state
  ──writes──▶  envelope.providers.{llm, embedding}
```

---

## Validation rules (factory-side)

| Rule | Source | Action on violation |
|------|--------|---------------------|
| `LLM_PROVIDER ∈ {openai, anthropic, ollama}` (lowercase, trimmed) | FR-001 | raise `ProviderError(provider="config", retryable=False, message="…accepted: openai, anthropic, ollama")` |
| `EMBEDDING_PROVIDER ∈ {openai, ollama}` | FR-002, FR-003 | raise `ProviderError(provider="config", retryable=False, message="…accepted: openai, ollama")`. The error message MUST call out `EMBEDDING_PROVIDER=anthropic` explicitly when that is the supplied value. |
| Factory must not access network on resolution | FR-005 | enforced via test: monkeypatch `httpx.AsyncClient.__init__` to raise; importing + resolving must not call it |

---

## State transitions

The `ProviderState` enum is point-in-time per `/healthz` call. There is no persisted state machine; each call to `probe_llm_provider()` / `probe_embedding_provider()` recomputes the state from current config and (for Ollama) live reachability. Successive calls may legitimately move `unreachable ↔ ok` as the Ollama container restarts.
