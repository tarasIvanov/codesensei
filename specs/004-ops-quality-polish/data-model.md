# Phase 1 — Data Model (004-ops-quality-polish)

This feature introduces **one new database table**, **two in-memory request/response shapes**, and **one new probe-result shape**. All other state (job queue, job results, worker heartbeat) lives in Redis with TTL and is not persisted to Postgres.

---

## `AppSetting` (new table — `app_settings`)

| Column        | Type                       | Notes                                                                       |
|---------------|----------------------------|-----------------------------------------------------------------------------|
| `key`         | `TEXT PRIMARY KEY`         | One of the whitelisted keys from research R5. Validated at the API layer.   |
| `value`       | `TEXT NOT NULL`            | For `is_secret = false`: stored plaintext. For `is_secret = true`: Fernet-encrypted ciphertext (base64). |
| `is_secret`   | `BOOLEAN NOT NULL`         | Drives both encryption-at-write and redaction-on-read.                      |
| `updated_at`  | `TIMESTAMPTZ NOT NULL`     | `default now()` on insert; bumped on update.                                |

**Whitelist** (mirrors research R5):

| Key                  | `is_secret` |
|----------------------|:-----------:|
| `LLM_PROVIDER`       | false       |
| `EMBEDDING_PROVIDER` | false       |
| `LLM_MODEL`          | false       |
| `EMBEDDING_MODEL`    | false       |
| `OLLAMA_BASE_URL`    | false       |
| `OPENAI_API_KEY`     | true        |
| `ANTHROPIC_API_KEY`  | true        |
| `GITHUB_TOKEN`       | true        |

**Migration**: `backend/alembic/versions/002_app_settings.py` creates the table and an empty (no seed) initial state.

**Redaction rule for reads**: when `is_secret = true`, the value returned by the store's `redacted()` accessor is `"…" + decrypted_value[-4:]` if the row exists **and** decryption succeeds; `null` if missing or decryption fails. Raw plaintext NEVER leaves the store except into the provider factory.

---

## `SettingsState` (response shape for `GET /api/settings`)

```json
{
  "active_llm_provider": "openai",
  "active_embedding_provider": "openai",
  "llm_model": "",
  "embedding_model": "",
  "ollama_base_url": "http://ollama:11434",
  "credentials": {
    "openai_api_key":   {"set": true,  "fingerprint": "…cdef"},
    "anthropic_api_key":{"set": false, "fingerprint": null},
    "github_token":     {"set": false, "fingerprint": null}
  },
  "master_key_present": true
}
```

- `master_key_present` reflects whether `Settings.master_key` is non-empty; it does NOT reveal the key.
- `credentials.<name>.fingerprint` is the redaction described above; never the full key.

---

## `SettingsUpdate` (request shape for `POST /api/settings`)

```json
{
  "active_llm_provider": "anthropic",
  "anthropic_api_key": "sk-ant-...new-value..."
}
```

- All fields **optional**. Only included fields are written; others are untouched.
- A field with an empty-string value **deletes** the stored entry (per FR-015).
- Unknown fields (outside the whitelist) → 400 `invalid_input` with the rejected field name in the message.
- Same validation as feature 002's factory applies — e.g. `active_embedding_provider: "anthropic"` is rejected with the exact same message feature 002 already surfaces, no parallel validation tree.

---

## `WorkerProbeResult` (probe shape for healthz)

```python
@dataclass(frozen=True)
class WorkerProbeResult:
    state: Literal["ok", "down", "unreachable"]
    last_heartbeat_at: datetime | None
```

The healthz envelope grows a `worker` field of type `Literal["ok", "down", "unreachable"]`. `last_heartbeat_at` is **not** exposed on the API (informational only, kept in-process for logs).

**Envelope (additive change)**:

```json
{
  "status": "ok",
  "db": "ok",
  "redis": "ok",
  "extensions": {"vector": "ok"},
  "providers": {"llm": "ok", "embedding": "ok"},
  "worker": "ok"
}
```

FR-005 reaffirmed: `worker` state does NOT contribute to `failing[]` or to overall `status`.

---

## `PingJobResult` (job payload — Redis-only, no Postgres row)

`arq` stores the function's return value under a Redis key with TTL `settings.job_result_ttl_s`. Our `ping_job` returns:

```python
{
    "stamped_at": "2026-05-17T12:34:56.789Z",  # ISO-8601 UTC
}
```

Job-lookup response shape (built by `GET /api/jobs/{id}`):

```json
{
  "job_id": "0123abcd…",
  "status": "complete",
  "submitted_at": "2026-05-17T12:34:55.901Z",
  "completed_at": "2026-05-17T12:34:56.789Z",
  "result": {"stamped_at": "2026-05-17T12:34:56.789Z"}
}
```

`status` ∈ `{"pending", "in_progress", "complete", "not_found"}`. For `not_found`, the response body's status is `not_found` and HTTP code is **404** (consistent with API ergonomics; this is **not** an error category in the `ReviewError` envelope sense).

---

## `JobError` (error envelope)

Reuses the **shape** of feature 003's `ReviewError` envelope to keep the API uniform:

```json
{"error": {"category": "queue_unavailable", "message": "Redis is not reachable.", "retryable": true}}
```

Categories specific to this feature:

| Category               | HTTP | Retryable | Triggered by                                                  |
|------------------------|:----:|:---------:|---------------------------------------------------------------|
| `invalid_input`        | 400  | false     | unknown setting key; malformed JSON body; bad job_id format    |
| `queue_unavailable`    | 502  | true      | Redis unreachable when enqueuing or polling                    |
| `settings_locked`      | 503  | false     | secret write attempted with no/invalid `MASTER_KEY`            |
| `internal`             | 500  | false     | unexpected error in the handler                                |

`ReviewError` from feature 003 is still in use for the `/review` endpoint; this feature does not change it.

---

## Settings additions (`codesensei.config.Settings`)

| Field                          | Type    | Default     | Purpose                                                |
|--------------------------------|---------|-------------|--------------------------------------------------------|
| `master_key`                   | `str`   | `""`        | Fernet-compatible 32-byte url-safe base64 key.         |
| `worker_heartbeat_stale_s`     | `int`   | `60`        | `worker` badge goes `down` if heartbeat older.         |
| `job_result_ttl_s`             | `int`   | `3600`      | Redis TTL applied by arq's `keep_result_seconds`.      |

All follow the pydantic-settings env-var pattern (`MASTER_KEY=…` etc.), defaulted to safe values, documented in `.env.example`.

---

## Migration check-list

- `002_app_settings.py` is forward-only safe — empty table addition.
- Downgrade: drop the table; no fk dependents.
- 003's `feature.json` already points at `specs/003-pr-review-mvp/`; this feature flips it to `specs/004-ops-quality-polish/` (already done at spec-creation time).
