---
description: "Task list for 012-tokens-cost-estimate"
---

# Tasks: Token usage + cost estimate per review

**Input**: Design documents from `/specs/012-tokens-cost-estimate/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md
**Tests**: pytest unit + integration (per spec.md §Tests). No frontend Vitest.
**Organization**: Tasks grouped by user story for independent verification.

## Format

`- [ ] TID [P?] [Story?] Description with file path`

## Path Conventions

Web app — `backend/src/`, `backend/tests/`, `backend/alembic/versions/`, `frontend/src/`. Repository root anchors all paths.

---

## Phase 1: Setup

**Purpose**: Constitution gate + branch placement.

- [X] T001 Verify branch `012-tokens-cost` is checked out and clean of unrelated edits via `git status -s` (working tree may contain only `specs/012-tokens-cost-estimate/*` artefacts).
- [X] T002 Draft ADR-015 "Persist token usage + cost estimate on review_runs" in `/Users/tarasivanov/Desktop/Диплом/_decision_log.md` using the prose from `specs/012-tokens-cost-estimate/research.md §Decision: ADR-015 contents`. Insert as a new entry directly above ADR-014. Status: accepted. Supersedes nothing. **HARD GATE — Constitution Principle II: NO production code below until this lands.**

**Checkpoint**: ADR-015 merged into decision log → unblocks all foundational tasks.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Schema migration + adapter usage primitive. Both required by every US.

**⚠️ CRITICAL**: No user-story task starts until Phase 2 is complete.

- [X] T003 Add `ChatUsage` frozen dataclass to `backend/src/codesensei/providers/base.py` (fields: `prompt_tokens: int | None`, `completion_tokens: int | None`, `model: str | None`). Per data-model.md §Entity 1. Protocol surface unchanged.
- [X] T004 Write alembic migration `backend/alembic/versions/005_review_run_tokens.py` with `revision = "005_review_run_tokens"`, `down_revision = "004_review_history"`. `upgrade()`: three `op.add_column` calls on `review_runs` — `prompt_tokens INTEGER NULL`, `completion_tokens INTEGER NULL`, `cost_usd NUMERIC(10, 6) NULL`. `downgrade()`: three `op.drop_column` calls in reverse order.
- [X] T005 Apply migration locally — `docker compose exec api alembic upgrade head` (or rebuild api: `docker compose up -d --build api worker`); confirm `alembic current` reports `005_review_run_tokens (head)`.

**Checkpoint**: dataclass available + DB schema extended → user-story phases may run in parallel where marked [P].

---

## Phase 3: User Story 1 — Live `/review` token + cost line (Priority: P1) 🎯 MVP

**Goal**: every successful `POST /api/review` returns + UI renders `prompt_tokens`, `completion_tokens`, `cost_usd`.

**Independent Test**: paste any public PR URL on `/review` with OpenAI configured → result card shows `1234 in / 567 out tokens · ~$0.0023` line under `provider · X ms`. Quickstart Step 1.

### Tests for User Story 1

- [X] T006 [P] [US1] Write unit tests in `backend/tests/unit/test_review_pricing.py` covering: known OpenAI/Anthropic pair → exact cost via `(prompt_tokens / 1e6) * in + (completion_tokens / 1e6) * out`; unknown pair → `None`; Ollama pair (absent) → `None`; either token `None` → `None`; rounding at 6 dp boundary.
- [X] T007 [P] [US1] Write unit tests in `backend/tests/unit/test_provider_usage.py` — for each of OpenAI/Anthropic/Ollama: stub the SDK response to include usage fields, instantiate adapter, `await provider.chat(...)`, assert `provider._last_usage` is a populated `ChatUsage`. Separately assert that on an SDK exception (`_translate` path) `_last_usage` is left as `None`. For Ollama: include both "with usage fields" and "without usage fields" cases.

### Implementation for User Story 1

- [X] T008 [P] [US1] Create `backend/src/codesensei/review/pricing.py` per `contracts/pricing_module.md`. Const `PRICING_PER_1M` with the 5 initial entries (openai gpt-4o-mini / gpt-4o / gpt-4.1-mini, anthropic claude-3-5-sonnet-latest / claude-3-5-haiku-latest). Pure function `compute_cost_usd(provider, model, prompt_tokens, completion_tokens) -> float | None` per the contract semantics table. Result rounded via `round(value, 6)`.
- [X] T009 [P] [US1] Extend `backend/src/codesensei/review/schema.py:ReviewResult` with three optional fields: `prompt_tokens: int | None = None`, `completion_tokens: int | None = None`, `cost_usd: float | None = None`. No new validators; defaults handle existing call sites.
- [X] T010 [P] [US1] Modify `backend/src/codesensei/providers/openai_adapter.py`: add `__init__` setting `self._last_usage: ChatUsage | None = None`. After successful `chat.completions.create`, populate `self._last_usage = ChatUsage(prompt_tokens=response.usage.prompt_tokens, completion_tokens=response.usage.completion_tokens, model=response.model or chosen)`. On exception path (via `_translate`) leave `_last_usage` as-is at `None`.
- [X] T011 [P] [US1] Modify `backend/src/codesensei/providers/anthropic_adapter.py`: same pattern as T010 but read `response.usage.input_tokens` / `response.usage.output_tokens`. Use the chosen model name as the `model` field on `ChatUsage` (Anthropic does not echo it back consistently).
- [X] T012 [P] [US1] Modify `backend/src/codesensei/providers/ollama_adapter.py`: same pattern. Read `data.get("prompt_eval_count")` / `data.get("eval_count")` — if either is `None`, leave `_last_usage = None` per the "either both or neither" invariant from data-model.md §Entity 1.
- [X] T013 [US1] Modify `backend/src/codesensei/review/service.py:_run_chat` — after `raw = await asyncio.wait_for(provider.chat(...), ...)`, read `usage = getattr(provider, "_last_usage", None)`, derive `model = usage.model if usage else None`, compute `cost = pricing.compute_cost_usd(provider.name, model, usage.prompt_tokens if usage else None, usage.completion_tokens if usage else None)`. Pass `prompt_tokens`, `completion_tokens`, `cost_usd` into the `ReviewResult(...)` constructor. Import `pricing` from `codesensei.review.pricing`. Depends on T008–T012.
- [X] T014 [P] [US1] Extend frontend type `ReviewResult` in `frontend/src/api/review.ts` with three optional fields: `prompt_tokens?: number | null`, `completion_tokens?: number | null`, `cost_usd?: number | null`.
- [X] T015 [US1] Modify `frontend/src/pages/ReviewPage.vue` — add a small helper inside `<script setup>`: `function formatTokenLine(r: ReviewResult): string | null` per `research.md §Decision 5`. Render the helper output as a second muted `<span class="text-xs font-mono">` underneath the existing `provider · {{ result.elapsed_ms }} ms` line, wrapped in `v-if` on a non-null helper return. Cost format: `~$${cost.toFixed(4)}`. Depends on T014.

**Checkpoint**: a fresh OpenAI/Anthropic review on `/review` renders the new line; an Ollama or unknown-model review shows `tokens N/A` or tokens-only.

---

## Phase 4: User Story 2 — `/history/<id>` replays the same line (Priority: P1)

**Goal**: persisted runs carry token/cost; the detail view renders the identical line without an LLM round-trip.

**Independent Test**: open any post-feature run from `/history/<id>` → identical token line as the live view. Pre-feature runs show `tokens N/A`. Quickstart Steps 4–5.

### Tests for User Story 2

- [X] T016 [P] [US2] Extend `backend/tests/integration/test_reviews_history_endpoint.py` — add `test_post_review_persists_tokens_and_cost`: monkeypatched provider sets `_last_usage = ChatUsage(prompt_tokens=1000, completion_tokens=500, model="gpt-4o-mini")` and chat returns valid JSON. Assert that `POST /api/review` response carries the three new fields AND that `GET /api/reviews/{id}` returns the same numeric values back. Add `test_get_review_legacy_row_returns_null_tokens`: insert a row via the fake store with all three new fields = `None`, assert detail GET returns them as JSON `null`.

### Implementation for User Story 2

- [X] T017 [P] [US2] Extend ORM in `backend/src/codesensei/reviews_history/models.py:ReviewRun` with `prompt_tokens: Mapped[int | None]`, `completion_tokens: Mapped[int | None]`, `cost_usd: Mapped[Decimal | None]`. Import `Decimal` from `decimal`; set `Numeric(10, 6)` on the cost column.
- [X] T018 [P] [US2] Extend `backend/src/codesensei/reviews_history/schema.py`: add the same three optional fields to both `ReviewRunSummary` and `ReviewRunDetail`. Reuse the wire-shape from `contracts/reviews_history_endpoints.md`. Cost field is `float | None` (pydantic coerces from `Decimal`).
- [X] T019 [P] [US2] Extend `backend/src/codesensei/reviews_history/store.py:insert_run` signature with `prompt_tokens: int | None = None`, `completion_tokens: int | None = None`, `cost_usd: float | None = None` kwargs and persist them. Extend `_row_to_summary` and `_row_to_detail` (or whichever helpers exist) to emit the three fields. Round `cost_usd` to 6 dp on insert (`round(value, 6) if value is not None else None`).
- [X] T020 [US2] Modify `backend/src/codesensei/review/service.py:_persist_run` signature + call site in `_run_chat` to pass through `prompt_tokens=`, `completion_tokens=`, `cost_usd=` (computed in T013) into `history_store.insert_run`. Depends on T013, T019.
- [X] T021 [P] [US2] Extend frontend types in `frontend/src/api/reviews.ts` — add the three optional fields to both `ReviewRunSummary` and `ReviewRunDetail`.
- [X] T022 [US2] Modify `frontend/src/pages/HistoryDetailPage.vue` — render the same token line as `/review` via an inline helper (duplicate the 5-line `formatTokenLine` rather than introducing a shared utility module — minor duplication is acceptable per plan.md §Structure Decision). Wire it into the existing run header card directly below `provider · {{ run.elapsed_ms }} ms`. Depends on T021.

**Checkpoint**: open `/history/<id>` for a fresh OpenAI run → token line renders from the persisted columns, no LLM call in logs.

---

## Phase 5: User Story 3 — Operator updates pricing (Priority: P3)

**Goal**: confirm the maintenance flow (`edit pricing.py → rebuild`) works end-to-end.

**Independent Test**: bump a price in `pricing.py`, rebuild api, run a review → cost reflects the new rate. Quickstart Step 7.

- [X] T023 [US3] No code task — verify `specs/012-tokens-cost-estimate/quickstart.md §Step 7` walks the operator through editing `backend/src/codesensei/review/pricing.py` and rebuilding the api image. If the step is missing details (which model, what to look for in the rebuilt output), tighten the prose before commit. This task closes US3 by ensuring the documentation matches the code surface.

**Checkpoint**: pricing-table maintenance flow is reproducible from quickstart.md alone — no tribal knowledge required.

---

## Phase 6: Polish & Cross-Cutting

**Purpose**: verification, lint, manual smoke, marker bumps.

- [X] T024 Run `docker compose exec api alembic current` — verify revision is `005_review_run_tokens`.
- [X] T025 Run backend test suite via `docker compose run --rm -v "$(pwd)/backend/tests:/app/tests" -e OPENAI_API_KEY= -e ANTHROPIC_API_KEY= -e GITHUB_TOKEN= -e MASTER_KEY= -e MASTER_KEY_FILE= api sh -c "/opt/venv/bin/python -m ensurepip && /opt/venv/bin/python -m pip install -q pytest pytest-asyncio respx && cd /app && /opt/venv/bin/python -m pytest --tb=short -q"`. Expect all green including the new `test_review_pricing.py` + `test_provider_usage.py` + extended `test_reviews_history_endpoint.py`.
- [X] T026 Run `docker compose run --rm api /opt/venv/bin/python -m ruff check src tests`. Expect `All checks passed!`.
- [X] T027 Run `cd frontend && npx vue-tsc --noEmit && npx vite build`. Both must be clean.
- [X] T028 `docker compose up -d --build api worker frontend` to bake the migration + UI changes into running images.
- [X] T029 Manual smoke per `specs/012-tokens-cost-estimate/quickstart.md` Steps 1–8. Verify token line on `/review` for OpenAI, token N/A for Ollama, historical replay on `/history/<id>`, pricing-table edit flow.
- [X] T030 Verify `.specify/feature.json` already points at `specs/012-tokens-cost-estimate` (was updated during /speckit-plan); verify `CLAUDE.md` SPECKIT marker also bumped (was updated during /speckit-plan). Idempotent check.

**Checkpoint**: all green → ready for single-commit pipeline boundary + PR.

---

## Dependencies

```text
Phase 1 (T001-T002)
  → Phase 2 (T003 || T004 → T005)
    → Phase 3 (US1)
       └─ T006, T007, T008, T009, T010, T011, T012, T014 parallel
       └─ T013 depends on T008-T012
       └─ T015 depends on T014
    → Phase 4 (US2)
       └─ T016, T017, T018, T019, T021 parallel
       └─ T020 depends on T013, T019
       └─ T022 depends on T021
    → Phase 5 (US3 — documentation-only, no code)
    → Phase 6 (Polish — sequential)
```

US1 and US2 share T013 (service-layer wiring) + T020 (persist call site). Stories can be developed in parallel up to the integration test (T016 sees the full path).

## Parallel Execution Examples

**Phase 2 kickoff** (after T002 ADR lands):
- T003 (dataclass) || T004 (migration)

**Phase 3 implementation parallelism** (after T005 migration applied):
- T006, T007, T008, T009, T010, T011, T012, T014 can run in parallel — they touch distinct files.

**Phase 4 implementation parallelism**:
- T016, T017, T018, T019, T021 — distinct files, no shared state.

## Implementation Strategy

**MVP slice**: T001–T015 alone delivers live `/review` token + cost UI. Phase 4 (history persistence) is bundled at P1 to avoid wire-vs-history shape drift, but if time-boxed, Phase 4 ships as a same-day follow-up without breaking Phase 3.

**Single-commit pipeline boundary**: all phases commit as one feature commit (`feat(012-tokens-cost-estimate): ...`) per project commit-granularity convention. Branch already exists as `012-tokens-cost`. Push to remote + open PR with quickstart-aligned test plan at Phase 6 completion.
