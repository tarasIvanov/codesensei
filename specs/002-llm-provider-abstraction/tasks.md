---
description: "Task list for feature 002-llm-provider-abstraction"
---

# Tasks: LLM and Embedding Provider Abstraction

**Input**: Design documents from `/specs/002-llm-provider-abstraction/`
**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/` (all present)

**Tests**: REQUIRED for this feature per FR-015 (CI must pass offline; vendor SDK calls and outbound HTTP MUST be mocked). Tests are written before the implementation they verify.

**Organization**: Tasks are grouped by user story so each story is independently completable and testable.

## Format: `[ID] [P?] [Story] Description`

- **[P]** — different file, no dependency on a yet-incomplete task; safe to run in parallel.
- **[Story]** — user-story label (US1 / US2 / US3 / US4); absent on Setup, Foundational, and Polish phases.
- File paths are concrete and absolute-relative to repo root.

## Path Conventions

- Backend code: `backend/src/codesensei/...`
- Backend tests: `backend/tests/unit/...` and `backend/tests/integration/...`
- Frontend code: `frontend/src/...`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: dependencies, settings surface, and test rigging that every later phase depends on.

- [ ] T001 Add `openai>=1.50`, `anthropic>=0.40` to `[project].dependencies` in `backend/pyproject.toml`; add `respx>=0.21` to `[tool.uv].dev-dependencies`. Then run `uv lock` inside `backend/` to regenerate `backend/uv.lock`.
- [ ] T002 Extend `Settings` in `backend/src/codesensei/config.py` with three new optional fields: `llm_model: str = ""`, `embedding_model: str = ""`, `ollama_base_url: str = "http://ollama:11434"`. Match the existing pydantic-settings env-var pattern.
- [ ] T003 [P] Append a new `# === Provider tuning (optional) ===` section to `.env.example` with `LLM_MODEL=`, `EMBEDDING_MODEL=`, `OLLAMA_BASE_URL=http://ollama:11434`. Do not change existing rows.
- [ ] T004 [P] Add a session-scoped autouse `respx` fixture and a no-network guard in `backend/tests/conftest.py` per `research.md > R10` — every test imports respx for httpx, and any unintercepted httpx call MUST fail loudly.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: shared types and exceptions that every user story imports. Nothing in Phase 3+ can compile without these.

**⚠️ CRITICAL**: complete this phase before starting any user story.

- [ ] T005 Create `backend/src/codesensei/providers/base.py` defining `ChatMessage` (TypedDict), `LLMProvider` (Protocol), `EmbeddingProvider` (Protocol), `ProviderState` (Enum: OK/UNCONFIGURED/UNREACHABLE), and `ProviderProbeResult` (frozen dataclass) per `data-model.md`.
- [ ] T006 Create `backend/src/codesensei/providers/errors.py` defining `ProviderError(Exception)` with `provider: str`, `message: str`, `retryable: bool`, plus `classify_http_status(code: int) -> bool` matching the truth table in `contracts/provider_error.md`. `str(exc)` MUST return `f"{provider}: {message}"`.
- [ ] T007 Update `backend/src/codesensei/providers/__init__.py` to publicly export `ChatMessage`, `LLMProvider`, `EmbeddingProvider`, `ProviderError`, `ProviderState`, `ProviderProbeResult`. Factories are exported in T013.

**Checkpoint**: foundation ready — user stories can begin.

---

## Phase 3: User Story 1 — Config-driven provider selection (Priority: P1) 🎯 MVP

**Goal**: `get_llm_provider()` and `get_embedding_provider()` return the correct adapter for each accepted env-var value, reject unknown values with a clear message, and never perform network I/O on import.

**Independent Test**: run `pytest backend/tests/unit/test_provider_factory.py` — selection across the four accepted (provider, role) combinations succeeds; unknown values raise `ProviderError(provider="config")` listing the accepted set.

### Tests for User Story 1 ⚠️ — write before implementation

- [ ] T008 [P] [US1] Create `backend/tests/unit/test_provider_factory.py` covering: (a) `LLM_PROVIDER=openai|anthropic|ollama` each returns the expected adapter type; (b) case-insensitive + trimmed comparison; (c) `EMBEDDING_PROVIDER=openai|ollama` each returns the expected adapter type; (d) `LLM_PROVIDER=mistral` raises `ProviderError(provider="config", retryable=False)` whose `message` lists the accepted values; (e) importing `codesensei.providers` does not touch the network — assert by monkeypatching `httpx.AsyncClient.__init__` to raise.

### Implementation for User Story 1

- [ ] T009 [P] [US1] Create `backend/src/codesensei/providers/openai_adapter.py` with `OpenAIChatProvider` and `OpenAIEmbeddingProvider` class skeletons (`name = "openai"`, lazy `AsyncOpenAI` client construction). `chat()` / `embed()` body is `raise NotImplementedError` — real implementation lands in US3.
- [ ] T010 [P] [US1] Create `backend/src/codesensei/providers/anthropic_adapter.py` with `AnthropicChatProvider` (`name = "anthropic"`, lazy `AsyncAnthropic` client). `chat()` body is `raise NotImplementedError` until US3. No embedding class is defined here — Anthropic-as-embedding is rejected by the factory.
- [ ] T011 [P] [US1] Create `backend/src/codesensei/providers/ollama_adapter.py` with `OllamaChatProvider` and `OllamaEmbeddingProvider` class skeletons (`name = "ollama"`, lazy `httpx.AsyncClient` keyed on `OLLAMA_BASE_URL`). `chat()` / `embed()` body is `raise NotImplementedError` until US3.
- [ ] T012 [US1] Create `backend/src/codesensei/providers/factory.py` with `@lru_cache(maxsize=1)` factories `get_llm_provider()` and `get_embedding_provider()`. Both read `Settings()` lazily, trim+lowercase the env value, dispatch to the matching adapter constructor, and raise `ProviderError(provider="config", retryable=False, message=...)` on unknown values. Depends on T009, T010, T011.
- [ ] T013 [US1] Extend `backend/src/codesensei/providers/__init__.py` to also export `get_llm_provider` and `get_embedding_provider`.

**Checkpoint**: factory works for the happy paths and unknown-value path. Anthropic-as-embedding rejection is addressed in US2.

---

## Phase 4: User Story 2 — Anthropic-embedding combination rejected (Priority: P1)

**Goal**: when `EMBEDDING_PROVIDER=anthropic`, `get_embedding_provider()` raises a configuration error at first resolution naming the offending env var, the unsupported value, and a suggested fix.

**Independent Test**: run `pytest backend/tests/unit/test_provider_factory.py::test_embedding_anthropic_rejected` — the call raises `ProviderError(provider="config", retryable=False)` whose `message` mentions both `EMBEDDING_PROVIDER` and `anthropic`, and lists `openai` and `ollama` as accepted.

### Tests for User Story 2 ⚠️

- [ ] T014 [US2] Append `test_embedding_anthropic_rejected` to `backend/tests/unit/test_provider_factory.py`: set `EMBEDDING_PROVIDER=anthropic`, assert `ProviderError` is raised, `provider=="config"`, `retryable is False`, and the message contains the substrings `EMBEDDING_PROVIDER`, `anthropic`, `openai`, and `ollama`.

### Implementation for User Story 2

- [ ] T015 [US2] Refine the `EMBEDDING_PROVIDER` branch inside `backend/src/codesensei/providers/factory.py`: when the value is `anthropic`, the error message MUST explicitly call out the unsupported combination (`EMBEDDING_PROVIDER=anthropic is not supported because Anthropic has no embeddings API`) and suggest `openai` or `ollama`. T012 implements the generic unknown-value path; T015 specializes the Anthropic branch with the dedicated message.

**Checkpoint**: factory fails fast and informatively on the misconfiguration.

---

## Phase 5: User Story 3 — Uniform error envelope across providers (Priority: P2)

**Goal**: every adapter raises exactly one exception type (`ProviderError`) carrying `provider`, `message`, `retryable`. Vendor SDK exceptions never escape the adapter.

**Independent Test**: run `pytest backend/tests/unit/test_openai_adapter.py backend/tests/unit/test_anthropic_adapter.py backend/tests/unit/test_ollama_adapter.py backend/tests/unit/test_provider_errors.py` — every mocked failure mode produces a `ProviderError` with the expected `retryable` flag per the truth table.

### Tests for User Story 3 ⚠️

- [ ] T016 [P] [US3] Create `backend/tests/unit/test_provider_errors.py` exercising the full `classify_http_status` truth table (5xx → True, 429 → True, 408 → True, other 4xx → False, plus an unknown-code path returning False) and `ProviderError.__str__` formatting.
- [ ] T017 [P] [US3] Create `backend/tests/unit/test_openai_adapter.py`: with `AsyncMock` over `AsyncOpenAI`, verify (a) `chat()` happy path returns string; (b) mocked 503 yields `ProviderError(retryable=True)`; (c) mocked `AuthenticationError` yields `ProviderError(retryable=False)`; (d) empty completion yields `ProviderError(retryable=False, message contains "empty")`; (e) `embed()` happy path returns `list[list[float]]`; (f) `embed()` mocked rate-limit yields `retryable=True`.
- [ ] T018 [P] [US3] Create `backend/tests/unit/test_anthropic_adapter.py`: with `AsyncMock` over `AsyncAnthropic.messages.create`, verify (a) `chat()` happy path; (b) mocked 401 yields `ProviderError(retryable=False, provider="anthropic")`; (c) mocked 503 yields `retryable=True`; (d) no `embed()` method exists on the module.
- [ ] T019 [P] [US3] Create `backend/tests/unit/test_ollama_adapter.py`: with `respx` mocking `POST /api/chat` and `POST /api/embeddings`, verify (a) `chat()` happy path; (b) `chat()` `ConnectError` → `retryable=True`; (c) `chat()` HTTP 500 → `retryable=True`; (d) `chat()` HTTP 404 → `retryable=False`; (e) `embed()` happy path; (f) `embed()` timeout → `retryable=True`.

### Implementation for User Story 3

- [ ] T020 [P] [US3] Implement `chat()` and `embed()` in `backend/src/codesensei/providers/openai_adapter.py`: call `AsyncOpenAI.chat.completions.create` / `embeddings.create`, return the extracted text / vectors, catch `openai.AuthenticationError`, `openai.RateLimitError`, `openai.APIStatusError`, `openai.APIConnectionError`, and any other `openai.OpenAIError` and translate each to `ProviderError` using `classify_http_status` for the status-bearing ones. Default model picked from `Settings.llm_model` / `Settings.embedding_model` with fallback to `gpt-4o-mini` / `text-embedding-3-small`.
- [ ] T021 [P] [US3] Implement `chat()` in `backend/src/codesensei/providers/anthropic_adapter.py`: call `AsyncAnthropic.messages.create`, extract the assistant text from `response.content[0].text`, catch `anthropic.AuthenticationError`, `anthropic.RateLimitError`, `anthropic.APIStatusError`, `anthropic.APIConnectionError`, and translate to `ProviderError`. Default model `claude-3-5-sonnet-latest`; honor `Settings.llm_model`.
- [ ] T022 [P] [US3] Implement `chat()` and `embed()` in `backend/src/codesensei/providers/ollama_adapter.py`: `POST {OLLAMA_BASE_URL}/api/chat` and `POST {OLLAMA_BASE_URL}/api/embeddings` via `httpx.AsyncClient`, parse the response, catch `httpx.ConnectError`, `httpx.TimeoutException`, and `httpx.HTTPStatusError` and translate to `ProviderError` using `classify_http_status`. Defaults: chat `llama3.1:8b`, embed `nomic-embed-text`.

**Checkpoint**: every adapter chat/embed call surfaces `ProviderError` only. Vendor SDK exception types are confined to adapter modules.

---

## Phase 6: User Story 4 — Provider readiness visible on dashboard (Priority: P3)

**Goal**: `/healthz` includes a `providers` object with `llm` and `embedding` states; the Vue dashboard renders two new badges using the same UX as the existing four.

**Independent Test**: with the stack up and `OPENAI_API_KEY` empty, `curl /healthz | jq '.providers.llm'` returns `"unconfigured"`; the dashboard shows a grey LLM badge. With Ollama configured but stopped, the value is `"unreachable"` and the badge is red.

### Tests for User Story 4 ⚠️

- [ ] T023 [P] [US4] Create `backend/tests/unit/test_provider_probe.py`: with respx and patched env settings, verify (a) OpenAI key set → `probe_llm_provider()` returns `ProviderState.OK`; (b) OpenAI key empty → `UNCONFIGURED`; (c) Ollama `GET /api/tags` → 200 → `OK`; (d) Ollama `ConnectError` → `UNREACHABLE`; (e) Ollama 500 → `UNREACHABLE`. Same coverage for `probe_embedding_provider()`.
- [ ] T024 [P] [US4] Create `backend/tests/integration/test_healthz_providers.py`: with the existing `async_client` fixture and a new `mock_provider_probes` fixture, hit `/healthz` and assert the envelope has the new `providers.llm` / `providers.embedding` fields with the patched states; assert that provider states do NOT alter `status` or `failing[]`.

### Implementation for User Story 4

- [ ] T025 [US4] Create `backend/src/codesensei/providers/probe.py` exporting `async def probe_llm_provider() -> ProviderProbeResult` and `async def probe_embedding_provider() -> ProviderProbeResult`. OpenAI / Anthropic paths check `bool(Settings.openai_api_key)` / `bool(Settings.anthropic_api_key)` only. Ollama path issues `GET {OLLAMA_BASE_URL}/api/tags` via `httpx.AsyncClient(timeout=2.0)`; on 200 → OK, on any error → UNREACHABLE.
- [ ] T026 [US4] Extend `backend/src/codesensei/healthcheck.py`: add the two provider probes to the existing `asyncio.gather(...)` call inside the `/healthz` handler; thread the results through `build_envelope(db_result, redis_status, llm_state, embedding_state)`; the envelope dictionary gains a top-level `providers` key with `llm` and `embedding` string fields. Per FR-013, provider states do NOT contribute to `failing[]` and do NOT flip overall `status` to `degraded`. Update the existing log line to include both new fields.
- [ ] T027 [US4] Extend `frontend/src/App.vue`: extend the `HealthEnvelope` TypeScript type with `providers: { llm: ProviderStatus; embedding: ProviderStatus }`; add two new `ref<ProviderStatus>('pending')` values and two new `<li>` badges (`llm`, `embedding`) below the existing four; reuse the `colorFor()` helper, mapping `ok` → green, `unconfigured` → grey, `unreachable` → red.
- [ ] T028 [US4] Update `backend/tests/integration/test_healthz_endpoint.py` and the `mock_probes` fixture in `backend/tests/conftest.py`: extend the fixture to also patch `codesensei.healthcheck.probe_llm_provider` and `probe_embedding_provider`; update all existing assertions that match the envelope shape to tolerate the new `providers` field. Default fixture state: both providers `OK`.

**Checkpoint**: every story is independently testable; the dashboard is observably correct against the four scenarios in `quickstart.md`.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: final hygiene before merging the feature PR.

- [ ] T029 [P] Run `uv run --with ruff ruff check backend/src backend/tests --fix` and commit any auto-fixes inside the same chunk.
- [ ] T030 [P] Run `uv lock` once more inside `backend/` to confirm the lockfile resolves cleanly with the new dependencies and commit any diff.
- [ ] T031 Verify ADR-003 (`../_decision_log.md`) still aligns with the model defaults in `research.md > R5`; if it pins different defaults, open a follow-up ADR PR per Principle II — do not silently diverge.
- [ ] T032 Walk through `specs/002-llm-provider-abstraction/quickstart.md` scenarios A → D against a freshly rebuilt stack (`docker compose up --build -d`). Capture any UX or wording fix in a follow-up commit before merge.
- [ ] T033 Update `CLAUDE.md` only if Phase 6 introduces a new top-level concern worth surfacing to future Claude sessions; otherwise leave the existing reference in place.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)** — no dependencies; T003 and T004 may run in parallel with T001/T002 once `pyproject.toml` is staged.
- **Foundational (Phase 2)** — depends on Setup; blocks all user stories.
- **US1 (Phase 3)** — depends on Foundational.
- **US2 (Phase 4)** — depends on US1 (specifically T012). Strictly speaking the rejection branch lives inside the same factory file; T015 is a polish on top of T012.
- **US3 (Phase 5)** — depends on Foundational + the adapter scaffolding (T009, T010, T011) from US1. T020/T021/T022 each upgrade their respective adapter from skeleton to real.
- **US4 (Phase 6)** — depends on Foundational; can run in parallel with US3 in principle, but T025 imports `Settings` extension from T002 (already done in Setup), so order is fine.
- **Polish (Phase 7)** — depends on every prior phase being merged.

### Parallel Opportunities

- T003 ∥ T004 ∥ T002 (different files).
- T009 ∥ T010 ∥ T011 (separate adapter files, independent).
- T017 ∥ T018 ∥ T019 (separate test files, separate adapters).
- T020 ∥ T021 ∥ T022 (separate adapter files; each only depends on its own US3 test).
- T029 ∥ T030 (different concerns: linter vs lockfile).

### Within Each User Story

1. Write the test tasks; confirm they fail.
2. Implement until the tests pass.
3. Do not start the next user story until the current one's checkpoint passes.

---

## Parallel Example: User Story 1

```bash
# Adapter skeletons can all be authored in parallel once T008 (test) is in place:
Task: "Create backend/src/codesensei/providers/openai_adapter.py skeleton (T009)"
Task: "Create backend/src/codesensei/providers/anthropic_adapter.py skeleton (T010)"
Task: "Create backend/src/codesensei/providers/ollama_adapter.py skeleton (T011)"
# Then T012 (factory) consumes all three.
```

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Phase 1 + Phase 2.
2. Phase 3 (US1) — factory + adapter skeletons; provider switch works conceptually even though chat/embed bodies raise `NotImplementedError`.
3. STOP and validate: `pytest backend/tests/unit/test_provider_factory.py` passes; the package imports without network I/O.

### Incremental Delivery

1. MVP (US1).
2. + US2 (Anthropic-embedding rejection) — small, low-risk increment.
3. + US3 (real adapter bodies + error normalization) — the bulk of vendor-integration work.
4. + US4 (`/healthz` extension + Vue badges) — observability + UI.
5. Polish.

### Single-PR Strategy (per memory)

Because this project commits at chunk boundaries — not per task — the whole feature lands as one PR. The phase order above is the recommended internal sequence for the implementer; commit can happen once Phase 7 is clean.

---

## Notes

- `[P]` tasks touch different files and have no incomplete dependency.
- `[Story]` labels map every implementation task to a user story for traceability.
- Tests are committed before the matching implementation tasks per FR-015 / Constitution "Test-first for critical paths".
- Vendor SDK exception types MUST NOT escape adapter modules — verified by US3 tests.
- No outbound HTTP in tests — verified by the autouse respx guard from T004.
