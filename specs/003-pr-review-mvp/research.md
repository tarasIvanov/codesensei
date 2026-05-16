# Phase 0 — Research Notes (003-pr-review-mvp)

Each entry below resolves a NEEDS-CLARIFICATION / open-design question raised in `plan.md`. Format: **Decision** → **Rationale** → **Alternatives considered**.

---

## R1: How do we coerce the LLM to return valid JSON findings, across three providers?

**Decision**: System-prompt + strict post-parse, no provider-side JSON-mode flag in this feature. The system prompt spells out the exact JSON envelope (`{"verdict": "...", "findings": [...]}`) and instructs the LLM to emit **only** that envelope with no preamble. The `parser.py` step strips a leading ```json fence if present, then `json.loads` + pydantic-validates. Any failure → `ReviewError(provider_malformed_output)` → HTTP 502. No retries.

**Rationale**:
- Keeps the review service provider-agnostic. JSON-mode flags exist on OpenAI (`response_format={"type":"json_object"}`) and Anthropic (via `tool_use`), but Ollama models vary; relying on a provider-side flag would push provider-specific code back into the review service, violating Principle III.
- Constitution forbids silent retries that hide upstream failures; FR-008 says fail-fast on malformed.
- Per-adapter JSON-mode wiring can be added **inside** each adapter in a later feature without changing the review service surface.

**Alternatives**:
- Pass `response_format={"type":"json_object"}` from the review service: rejected — leaks provider knobs into business logic.
- Retry once on parse failure: rejected — masks real provider regressions; SC-003 wants a single, consistent error.
- LLM tool-use / function-calling: deferred — adds two more code paths (OpenAI/Anthropic style differs from Ollama), zero gain on the MVP slice.

---

## R2: What is the diff-size limit?

**Decision**: `REVIEW_MAX_DIFF_BYTES = 256_000` (≈ 250 KB) as a default, configurable via env. Exceeding → 413.

**Rationale**:
- 256 KB comfortably holds a ~200-changed-line PR (typical mid-size review per SC-001) with ~40× headroom for context lines and per-file headers, but rejects monster refactors before any LLM cost is incurred.
- Sits well under the input-token budget of all three providers' default models (`gpt-4o-mini`, `claude-3-5-sonnet-latest`, `llama3.1:8b`) so we never get cut off mid-prompt.
- Single byte-count check, no tokenisation needed — meets the "<1 s reject" budget in SC-004.

**Alternatives**:
- Token-count limit (`tiktoken`): rejected for MVP — provider-specific, and constitution §Pre-flight token counting applies once we add RAG; here we're below saturation anyway.
- Line-count limit: rejected — diffs with very long lines (minified files) would bypass the guard.
- No limit: rejected — wastes LLM budget on inputs that won't yield useful reviews.

---

## R3: How does the backend fetch a PR diff from GitHub?

**Decision**: Single `httpx.AsyncClient` GET to `https://api.github.com/repos/{owner}/{repo}/pulls/{number}` with header `Accept: application/vnd.github.v3.diff`. When `GITHUB_TOKEN` is set, add `Authorization: Bearer {token}` and `X-GitHub-Api-Version: 2022-11-28`. Map HTTP statuses → `ReviewError` categories: `401|403` → `github_fetch_failed/auth`; `404` → `github_fetch_failed/not_found`; `5xx | TimeoutException | ConnectError` → `github_fetch_failed/other`. Response body **is** the unified diff (no JSON unwrap needed).

**Rationale**:
- The `application/vnd.github.v3.diff` Accept header is the GitHub-documented way to fetch a unified diff directly; avoids client-side concatenation of per-file patches.
- `httpx` is already a stack dependency (used in 002 Ollama adapter); no new lib.
- We never pass the token to the frontend, never log it, never include it in error responses (FR-011).

**Alternatives**:
- `PyGithub` SDK: rejected — heavier, sync API surface, adds an unjustified dependency for a single endpoint hit.
- `gh` CLI subprocess: rejected — couples the container to a non-Python toolchain.
- Fetch per-file patches via `/files` endpoint + assemble: rejected — paginated, more network round-trips, more code.

---

## R4: Does the frontend need a router?

**Decision**: Yes — add `vue-router@4` and define two routes: `/` (existing health page, refactored into `HealthPage.vue`) and `/review` (new `ReviewPage.vue`). No nested routes, no lazy-loading for MVP.

**Rationale**:
- Spec FR-001 specifies the page at `/review` as a product-visible URL. Implementing this with `v-if` toggles would hide the URL in the browser, breaking shareability and bookmarking.
- `vue-router` is the canonical Vue 3 routing solution; constitution §Stack mandates Vue 3 + Vite SPA, which standardly ships with `vue-router` for multi-page SPAs — accessory, not "new infrastructural component", so no new ADR.

**Alternatives**:
- Hand-rolled `window.location.pathname` switch: rejected — re-invents `vue-router` poorly, fails on browser back/forward.
- Skip routing, render both pages in a tabbed component on `/`: rejected — violates FR-001 (page must be at `/review`).

---

## R5: What does the LLM prompt look like?

**Decision**: Two-message template, system + user. **System** establishes role ("You are a senior code reviewer reviewing a unified diff. Return JSON only."), spells out the exact JSON contract (verdict ∈ {approve, request_changes, comment}; findings array; per-finding fields and the allowed severity set), and forbids prose around the JSON. **User** supplies a fenced ```diff block containing the unified diff. `temperature=0.1`, `max_tokens=4096` (fits findings even for chatty providers). Full template lives in `contracts/llm_prompt.md` and is snapshot-tested.

**Rationale**:
- Keeps the contract explicit and observable; future prompt tweaks land via a single file edit that the snapshot test will flag.
- Low temperature reduces creative deviation from the JSON shape.
- `max_tokens=4096` is generous for a findings list (~80 findings of ~50 tokens each) and well under each default model's context.

**Alternatives**:
- Chain-of-thought (let the LLM reason in prose, then summarise to JSON): rejected — doubles the response size and makes parsing brittle.
- One big user prompt with system content inlined: rejected — Anthropic adapter from 002 already splits `system` to the top-level Messages parameter; conventional shape works on all three providers.

---

## R6: Timeout topology end-to-end?

**Decision**:
- **Backend `LLMProvider.chat`** call wrapped in `asyncio.wait_for(..., timeout=settings.REVIEW_LLM_TIMEOUT_S)` (default `60.0`).
- **GitHub fetch** uses `httpx.AsyncClient(timeout=10.0)`.
- **Endpoint** has no separate FastAPI-level timeout; uvicorn keeps the connection open as long as the handler runs.
- **Frontend** uses default `fetch` (no `AbortSignal.timeout`) so the browser doesn't cut off a slow but legitimate review.

LLM timeout → `provider_unavailable/timeout`. GitHub timeout → `github_fetch_failed/other`.

**Rationale**:
- 60 s comfortably covers `gpt-4o-mini` / `claude-3-5-sonnet-latest` cold-path latency on 200-line diffs (SC-001 target ≤ 30 s, with 2× safety margin).
- GitHub 10 s is generous for a 250 KB diff fetch over a healthy connection; failures are user-actionable.

**Alternatives**:
- Frontend-side `AbortSignal.timeout(45_000)`: rejected for MVP — would mask backend timeout categorisation. Revisit when we add async/queue.
- Per-provider timeout: deferred — defaults differ by model, but for MVP one knob is enough.

---

## R7: Where does request/response validation live?

**Decision**: Pydantic v2 BaseModel for all wire shapes: `ReviewRequest` (with `model_validator` enforcing exactly-one of `diff` or `pr_url`), `Finding`, `ReviewResult`. FastAPI auto-validates the request body and serialises responses. No separate JSON Schema files; the contract is the pydantic model.

**Rationale**:
- Pydantic is already in the stack (`pydantic-settings` transitively). No new dep.
- FastAPI's auto-422 on invalid request matches FR-013's `invalid_input` category — we wrap the default 422 in our error envelope via an exception handler.

**Alternatives**:
- Hand-written validation in the handler: rejected — duplicates effort, error-prone.
- `attrs` / `dataclasses_json`: rejected — pydantic is the FastAPI ecosystem default.

---

## R8: Error categories → HTTP status mapping

**Decision**: One enum (`ReviewErrorCategory`) maps to HTTP codes as follows. The wire shape is always `{"error": {"category": "<enum>", "message": "<human>", "retryable": <bool>}}`.

| Category                       | HTTP | Retryable? | Triggered by                                                          |
|--------------------------------|:----:|:----------:|-----------------------------------------------------------------------|
| `invalid_input`                | 400  | false      | empty body, both `diff` and `pr_url` set, neither set, non-diff blob, malformed PR URL |
| `payload_too_large`            | 413  | false      | `len(diff_bytes) > REVIEW_MAX_DIFF_BYTES`                             |
| `github_fetch_failed`          | 502  | false      | GitHub returned 401/403/404 or 5xx; subtype in `message`              |
| `provider_unavailable`         | 502  | true       | `ProviderError(retryable=True)` from feature 002 (rate-limit/timeout/5xx) |
| `provider_malformed_output`    | 502  | false      | LLM returned non-JSON, wrong shape, unknown severity                  |
| `internal`                     | 500  | false      | unexpected exception in the handler                                   |

**Rationale**:
- 502 for both `github_fetch_failed` and `provider_*` matches "the backend tried to call an upstream and failed"; the body's `category` disambiguates for the UI.
- `retryable: true` only when the upstream might transiently recover (rate-limit, 5xx, timeout); never for malformed output (deterministic bug).

**Alternatives**:
- Separate HTTP code per category (e.g. 504 for timeout, 503 for rate-limit): rejected — over-fits HTTP semantics; the UI keys on the structured `category` anyway.
- 422 for `invalid_input`: rejected — 422 is FastAPI's body-validation default and we wrap that into 400 with our envelope, for one consistent shape.

---

## R9: Severity colour scheme on the frontend?

**Decision**:
- `blocker` → red (`#dc2626`)
- `major` → orange (`#ea580c`)
- `minor` → yellow (`#ca8a04`)
- `nit` → grey (`#6b7280`)

Same Tailwind-ish palette as the health badges added in 002 (consistent visual language). All badges include a text label so colour is never the sole channel (accessibility).

**Rationale**: Matches the four-level severity in FR-007; ordering parallels the colour-warmth gradient users already read on the health page.

**Alternatives**: Two-level (blocker/non-blocker): rejected — collapses useful information that the LLM already produces. Five-level (add `info`): rejected — extra noise without product value for this MVP.

---

## R10: Do we ever retry the LLM on a transient error?

**Decision**: No retries in the review service for this MVP. Retryability is signalled in the response (`retryable: true` for `provider_unavailable`), and the UI surfaces a "try again" button. The reviewer manually re-submits.

**Rationale**:
- Server-side retries on a synchronous endpoint extend wall-clock time and risk client-side timeouts (SC-001 budget is 30 s).
- Centralised retry policy belongs in a later queue/worker feature (when we add `arq`), not in a sync handler.
- The user-visible "try again" interaction is more honest than a hidden retry loop.

**Alternatives**: One server-side retry with exponential back-off: rejected for MVP — adds latency variance, makes failures harder to diagnose.
