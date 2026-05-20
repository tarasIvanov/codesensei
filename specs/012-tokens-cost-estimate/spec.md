# Feature Specification: Token usage + cost estimate per review

**Feature Branch**: `012-tokens-cost`
**Created**: 2026-05-21
**Status**: Draft
**Input**: User description (paraphrased): "Close the last UI gap from `_mvp_scope.md §2.5` — every successful review should surface how many tokens the LLM ate and how much that cost, both live on `/review` and replayed from `/history/<id>`. No aggregate widgets, no budget caps; just one extra muted line per review."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - See token usage and cost on every fresh review (Priority: P1)

A developer running a code review on `/review` wants to know, at a glance, how many tokens the LLM consumed and approximately how much that single call cost. Today the result card shows only the provider name and elapsed milliseconds — they have to leave the page (open the provider dashboard, do arithmetic) to audit spend.

**Why this priority**: This is the MVP-scope item the supervisor will ask about during defence ("how do you trace cost per review?"). Without it, the §2.5 line "Token count + cost estimate у звіті" stays open and the demo loses an auditability talking point. Every other story below is a follow-on of this same line.

**Independent Test**: Run a review against a known PR using an OpenAI key. The result card MUST show two lines:
1. `provider openai · 1832 ms` (existing).
2. `1234 in / 567 out tokens · ~$0.0023` (new).

The numbers must match what the OpenAI usage dashboard would show for the same call (±0 tokens — usage is exact, not estimated).

**Acceptance Scenarios**:

1. **Given** an OpenAI-backed review just completed, **When** the result card renders, **Then** prompt tokens, completion tokens, and a dollar estimate are visible inline.
2. **Given** an Anthropic-backed review just completed, **When** the result card renders, **Then** the same line appears with Anthropic-specific token names mapped onto the same `in / out` labels and the matching cost estimate.
3. **Given** an Ollama-backed review (the local provider returns no usage information), **When** the result card renders, **Then** the new line gracefully shows `tokens N/A` without crashing or showing `null / null`.

---

### User Story 2 - Re-open a historical review with the same token line (Priority: P1)

A developer revisits a past review at `/history/<id>` to remind themselves of a verdict. They expect the same token-and-cost line they saw on `/review` the first time — without spending another LLM call.

**Why this priority**: History persistence is the existing differentiator from feature 009. If new token/cost data is wire-only and not persisted, the history detail view becomes inconsistent with the live view, which would be a visible defect on the demo. This story is bundled at P1 to keep both surfaces in lock-step.

**Independent Test**: Persist a fresh review (US1 already covers the live path). Open the same run from `/history/<id>` — the result card MUST render the identical `prompt in / completion out · ~$cost` line, identical to the live view, with no re-call to the LLM provider.

**Acceptance Scenarios**:

1. **Given** a review run that already persisted token/cost data, **When** the user opens `/history/<id>`, **Then** the run detail shows the same token line as the live page did.
2. **Given** a review run that was persisted BEFORE this feature shipped (no token data on disk), **When** the user opens its detail view, **Then** the run still loads and shows `tokens N/A` instead of throwing.
3. **Given** a review run with non-null tokens but null cost (pricing entry missing for that model), **When** the user opens its detail view, **Then** the page shows the token count without a dollar estimate.

---

### User Story 3 - Operator updates the pricing table (Priority: P3)

An operator notices that OpenAI dropped the price of `gpt-4o-mini` by 20% on their public pricing page. They want to bump the local pricing constant so future reviews show the correct estimate.

**Why this priority**: This is a maintenance flow, not a primary user journey, but it must be discoverable so the cost estimate stays honest over time. P3 because every developer-operator hits this rarely (≤ once per quarter) and the work is trivial.

**Independent Test**: Locate the pricing table inside the code, edit the OpenAI `gpt-4o-mini` row, rebuild the API image, fire a fresh review — the new cost figure reflects the updated rate.

**Acceptance Scenarios**:

1. **Given** the pricing table is a single code-internal constant (no DB, no env var, no admin UI), **When** an operator edits the constant and redeploys, **Then** subsequent reviews use the new rate without further migration.
2. **Given** an operator adds a brand-new `(provider, model)` row to the constant, **When** a review uses that model, **Then** its cost figure renders without code changes elsewhere.

---

### Edge Cases

- **Provider doesn't return usage**: Ollama in some modes, and any future adapter that doesn't surface counts. Result: tokens are `null`, cost is `null`, UI shows `tokens N/A` — never `0 in / 0 out`.
- **Unknown (provider, model) pair**: cost lookup returns `null` even though tokens are non-null. UI shows the token counts without a cost figure.
- **LLM call fails mid-flight**: no `ReviewResult` is returned at all; the new fields never enter the persistence path. Existing error UX is unchanged.
- **Historical row pre-dates the migration**: NULL tokens + NULL cost → UI degrades gracefully to `tokens N/A`. No backfill is performed.
- **Provider model override**: the operator picks `gpt-4o` instead of the default `gpt-4o-mini` via `/settings`. The cost line MUST reflect the actually-used model, not the default.
- **Rounding boundary**: any cost less than `$0.000001` is stored as `0.000000` (NUMERIC(10,6)) and displayed as `~$0.0000`. Acceptable for the thesis demo; aggregate accounting is out of scope.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The live review response (`POST /api/review`) MUST include `prompt_tokens`, `completion_tokens`, and `cost_usd` fields. Each field MUST be either an integer/decimal value or explicit `null`.
- **FR-002**: Each persisted review run MUST store the same three values alongside the existing run summary so the historical detail view can replay them without calling the LLM provider again.
- **FR-003**: The historical detail response (`GET /api/reviews/{id}`) MUST be byte-shape-identical to the live review response so a single frontend component renders both surfaces.
- **FR-004**: The cost estimate MUST be derived from a code-internal pricing table keyed by `(provider, model)` exposed in USD per 1M tokens, with separate input and output prices. The initial table MUST contain at minimum entries for OpenAI `gpt-4o-mini`, OpenAI `gpt-4o`, OpenAI `gpt-4.1-mini`, Anthropic `claude-3-5-sonnet-latest`, and Anthropic `claude-3-5-haiku-latest`.
- **FR-005**: If a `(provider, model)` pair is missing from the pricing table, the cost field MUST be `null` (not `0`, not "unknown") so the UI can distinguish "free" from "unknown".
- **FR-006**: Cost values stored on disk MUST be rounded to 6 decimal places; cost values rendered to the user MUST display up to 4 decimal places.
- **FR-007**: If the LLM provider does not surface usage information (e.g. Ollama), both token fields MUST be `null` and the cost field MUST be `null`. The system MUST NOT substitute zeroes.
- **FR-008**: The live review-result card on `/review` MUST render the token-and-cost line directly under the existing `provider · elapsed_ms` line, using muted styling consistent with the rest of the result header.
- **FR-009**: The historical run detail page (`/history/<run_id>`) MUST render the same token-and-cost line from the persisted values.
- **FR-010**: Reviews persisted before this feature shipped MUST continue to load successfully and MUST render `tokens N/A` for the new line — without any backfill operation.
- **FR-011**: An exception or empty completion from the provider MUST leave the token/cost fields as `null` on the resulting review (never populate them with stale data from a prior call).
- **FR-012**: The cost rendering MUST clearly mark itself as an estimate (e.g. `~$0.0023`) so no reader mistakes it for an invoiced charge.

### Key Entities *(data involved)*

- **Token usage triple**: the prompt-token count, completion-token count, and derived cost in USD that describe one LLM call. Lives on both the live review response and the persisted review run. Either token field may be null when the provider does not surface usage; the cost field may be null when tokens are null or the model/provider pair has no price entry.
- **Pricing entry**: a (provider, model) → (input USD / 1M tokens, output USD / 1M tokens) mapping. Code-internal, edited via source files only in v1. Used to derive the cost field from observed usage counts.
- **Review run record (extended)**: the existing persisted review-run row (from feature 009) gains the same three fields so the historical detail view stays consistent with the live response shape.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A reviewer can read the exact prompt-token count, completion-token count, and cost estimate for any successful review within 2 seconds of the result rendering, without leaving the page.
- **SC-002**: 100% of successful reviews against OpenAI or Anthropic providers carry non-null token counts on both the live response and the persisted record.
- **SC-003**: 100% of successful reviews where both tokens and the pricing entry are known carry a non-null cost figure on both surfaces.
- **SC-004**: Reviews persisted before this feature shipped continue to render correctly (no 5xx, no missing-field crashes) at a verified 100% success rate on the existing fixtures.
- **SC-005**: Adding a new `(provider, model)` pricing entry requires editing exactly one file and rebuilding — no migration, no env-var change, no admin UI.
- **SC-006**: The historical detail view (`/history/<id>`) and the live review view (`/review`) render token-and-cost data using a single shared component, guaranteeing visual parity between the two surfaces (zero diff in rendered HTML for an identical row).

## Assumptions

- Pricing maintenance happens in source control (the operator owning the deploy edits a constant and rebuilds the API image). No runtime override channel is offered in v1.
- The pricing constant reflects public OpenAI / Anthropic per-1M-token list prices as of 2026-05-21. The cost figure is explicitly an **estimate**, not invoiced spend; volume discounts, prompt-caching, and provider-side billing rules are out of scope.
- Ollama remains best-effort: when its `/api/chat` response includes `prompt_eval_count` and `eval_count`, those are used; otherwise tokens are null. No additional probe round-trip is added to fish out counts.
- Historical (pre-migration) review rows are NOT backfilled. The expected ratio of pre-feature rows in production at the time of demo is small (the operator can purge them via `DELETE /api/reviews/{id}` if the inconsistent display bothers them).
- The cost figure is computed at persist time. Re-running the same review later (with a different pricing table) does NOT retroactively rewrite the stored cost — by design, the recorded cost reflects the rate that was in effect at the time of the call.
- No multi-currency support: cost is always USD because both Anthropic and OpenAI bill in USD upstream.
- No streaming LLM responses (already out of scope per `_mvp_scope.md §4`); usage counts are obtained from the final non-streamed response.

## Out of Scope

- Aggregate spend widgets ("total $ this month", "spend by repo") on `/history`.
- Hard budget caps or alerts when a review crosses a price threshold.
- Pre-submission cost estimates on `/review` (would require token counting before the actual call; deferred).
- Per-team or per-repo pricing overrides.
- A `/settings` UI for editing the pricing table (operators edit `pricing.py` and rebuild).
- Backfilling token/cost data for review rows that pre-date this feature.
- LLM streaming (incompatible with structured JSON output, OUT-OF-SCOPE in `_mvp_scope.md §4`).
- Currency conversion away from USD.
