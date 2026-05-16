# Phase 1 — Data Model (003-pr-review-mvp)

All entities are **in-memory only** for the duration of one HTTP request. Nothing in this feature touches Postgres or Redis. Models live in `backend/src/codesensei/review/schema.py` (pydantic v2 `BaseModel`) and `errors.py` (`StrEnum`).

---

## `ReviewRequest` (request body)

| Field      | Type          | Required | Constraints                                                         |
|------------|---------------|----------|---------------------------------------------------------------------|
| `diff`     | `str \| None` | one-of   | Non-empty; valid UTF-8; contains at least one of `diff --git ` or matching `--- a/` + `+++ b/` line pair |
| `pr_url`   | `str \| None` | one-of   | Matches `^https://github\.com/[^/]+/[^/]+/pull/\d+$`                |

**Validation rules**:
- Exactly one of `diff` or `pr_url` MUST be present (`model_validator(mode="after")`). Both-present or both-absent → `invalid_input`.
- `diff` (or the diff fetched via `pr_url`) MUST satisfy `len(encoded_bytes) <= REVIEW_MAX_DIFF_BYTES`; exceeding → `payload_too_large`. The size check applies to **bytes**, not characters, so multi-byte content does not bypass the guard.

---

## `Severity` (enum)

`StrEnum` with members: `blocker`, `major`, `minor`, `nit`. Used in `Finding.severity`. Any other value in LLM output → `provider_malformed_output`.

---

## `Verdict` (enum)

`StrEnum` with members: `approve`, `request_changes`, `comment`. Mirrors the three states a human reviewer can pick on a GitHub PR review. Unknown value in LLM output → `provider_malformed_output`.

---

## `Finding`

| Field        | Type            | Required | Notes                                                            |
|--------------|-----------------|----------|------------------------------------------------------------------|
| `file`       | `str`           | yes      | Non-empty; path is taken verbatim from the LLM (we do not normalise against the diff). |
| `line`       | `int \| None`   | yes      | `int` when the finding is line-specific; `None` for file-level comments. Negative or zero → `provider_malformed_output`. |
| `severity`   | `Severity`      | yes      | See enum above.                                                  |
| `message`    | `str`           | yes      | Non-empty, ≤ 2000 chars (oversize → truncated server-side with a `…` suffix; we never raise on long messages so a chatty model doesn't break the endpoint). |
| `suggestion` | `str \| None`   | no       | Optional concrete code change. ≤ 4000 chars; same truncation rule. |

---

## `ReviewResult` (success response body)

| Field         | Type            | Required | Notes                                                          |
|---------------|-----------------|----------|----------------------------------------------------------------|
| `verdict`     | `Verdict`       | yes      | Top-level summary from the LLM.                                |
| `findings`    | `list[Finding]` | yes      | May be empty (clean diff). Ordering preserved from LLM output. |
| `provider`    | `str`           | yes      | Echoes `LLMProvider.name` (e.g. `"openai"` / `"anthropic"` / `"ollama"`). |
| `elapsed_ms`  | `int`           | yes      | Wall-clock time from "received" to "response built", in milliseconds. |

---

## `ReviewErrorCategory` (enum)

`StrEnum` with members:

| Member                       | HTTP | `retryable` default | Meaning                                                        |
|------------------------------|:----:|:-------------------:|----------------------------------------------------------------|
| `invalid_input`              | 400  | false               | request body fails `ReviewRequest` validation                  |
| `payload_too_large`          | 413  | false               | diff bytes > `REVIEW_MAX_DIFF_BYTES`                           |
| `github_fetch_failed`        | 502  | false               | GitHub returned non-2xx or the fetch threw                     |
| `provider_unavailable`       | 502  | true                | `ProviderError(retryable=True)` or `LLM timeout`               |
| `provider_malformed_output`  | 502  | false               | LLM output failed JSON parse or pydantic validation            |
| `internal`                   | 500  | false               | unexpected exception                                           |

---

## `ReviewError` (error response body)

| Field        | Type                    | Required | Notes                                                         |
|--------------|-------------------------|----------|---------------------------------------------------------------|
| `error.category`    | `ReviewErrorCategory` | yes  | Machine-readable; frontend keys off this.                     |
| `error.message`     | `str`                | yes  | Human-readable, safe for direct display (never includes credentials, diff bytes, stack frames). |
| `error.retryable`   | `bool`               | yes  | UI uses this to decide whether to enable a "Try again" button. |

Wire shape (always):

```json
{"error": {"category": "...", "message": "...", "retryable": false}}
```

---

## Settings additions (`codesensei.config.Settings`)

| Field                       | Type   | Default                | Purpose                                                  |
|-----------------------------|--------|------------------------|----------------------------------------------------------|
| `review_max_diff_bytes`     | `int`  | `256_000`              | Server-side cap; over → `payload_too_large`.             |
| `review_llm_timeout_s`      | `float`| `60.0`                 | `asyncio.wait_for` on `LLMProvider.chat`.                |
| `github_token`              | `str`  | `""`                   | Optional. Absent → only public PR URLs work; private/private-repo PRs error with `github_fetch_failed/auth`. |

All three follow the same env-var convention established in 001/002 (`pydantic-settings`, uppercased name). `.env.example` updated.

---

## Persistence

**None.** No SQLAlchemy models, no alembic migration, no Redis writes. FR-018 is enforced at the structural level — there is no place in the code that opens a session or a redis connection for this feature.
