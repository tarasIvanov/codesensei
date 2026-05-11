# Contract: `LLMProvider`

In-process interface that every chat-completion adapter MUST satisfy. Implemented as a `typing.Protocol` so adapters can be duck-typed without inheritance.

---

## Surface

```text
class LLMProvider(Protocol):
    name: str  # "openai" | "anthropic" | "ollama"

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.2,
    ) -> str: ...
```

`ChatMessage` is a `TypedDict` with fields `role: Literal["system","user","assistant"]` and `content: str`.

---

## Inputs

| Param | Required | Notes |
|-------|----------|-------|
| `messages` | yes | non-empty list. The adapter MUST accept at least one `system` message followed by one or more `user`/`assistant` messages. Order is preserved. |
| `model` | no | overrides the adapter's default (`gpt-4o-mini` / `claude-3-5-sonnet-latest` / `llama3.1:8b`). When `None`, the adapter uses the env-driven `LLM_MODEL` if set, else its compiled-in default. |
| `max_tokens` | no | upper bound on completion length. Adapter MUST forward to the upstream control (`max_tokens` for OpenAI/Anthropic, `options.num_predict` for Ollama). |
| `temperature` | no | forwarded verbatim. |

## Output

| Case | Return value |
|------|--------------|
| upstream success | the assistant's full completion text as `str` |
| upstream failure | **raises** `ProviderError(provider=self.name, message=<upstream detail>, retryable=<per R6>)` |

The adapter MUST NOT return the upstream raw response object. It MUST NOT return an empty string on success — if the upstream returns no content, the adapter MUST raise `ProviderError(retryable=False, message="empty completion")`.

## Error contract

| Condition | Surfaced as |
|-----------|-------------|
| HTTP 5xx, 408, 429 | `ProviderError(retryable=True)` |
| HTTP other 4xx | `ProviderError(retryable=False)` |
| Connection error / timeout | `ProviderError(retryable=True)` |
| Auth failure (SDK-typed) | `ProviderError(retryable=False)` |
| Rate-limit (SDK-typed) | `ProviderError(retryable=True)` |
| Vendor SDK exception not classified above | `ProviderError(retryable=False)` — adapter MUST NOT let raw SDK exception types escape |

## Concurrency

Adapter instances are safe to share across coroutines (they are typically thin wrappers over an underlying SDK async client that is itself concurrency-safe). Per-call I/O is fully `async`.

## Implementations covered in this feature

| Implementation | Path | Notes |
|----------------|------|-------|
| `OpenAIChatProvider` | `backend/src/codesensei/providers/openai_adapter.py` | uses `AsyncOpenAI` |
| `AnthropicChatProvider` | `backend/src/codesensei/providers/anthropic_adapter.py` | uses `AsyncAnthropic`; messages-API shape |
| `OllamaChatProvider` | `backend/src/codesensei/providers/ollama_adapter.py` | uses `httpx.AsyncClient` against `POST {OLLAMA_BASE_URL}/api/chat` |
