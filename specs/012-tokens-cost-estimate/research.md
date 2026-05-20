# Phase 0 Research: Token usage + cost estimate per review

**Feature**: 012-tokens-cost-estimate
**Date**: 2026-05-21

This document resolves all open decisions implied by the spec. No `[NEEDS CLARIFICATION]` markers remain in spec.md, so research consolidates the implementation-level choices that downstream tasks will execute.

---

## Decision 1: Where does usage data come from in each provider SDK?

**Decision**:

- **OpenAI** (`openai >= 1.50`): `response.usage.prompt_tokens` (int) and `response.usage.completion_tokens` (int). Always populated on a successful `chat.completions.create(stream=False)` call. The `model` field on the response echoes back the resolved model name (incl. version suffix).
- **Anthropic** (`anthropic >= 0.40`): `response.usage.input_tokens` and `response.usage.output_tokens`. Always populated on a successful non-streamed `messages.create`. The Anthropic API naming differs from OpenAI; the adapter normalises to `prompt_tokens` / `completion_tokens` at the boundary.
- **Ollama** (REST `/api/chat`): the non-streamed JSON response includes `prompt_eval_count` and `eval_count`. Both fields are best-effort — some local model builds omit them, in which case the adapter leaves `_last_usage` as the constructor default (None).

**Rationale**: all three providers already return usage on the same response object that the adapter inspects to extract the message text. Reading two more keys adds zero round-trips and zero new dependencies.

**Alternatives considered**:

- **Counting tokens locally via tiktoken**: rejected. tiktoken's vocabularies are OpenAI-specific (and outdated for newer SDKs); Anthropic uses a separate tokenizer; Ollama models vary widely. Provider-reported counts are authoritative for billing.
- **Sending a separate `/usage` request after the chat call**: rejected. Doubles the latency and rate-limit footprint of every review.
- **Streaming with `stream_options.include_usage=True`**: rejected. CodeSensei intentionally avoids streaming (incompatible with the structured JSON contract per `_mvp_scope.md §4`).

---

## Decision 2: How does the service layer obtain usage without changing the `LLMProvider` Protocol?

**Decision**: Each concrete adapter class declares `self._last_usage: ChatUsage | None = None` in `__init__` and updates it immediately after a successful API call. The `review/service.py:_run_chat` reads it via `getattr(provider, "_last_usage", None)`. The `LLMProvider` Protocol in `providers/base.py` stays untouched (still only `name: str` + `async def chat(...) -> str`).

**Rationale**:

- Constitution Principle III bans direct SDK leakage into call sites. Keeping the Protocol surface stable means the new usage path is purely an adapter-implementation detail that consumers opt-in to via duck typing.
- Existing unit tests for adapters (`test_openai_adapter.py` etc.) mock `chat()` returning `str`; they continue to pass because they do not interact with `_last_usage`.
- Existing service-level fakes (`tests/unit/test_review_service.py`, `tests/integration/test_review_endpoint.py`, etc.) implement `async def chat(...)` without `_last_usage`; `getattr` falls back to `None` and the service path renders "tokens N/A".
- Each chat-provider instance is constructed per request (factory style — see `providers/factory.py`), so the mutable state on `_last_usage` does not race across reviews.

**Alternatives considered**:

- **Change `chat()` return type to `ChatResponse(text, usage)`**: rejected. Touches 10+ test sites for marginal API ergonomics, and the new return type would be a breaking change to ADR-003's adapter contract — gratuitous Principle II hard trigger.
- **Pass an out-param `usage_buf: list`** to `chat()`: rejected. Awkward, hides intent, and still requires a Protocol change.
- **Use a `ContextVar` to thread usage out-of-band**: rejected. Same complexity as the attribute approach without the locality benefit; ContextVars also bleed across `asyncio.gather` calls in subtle ways.

---

## Decision 3: Pricing table — where lives it, how is it sourced, how is it maintained?

**Decision**:

- **Location**: `backend/src/codesensei/review/pricing.py`. Pure Python module, no I/O, no DB.
- **Shape**: `PRICING_PER_1M: dict[tuple[str, str], tuple[float, float]]` keyed by `(provider, model)` → `(in_price, out_price)`. Both prices are USD per 1 000 000 tokens (the unit OpenAI / Anthropic publish in).
- **Initial entries** (sourced from public list prices as of 2026-05-21):
  ```python
  PRICING_PER_1M = {
      ("openai", "gpt-4o-mini"): (0.15, 0.60),
      ("openai", "gpt-4o"): (2.50, 10.00),
      ("openai", "gpt-4.1-mini"): (0.40, 1.60),
      ("anthropic", "claude-3-5-sonnet-latest"): (3.00, 15.00),
      ("anthropic", "claude-3-5-haiku-latest"): (0.80, 4.00),
  }
  ```
- **Helper**: `compute_cost_usd(provider: str, model: str | None, prompt_tokens: int | None, completion_tokens: int | None) -> float | None`. Returns None when the pair is missing OR when either token field is None. Result is rounded to 6 decimal places.
- **Maintenance**: editing the constant + rebuilding the api image. No env-var override, no admin UI, no DB row. Operators who care can fork the file.

**Rationale**:

- The pricing table is small (≤ 20 rows for the foreseeable scope), changes ≤ once per quarter, and never needs to differ across deploys of CodeSensei. A code-internal const is the lowest-friction shape for this profile.
- Storing prices on disk (e.g. `app_settings`) would invite the question "do persisted reviews use the active pricing or the at-call pricing?" — keeping pricing in code makes the answer obvious: cost is computed at call time, the stored number is frozen.
- The spec (FR-005) explicitly mandates that unknown pairs return `null`, distinguishing them from `0`. This is naturally expressed as a dict-lookup miss.

**Alternatives considered**:

- **`app_settings` row keyed by `(provider, model)`**: rejected. Adds an admin path for a value that maintainers want to grep, not click.
- **Env-var-driven (`PRICING_JSON`)**: rejected. Fiddly to author at the shell, fragile to typos, no advantage over a Python module.
- **Pull live pricing from OpenRouter / provider APIs**: rejected. Out of scope, network dependency, doesn't actually exist for Anthropic.

---

## Decision 4: Database storage shape

**Decision**:

- Three nullable columns on `review_runs`:
  - `prompt_tokens INTEGER NULL`
  - `completion_tokens INTEGER NULL`
  - `cost_usd NUMERIC(10, 6) NULL`
- Single alembic revision `005_review_run_tokens.py` with `down_revision = "004_review_history"`. Body: three `op.add_column` calls. No data migration.
- Pre-existing rows keep NULL on all three columns; the frontend degrades to "tokens N/A" for them (FR-010).

**Rationale**:

- `INTEGER` (32-bit signed) easily accommodates any plausible review token count: GPT-4o context window is 128k; even a 4× hypothetical bump fits comfortably under `INT_MAX`.
- `NUMERIC(10, 6)` allows up to 9 999.999999 USD — orders of magnitude above any single-call cost (a saturated GPT-4o request at $10/1M output, 16k completion tokens = $0.16). The precision (6 dp) matches the spec's persistence policy (FR-006).
- A separate `review_findings_tokens` sub-table would be overkill — the granularity is per-run, not per-finding, and we never query "show me runs over X tokens" in the UI.

**Alternatives considered**:

- **`DECIMAL(8, 4)`**: insufficient precision at the bottom end (a $0.0001-class call rounds to zero), and the ceiling is too low for an unusually-large GPT-4o run.
- **Storing cost as cents (`INTEGER`, "1234 = $0.001234")**: rejected. Awkward, no win over NUMERIC, and breaks the "render at 4dp" contract because of the integer-vs-decimal conversion ceremony.

---

## Decision 5: Frontend rendering shape

**Decision**:

- A pure helper `formatTokenLine(result: { prompt_tokens: number | null; completion_tokens: number | null; cost_usd: number | null }) → string` lives at the top of each page that uses it (or co-located in `api/review.ts` if duplication is undesirable). The helper returns one of:
  - `null` (render no line) — when both tokens AND cost are null AND the run pre-dates the migration (the page can choose not to render the row at all for older rows).
  - `"tokens N/A"` — when tokens are null but the run is fresh (rendered to confirm the new field is wired, not silently hidden).
  - `"1234 in / 567 out tokens"` — when tokens are present but cost is null (unknown pricing pair).
  - `"1234 in / 567 out tokens · ~$0.0023"` — when both are present.
- Rendered as a `<span class="text-xs font-mono" :style="{ color: 'var(--color-text-muted)' }">` directly under the existing provider/elapsed line on `/review` and `/history/<id>`.
- Cost figure formats via `cost.toFixed(4)` (matches FR-006's 4dp UI policy). The tilde prefix (`~`) marks it as an estimate (FR-012).

**Rationale**:

- Co-locating the helper avoids creating a "utility module" footprint for a one-liner. Both pages render the same content, so the helper signature is stable.
- Using `var(--color-text-muted)` matches the existing styling of the provider/elapsed line — operators see one continuous "metadata about the call" block.

**Alternatives considered**:

- **Render as a `<table>` or definition list**: rejected. Single line is already terse enough; a table is over-styled for two numbers.
- **Live currency conversion via the browser's `Intl.NumberFormat`**: rejected. No multi-currency support is in scope; hardcoded `$` keeps the implementation trivial and matches the spec's USD-only assumption.

---

## Decision: ADR-015 contents (drafted at the implementation gate)

The ADR that MUST be written before any production code lands. Drafted here so `tasks.md` can reference it as T002; the actual prose lives in `_decision_log.md` as a NEW entry.

```
### ADR-015: Persist token usage + cost estimate on review_runs
- Date: 2026-05-21
- Status: accepted
- Decision: Each successful POST /api/review run carries three new optional
  fields — prompt_tokens, completion_tokens, cost_usd — both on the wire
  (ReviewResult) and on the persisted review_runs row (3 nullable columns
  added in alembic revision 005_review_run_tokens.py, down_revision=004).
  Cost is derived in-process by review/pricing.py from a code-internal
  PRICING_PER_1M[(provider, model)] dict (USD per 1M tokens, split in/out)
  sourced from public OpenAI / Anthropic per-1M-token list prices as of
  2026-05-21. Provider adapters surface usage via a per-instance
  _last_usage: ChatUsage | None attribute that the service layer reads via
  getattr; the public LLMProvider Protocol surface is unchanged. Cost is
  stored at 6 dp on disk (NUMERIC(10, 6)) and rendered at 4 dp on the UI
  (~$0.0023). Pre-feature rows keep NULL columns; no backfill is performed.
- Why: Closes the last UI gap from _mvp_scope.md §2.5 ("Token count + cost
  estimate у звіті"). Without it, the supervisor's "how do you trace cost
  per review?" question has no demonstrable answer in the SPA. The
  approach reuses the existing review_runs surface (one migration only,
  no new tables, no new compose service, no new env var). The "pricing in
  source control" decision is deliberate: it makes the rate visible at
  audit time (grep), changes flow through PRs (review trail), and avoids
  the ambiguity of "did this row use the active or the at-call pricing?"
  by freezing the cost at insert time.
- Notes: NFR-3.1 confirmation — tokens and cost are NOT credentials. No
  external pricing service is contacted. The cost field is explicitly
  marked as an estimate (FR-012, ~$ prefix in UI). Pricing-table
  maintenance is documented in research.md §Decision 3 (edit
  pricing.py + rebuild). Ollama tokens remain best-effort: when the
  /api/chat response carries prompt_eval_count + eval_count, they are
  surfaced; otherwise tokens stay null. Cost rounding boundary policy:
  any value below $0.000001 stores as 0.000000 and renders as ~$0.0000
  — acceptable for the thesis demo, aggregate accounting is out of scope.
  Supersedes nothing.
```

---

## Open clarifications

None. All spec-driven decisions are resolved; no `[NEEDS CLARIFICATION]` markers remained after spec.md.
