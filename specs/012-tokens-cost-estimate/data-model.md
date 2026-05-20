# Data Model: Token usage + cost estimate per review

**Feature**: 012-tokens-cost-estimate
**Date**: 2026-05-21

This document defines the persistent + in-memory entities introduced or extended by feature 012. All shape decisions are derived from spec.md and research.md.

---

## Entity 1 — `ChatUsage` (in-memory dataclass)

Carries token usage from one LLM call, set on the adapter instance after a successful chat round-trip.

**Location**: `backend/src/codesensei/providers/base.py`

**Shape** (frozen dataclass):

| Field | Type | Nullable | Notes |
|-------|------|----------|-------|
| `prompt_tokens` | `int` | yes | Provider-reported input tokens. None when the provider does not surface usage. |
| `completion_tokens` | `int` | yes | Provider-reported output tokens. Same null semantics. |
| `model` | `str` | yes | Resolved model name as the provider echoed it back (e.g. `gpt-4o-mini-2024-07-18`). Used by the service layer to look up pricing. |

**Lifecycle**: per-instance attribute `_last_usage` on each concrete adapter (`OpenAIChatProvider`, `AnthropicChatProvider`, `OllamaChatProvider`). Initialised to `None` in `__init__`; replaced with a populated `ChatUsage` after each successful `chat()` call; cleared back to `None` only if the next call raises (the service reads it immediately after `await`, so racing is impossible inside the per-request scope).

**Invariants**:

- `prompt_tokens >= 0` when not None.
- `completion_tokens >= 0` when not None.
- Either both token fields are non-None or both are None (a provider that reports one half but not the other is treated as "no usage" — the adapter sets `_last_usage = None`).

---

## Entity 2 — `PricingEntry` (code-internal dict value)

A single row of the in-process pricing table.

**Location**: `backend/src/codesensei/review/pricing.py`

**Shape**: `tuple[float, float]` = `(input_price_per_1m_usd, output_price_per_1m_usd)`.

**Key**: `tuple[str, str]` = `(provider, model)`. The `provider` matches `LLMProvider.name` (`"openai"`, `"anthropic"`, `"ollama"`); the `model` is the exact resolved model name returned by the provider (post any `_VERSION` aliasing).

**Validation rules**:

- `input_price_per_1m_usd >= 0`, `output_price_per_1m_usd >= 0`.
- Missing keys deliberately do NOT raise — the lookup returns `None` so the caller can render "unknown cost" gracefully.

**Initial population** (as of 2026-05-21):

| Provider | Model | Input ($/1M) | Output ($/1M) |
|----------|-------|-------------:|--------------:|
| openai | gpt-4o-mini | 0.15 | 0.60 |
| openai | gpt-4o | 2.50 | 10.00 |
| openai | gpt-4.1-mini | 0.40 | 1.60 |
| anthropic | claude-3-5-sonnet-latest | 3.00 | 15.00 |
| anthropic | claude-3-5-haiku-latest | 0.80 | 4.00 |

Ollama is intentionally absent — local inference has no per-token cost.

---

## Entity 3 — `ReviewResult` (extended pydantic model)

Wire shape of `POST /api/review` and `GET /api/reviews/{id}`.

**Location**: `backend/src/codesensei/review/schema.py`

**Existing fields** (unchanged):

| Field | Type | Notes |
|-------|------|-------|
| `verdict` | `"approve" \| "request_changes" \| "comment"` | |
| `findings` | `list[Finding]` | |
| `provider` | `str` | LLM provider name. |
| `elapsed_ms` | `int` | Wall-clock for the chat call. |
| `context_files` | `list[str] \| None` | RAG context files surfaced to the LLM. |

**New fields** (all optional, default `None` — additive on the wire):

| Field | Type | Notes |
|-------|------|-------|
| `prompt_tokens` | `int \| None` | Provider-reported input tokens; null when provider does not surface usage or call failed. |
| `completion_tokens` | `int \| None` | Provider-reported output tokens; same null semantics. |
| `cost_usd` | `float \| None` | Derived from pricing table; null when tokens are null OR `(provider, model)` is missing from `PRICING_PER_1M`. Rounded to 6 dp at insertion. |

**Validation rules** (enforced via pydantic field defaults — no custom validators needed):

- All three new fields default to `None`. Setting `prompt_tokens` to `0` is permitted (Ollama might literally return zero for an unusual short-circuit).
- `cost_usd >= 0` when not None.

---

## Entity 4 — `review_runs` row (extended Postgres table)

Persistent shape of each historical review. Existing columns (from ADR-013 / feature 009) are unchanged.

**New columns** (alembic revision `005_review_run_tokens.py`):

| Column | SQL type | Null? | Notes |
|--------|----------|-------|-------|
| `prompt_tokens` | `INTEGER` | YES | Mirrors `ReviewResult.prompt_tokens`. |
| `completion_tokens` | `INTEGER` | YES | Mirrors `ReviewResult.completion_tokens`. |
| `cost_usd` | `NUMERIC(10, 6)` | YES | Stores cost in USD with 6 dp precision (max value 9 999.999999 — orders of magnitude beyond any single review cost). |

**Migration policy**:

- Three `op.add_column` calls. Each new column is `nullable=True`. No backfill — pre-existing rows keep `NULL` and the UI degrades gracefully.
- Downgrade: three `op.drop_column` calls in reverse order.
- No new index — the new columns are not used for filtering or sorting in v1.

**ORM mirror**: `reviews_history/models.py:ReviewRun` gains three `Mapped[int | None]` / `Mapped[Decimal | None]` columns matching the migration.

---

## Entity 5 — `ReviewRunSummary` + `ReviewRunDetail` (extended pydantic models)

Wire shape of `GET /api/reviews` (list) and `GET /api/reviews/{id}` (detail).

**Location**: `backend/src/codesensei/reviews_history/schema.py`

Both models gain the same three optional fields (`prompt_tokens`, `completion_tokens`, `cost_usd`) so the list view can optionally render a token total in a future iteration (out of scope here — but adding to the summary now avoids a second migration later).

---

## State transitions

Not applicable — there are no entities with multi-step state. Token/cost data is set exactly once on insertion and never mutated thereafter (per the spec assumption: "the recorded cost reflects the rate that was in effect at the time of the call").
