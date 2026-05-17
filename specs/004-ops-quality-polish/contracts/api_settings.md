# Contract — `GET /api/settings` + `POST /api/settings`

Operator-facing CRUD for the small set of provider/model/credential settings. Reads are redacted; writes encrypt secrets at rest.

---

## `GET /api/settings`

### Success — `200 OK`

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

- `active_llm_provider` / `active_embedding_provider` come from `app_settings` if present, else from env (`Settings.llm_provider` / `embedding_provider`).
- `llm_model`, `embedding_model`, `ollama_base_url` — same precedence: db row beats env.
- `credentials.<name>.set` is `true` iff a non-empty row exists in `app_settings` for that key.
- `credentials.<name>.fingerprint` is `null` when `set: false`, else `"…" + decrypted_value[-4:]`. If decryption fails (bad/rotated `MASTER_KEY`), `set: true, fingerprint: null` and a server-side WARNING is logged.
- `master_key_present` mirrors `bool(Settings.master_key)`; the value is **never** in the response.

### Errors

- `502 queue_unavailable` is NOT relevant here (this endpoint only touches Postgres and process env).
- `500 internal` on unexpected error.

---

## `POST /api/settings`

### Request body

All fields are optional. Empty string for any field **deletes** the corresponding row from `app_settings` (FR-015).

```json
{
  "active_llm_provider": "anthropic",
  "anthropic_api_key": "sk-ant-...",
  "openai_api_key": ""
}
```

(In this example the operator switches LLM to Anthropic, sets a new Anthropic key, and clears the OpenAI key.)

**Whitelisted fields** (any other key → `400 invalid_input`):

`active_llm_provider`, `active_embedding_provider`, `llm_model`, `embedding_model`, `ollama_base_url`, `openai_api_key`, `anthropic_api_key`, `github_token`.

### Validation rules

- `active_llm_provider` ∈ `{openai, anthropic, ollama}`; trimmed + lowercased.
- `active_embedding_provider` ∈ `{openai, ollama}` — `anthropic` rejected with the exact same message feature 002 already surfaces (`EMBEDDING_PROVIDER=anthropic is not supported because Anthropic has no embeddings API; accepted values: openai, ollama`).
- `ollama_base_url`, when present, must be a valid HTTP/HTTPS URL.
- Secret writes (`*_api_key`, `github_token`) require `Settings.master_key` to be non-empty and a valid Fernet key. Missing/invalid → `503 settings_locked`.

### Success — `200 OK`

Returns the **same shape** as `GET /api/settings`, reflecting the post-write state. The provider factory cache is invalidated **before** the response is built, so the next call sees the new values.

### Errors

| HTTP | category            | Triggered by                                                              |
|-----:|---------------------|---------------------------------------------------------------------------|
|  400 | `invalid_input`     | unknown field; bad provider value; malformed URL                          |
|  503 | `settings_locked`   | secret field present, `MASTER_KEY` missing/invalid                        |
|  500 | `internal`          | unexpected exception                                                      |

Error body shape mirrors feature 003's envelope:

```json
{"error": {"category": "settings_locked", "message": "…", "retryable": false}}
```

---

## Logging

Per request, exactly one structured line:

- `event="settings.read"` on GET (no payload content).
- `event="settings.updated"` on successful POST, with **only** the set of `keys_set` and `keys_cleared` (lists of whitelisted field names) — **never** values.
- `event="settings.failed"` with `error_category` on failure.

The full plaintext of any secret never appears in any log line, response, or error message (FR-022).

---

## Concurrency

Last-write-wins. No optimistic locking. Two concurrent POSTs may interleave per-key; consistent (each key is its own row), but the visible state after both calls is the merge of their writes in arrival order.
