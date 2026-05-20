"""Unit tests for review/pricing.py (feature 012)."""

from __future__ import annotations

import pytest

from codesensei.review import pricing
from codesensei.review.pricing import PRICING_PER_1M, compute_cost_usd


def test_known_openai_pair_exact_math():
    # gpt-4o-mini → (0.15, 0.60) USD per 1M
    # 1000 in / 500 out → 1000/1e6 * 0.15 + 500/1e6 * 0.60 = 0.000150 + 0.000300 = 0.000450
    cost = compute_cost_usd("openai", "gpt-4o-mini", 1000, 500)
    assert cost == pytest.approx(0.000450, abs=1e-9)


def test_known_anthropic_pair_exact_math():
    # claude-3-5-sonnet-latest → (3.00, 15.00) USD per 1M
    cost = compute_cost_usd("anthropic", "claude-3-5-sonnet-latest", 2000, 1000)
    expected = 2000 / 1_000_000 * 3.00 + 1000 / 1_000_000 * 15.00
    assert cost == pytest.approx(round(expected, 6), abs=1e-9)


def test_unknown_pair_returns_none():
    assert compute_cost_usd("openai", "some-future-model", 1000, 500) is None


def test_ollama_pair_returns_none_by_design():
    # Ollama deliberately absent from PRICING_PER_1M (local inference has no per-token cost).
    assert ("ollama", "llama3.1:8b") not in PRICING_PER_1M
    assert compute_cost_usd("ollama", "llama3.1:8b", 1000, 500) is None


def test_either_token_none_returns_none():
    assert compute_cost_usd("openai", "gpt-4o-mini", None, 500) is None
    assert compute_cost_usd("openai", "gpt-4o-mini", 1000, None) is None


def test_model_none_returns_none():
    assert compute_cost_usd("openai", None, 1000, 500) is None


def test_zero_tokens_returns_zero():
    assert compute_cost_usd("openai", "gpt-4o-mini", 0, 0) == 0.0


def test_rounding_at_six_dp_boundary():
    # 1 input + 1 output @ gpt-4o-mini → 0.00000015 + 0.0000006 = 0.00000075
    # round(value, 6) → 0.000001 (banker's rounding)
    cost = compute_cost_usd("openai", "gpt-4o-mini", 1, 1)
    assert cost is not None
    assert cost == round(cost, 6)


def test_module_has_five_initial_entries():
    expected_keys = {
        ("openai", "gpt-4o-mini"),
        ("openai", "gpt-4o"),
        ("openai", "gpt-4.1-mini"),
        ("anthropic", "claude-3-5-sonnet-latest"),
        ("anthropic", "claude-3-5-haiku-latest"),
    }
    assert expected_keys.issubset(set(PRICING_PER_1M.keys()))


def test_pure_function_no_side_effects():
    """Running compute twice returns identical results; module state unchanged."""
    a = compute_cost_usd("openai", "gpt-4o", 100, 50)
    b = compute_cost_usd("openai", "gpt-4o", 100, 50)
    assert a == b
    assert pricing.PRICING_PER_1M is PRICING_PER_1M
