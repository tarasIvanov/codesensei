# Contract: `backend/src/codesensei/review/pricing.py`

**Status**: NEW module, introduced by feature 012.

## Surface

```python
from typing import Final

PRICING_PER_1M: Final[dict[tuple[str, str], tuple[float, float]]] = {
    ("openai", "gpt-4o-mini"): (0.15, 0.60),
    ("openai", "gpt-4o"): (2.50, 10.00),
    ("openai", "gpt-4.1-mini"): (0.40, 1.60),
    ("anthropic", "claude-3-5-sonnet-latest"): (3.00, 15.00),
    ("anthropic", "claude-3-5-haiku-latest"): (0.80, 4.00),
}


def compute_cost_usd(
    provider: str,
    model: str | None,
    prompt_tokens: int | None,
    completion_tokens: int | None,
) -> float | None:
    """Compute the USD cost estimate for one LLM call.

    Returns None when:
      - either `prompt_tokens` or `completion_tokens` is None;
      - `(provider, model)` is not present in `PRICING_PER_1M`;
      - `model` itself is None.

    Otherwise returns a non-negative float rounded to 6 decimal places.
    """
```

## Semantics

| Input | Output |
|-------|--------|
| `("openai", "gpt-4o-mini", 1000, 500)` | `0.00045` (1000/1e6 * 0.15 + 500/1e6 * 0.60 = 0.00045, rounded to 0.000450) |
| `("openai", "unknown-model", 1000, 500)` | `None` (missing pricing pair) |
| `("openai", "gpt-4o-mini", None, 500)` | `None` (token field missing) |
| `("openai", "gpt-4o-mini", 1000, None)` | `None` (token field missing) |
| `("ollama", "llama3.1:8b", 1000, 500)` | `None` (Ollama deliberately absent from table) |
| `("openai", None, 1000, 500)` | `None` (model name unknown) |

## Invariants

- **Pure function**: no I/O, no module state mutation, no side effects.
- **Determinism**: same input always returns the same output across calls.
- **No exceptions**: an unknown pair returns `None`, never raises `KeyError`.
- **Rounding**: result rounded via `round(value, 6)` — Python's banker's rounding is acceptable for this precision.

## Maintenance policy

- Editing `PRICING_PER_1M` is a code change. Reviewed in PR, deployed via image rebuild. No DB migration is needed.
- New `(provider, model)` rows can be appended without touching tests beyond `test_review_pricing.py` (which only asserts the existing entries + lookup semantics).
- Stale rows (a model the provider deprecated) are left as-is unless they actively mislead — old reviews persisted with that model keep their frozen cost from the at-call rate, and new reviews against the deprecated model are silently absent from the lookup → `cost_usd = None`.
