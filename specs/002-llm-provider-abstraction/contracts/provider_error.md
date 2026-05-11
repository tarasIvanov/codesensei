# Contract: `ProviderError`

Single normalized exception type for every failure surfaced by any provider adapter. All callers MUST handle exactly this one type.

---

## Shape

```text
class ProviderError(Exception):
    def __init__(
        self,
        provider: str,
        message: str,
        *,
        retryable: bool,
    ) -> None: ...

    provider: str   # "openai" | "anthropic" | "ollama" | "config"
    message: str    # upstream-supplied human-readable detail, safe for logs
    retryable: bool # per the truth table below
```

`str(exc)` MUST yield `f"{exc.provider}: {exc.message}"` for compact log output.

---

## Classification — `retryable` truth table

| Upstream signal | `retryable` | Notes |
|-----------------|-------------|-------|
| `httpx.ConnectError` | `True` | network reachability glitch |
| `httpx.ReadTimeout`, `WriteTimeout`, `PoolTimeout` | `True` | transient |
| HTTP 500–599 | `True` | upstream defect, expected to recover |
| HTTP 429 | `True` | rate limit — retry after backoff |
| HTTP 408 | `True` | request timeout |
| HTTP 400–499 (other) | `False` | client error — fix the request, do not retry |
| `openai.AuthenticationError`, `anthropic.AuthenticationError` | `False` | credentials problem |
| `openai.RateLimitError`, `anthropic.RateLimitError` | `True` | per SDK semantics |
| Configuration error (e.g. Anthropic+embeddings) | `False` | uses `provider="config"` |
| Any other vendor SDK exception | `False` | unknown-as-terminal prevents retry storms |

---

## Identity of the `provider` field

| Source | `provider` value |
|--------|-------------------|
| OpenAI adapter | `"openai"` |
| Anthropic adapter | `"anthropic"` |
| Ollama adapter | `"ollama"` |
| Factory / config validation | `"config"` |

The string `"config"` is used for misconfiguration errors so that callers can distinguish "the SDK said no" from "the operator said something invalid". The future `/review` endpoint uses this distinction to choose its HTTP status:

- `provider == "config"` → HTTP 500 (operator must fix env)
- `retryable == True` → HTTP 503 (transient upstream issue)
- `retryable == False`, `provider != "config"` → HTTP 502 (terminal upstream issue)

These status-code rules are documented for the 003 consumer; this feature only ships the exception shape.

---

## Boundary rule

Vendor SDK exception types MUST NOT be raised out of any adapter module. The `try ... except` blocks inside adapter methods catch the SDK-typed exceptions (or `httpx.HTTPError` subclasses for Ollama) and translate them. The translator helper `classify_http_status(code: int) -> bool` lives in `errors.py` and is the single source of truth for retryability.

A test in `tests/unit/test_provider_errors.py` MUST assert the full truth table above.
