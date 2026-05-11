# Contract: `EmbeddingProvider`

In-process interface that every embedding adapter MUST satisfy. Anthropic deliberately has no implementation — the factory rejects `EMBEDDING_PROVIDER=anthropic` before construction.

---

## Surface

```text
class EmbeddingProvider(Protocol):
    name: str  # "openai" | "ollama"

    async def embed(
        self,
        texts: list[str],
        *,
        model: str | None = None,
    ) -> list[list[float]]: ...
```

## Inputs

| Param | Required | Notes |
|-------|----------|-------|
| `texts` | yes | non-empty list of non-empty strings. Adapter MUST raise `ProviderError(retryable=False, message="empty input")` if the list is empty or any element is the empty string. |
| `model` | no | overrides default (`text-embedding-3-small` / `nomic-embed-text`). When `None`, adapter uses `EMBEDDING_MODEL` env var if set, else its compiled-in default. |

## Output

| Case | Return value |
|------|--------------|
| success | `list[list[float]]` — one vector per input text, same order; all vectors have identical dimensionality |
| failure | **raises** `ProviderError(...)` |

Dimensionality contract: the adapter is responsible for the dimensionality of its chosen model (OpenAI `text-embedding-3-small` → 1536; Ollama `nomic-embed-text` → 768). Caller code MUST NOT assume a fixed dimensionality across providers; the future indexing layer (003) will pin a single provider per deployment.

## Error contract

Same `ProviderError` shape and classification as `llm_provider.md`. Adapter-specific notes:

- OpenAI: per-call timeout failures map to `retryable=True`; auth failures to `retryable=False`.
- Ollama: connection errors / 5xx → `retryable=True`; 4xx → `retryable=False`.

## Factory rejection of Anthropic

Calling `get_embedding_provider()` with `EMBEDDING_PROVIDER=anthropic` raises a configuration error **before** any adapter construction. The error message MUST:

1. Name the offending env var (`EMBEDDING_PROVIDER`).
2. Name the unsupported value (`anthropic`).
3. List the accepted values (`openai`, `ollama`).
4. Be raised as `ProviderError(provider="config", retryable=False, message=...)` so structured logs see a uniform type.

There is no `AnthropicEmbeddingProvider` class — even an always-raising stub would weaken the fail-fast guarantee by allowing factory resolution to succeed.

## Implementations covered in this feature

| Implementation | Path | Notes |
|----------------|------|-------|
| `OpenAIEmbeddingProvider` | `backend/src/codesensei/providers/openai_adapter.py` | uses `AsyncOpenAI.embeddings.create` |
| `OllamaEmbeddingProvider` | `backend/src/codesensei/providers/ollama_adapter.py` | uses `httpx.AsyncClient` against `POST {OLLAMA_BASE_URL}/api/embeddings` |
