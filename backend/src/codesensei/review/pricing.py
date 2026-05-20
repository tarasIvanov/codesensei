"""Per-(provider, model) price table + cost helper (feature 012)."""

from __future__ import annotations

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
    if prompt_tokens is None or completion_tokens is None or model is None:
        return None
    rates = PRICING_PER_1M.get((provider, model))
    if rates is None:
        return None
    in_price, out_price = rates
    value = (prompt_tokens / 1_000_000.0) * in_price + (completion_tokens / 1_000_000.0) * out_price
    return round(value, 6)
