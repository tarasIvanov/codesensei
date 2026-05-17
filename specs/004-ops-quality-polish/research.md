# Phase 0 — Research Notes (004-ops-quality-polish)

Each entry resolves a NEEDS-CLARIFICATION raised in `plan.md`. Format: **Decision → Rationale → Alternatives**.

---

## R1: arq version + worker invocation pattern

**Decision**: Pin `arq>=0.26`. Worker entrypoint is `arq codesensei.tasks.worker.WorkerSettings`, run as the `command:` of a new `worker` compose service reusing the existing `codesensei-api:dev` image. `WorkerSettings.functions = [ping_job]`; `redis_settings` built from `settings.redis_url` via `arq.connections.RedisSettings.from_dsn(...)`; `keep_result_seconds = settings.job_result_ttl_s` (default 3600).

**Rationale**:
- `arq>=0.26` is the current stable line, async-native, no Celery-style separate broker.
- Same image as `api` means a single Dockerfile + a single `uv sync`; the worker just runs a different command.
- `from_dsn` keeps us aligned with how 001's healthcheck consumes `REDIS_URL`.

**Alternatives**:
- Celery: rejected — sync-first, separate broker abstraction, heavier image.
- RQ: rejected — sync-only handlers, awkward with async FastAPI.
- Plain Redis lists + custom worker: rejected — reinventing `arq`.

---

## R2: ADR-007 — confirm arq+Redis as the queue

**Decision**: Add **ADR-007** to `../_decision_log.md`:

```
### ADR-007: Async task queue — arq + Redis
- Date: 2026-05-17
- Status: accepted
- Decision: Background jobs run on `arq>=0.26` workers backed by the same Redis instance already used for other state.
- Why: Closes the TBD in ADR-005's "Open decisions" footnote. arq is async-native (matches §Async-by-default), shares Redis with the rest of the stack (no new compose service for a broker), and survives the `docker compose up` single-command contract.
- Notes: Worker runs as a separate compose service reusing `codesensei-api:dev`. Job results have a default TTL of 1 hour (configurable). The MVP queue is not yet wired into `/api/review` — that's deferred to feature 005+.
```

**Rationale**: Constitution §II requires an ADR for "queue system" changes; this is a confirmatory ADR closing the §Stack TBD.

**Alternatives**: leave the TBD open; rejected — implementation without ADR violates §II.

---

## R3: Symmetric encryption library for stored credentials

**Decision**: `cryptography>=44`'s `Fernet`. Encryption algorithm: AES-128-CBC + HMAC-SHA256 (Fernet spec). Keys are 32 bytes, url-safe base64 encoded.

**Rationale**:
- `cryptography` is the de-facto Python crypto lib, packaged in major distros, broadly audited.
- `Fernet` provides authenticated encryption (AES-CBC + HMAC) in a single primitive — no plaintext-without-MAC pitfalls.
- No new transitive deps beyond what `cryptography` already brings.

**Alternatives**:
- PyNaCl `SecretBox`: rejected — adds libsodium native dep, comparable feature set, fewer ecosystem ergonomics for key rotation.
- `age`-style asymmetric: rejected — we have a single-tenant single-key model; asymmetric is overkill.
- Roll your own AES-GCM: rejected — every implementation diary has a story about getting nonces wrong.

---

## R4: `MASTER_KEY` format and missing-key behaviour

**Decision**:
- **Format**: 32 bytes, url-safe base64 encoded — i.e. exactly what `Fernet.generate_key().decode()` produces.
- **Source**: read once at api startup from env var `MASTER_KEY`. Stored in `Settings.master_key: str = ""`.
- **Missing key behaviour**: any `POST /api/settings` that includes a secret field raises `SettingsError(category=settings_locked, retryable=false)` → HTTP 503. Reads of non-secret settings (`GET /api/settings`) still work and the affected secret fields appear as `null` (interpreted by UI as "not configured").
- **Bad key behaviour**: decryption failures on existing rows produce `null` in the redacted view and a `WARNING` log; never crash a request.

**Rationale**: matches Constitution IV exactly ("API keys ... encrypted-at-rest"); refusing **writes** without a key blocks new-credential leaks; allowing **reads** keeps the Settings page diagnostic instead of fully broken.

**Alternatives**:
- Fail-closed for reads too: rejected — a stale `MASTER_KEY` rotation would lock the operator out of the page entirely; bad UX.
- Auto-generate `MASTER_KEY` on first start: rejected — silently inventing keys hides the secret in a container layer; operator must own this.

---

## R5: Whitelist of `app_settings` keys

**Decision**: The store accepts **only** these keys (others rejected at the API layer with `invalid_input`):

| Key                   | `is_secret` |
|-----------------------|:-----------:|
| `LLM_PROVIDER`        | false       |
| `EMBEDDING_PROVIDER`  | false       |
| `LLM_MODEL`           | false       |
| `EMBEDDING_MODEL`     | false       |
| `OLLAMA_BASE_URL`     | false       |
| `OPENAI_API_KEY`      | true        |
| `ANTHROPIC_API_KEY`   | true        |
| `GITHUB_TOKEN`        | true        |

Keys outside this set → `invalid_input` from the POST handler.

**Rationale**: matches the existing `Settings` env-var surface from 001/002/003. Whitelisting prevents the Settings UI from becoming a generic key/value store. The set is small and stable; adding a new key in a future feature is one whitelist entry.

**Alternatives**: free-form key acceptance — rejected, opens the door to misuse and grep-unfriendly storage.

---

## R6: Factory cache invalidation after `POST /api/settings`

**Decision**:
- The provider factories use a new module-level `_settings_revision: int` counter and a closure cache keyed on `(revision, llm_provider, embedding_provider)`. `POST /api/settings` bumps the counter; the next factory call rebuilds.
- For pydantic `get_settings()` (env-only): cleared via `get_settings.cache_clear()` at the end of a successful `POST /api/settings`.
- Provider factory now does: `settings_store.get_effective_settings()` → merge with env → instantiate. Effective-settings function reads `app_settings` once per call (cheap; ~8 rows, single SELECT).

**Rationale**: cache is short-lived (per-request lifetime in practice for FastAPI). Bumping a revision counter + `cache_clear()` is the minimal invalidation needed; no pub/sub between processes required since FastAPI runs single-process for our deployment shape.

**Alternatives**:
- Redis-backed signal (`SUBSCRIBE` channel): rejected — premature; single-process api.
- Restart-on-save: rejected — defeats SC-003 ("no container restart").

---

## R7: Worker liveness probe

**Decision**: arq writes a heartbeat key to Redis (`arq:health-check:default` by default, configurable). `probe_worker()` reads this key with a 1-second timeout and parses the timestamp. Result mapping:
- key fresh (< `worker_heartbeat_stale_s`, default 60s) → `ok`
- key stale or missing → `down`
- redis unreachable → `unreachable`

The badge is informational, like the provider badges from 002: it never flips `status` or appears in `failing[]`.

**Rationale**: no new connection to the worker process from the api; we read the same Redis the worker writes to. Failure-modes (worker crashed but redis up vs both down) are distinguishable in the badge.

**Alternatives**:
- HTTP healthcheck on worker container: rejected — workers don't speak HTTP and adding a sidecar HTTP server is over-engineering.
- Test-enqueue a probe job every 30s: rejected — pollution of the queue with synthetic work.

---

## R8: Job result TTL default

**Decision**: `JOB_RESULT_TTL_S = 3600` (1 hour). Configurable via env. Tighter than arq's library default of 1 day; bounds local storage growth.

**Rationale**: matches FR-007 ("single-digit hours"); 1 hour is enough for an operator to enqueue, walk away, and return to find results; older results have no business value in a synchronous MVP.

**Alternatives**: 24h (arq default) — rejected, accumulates state on a long-lived single-tenant box; 5 min — rejected, too tight if the demo gets interrupted.

---

## R9: ADR-008 — encrypted-settings persistence

**Decision**: Add **ADR-008** to `../_decision_log.md`:

```
### ADR-008: Persisted app settings via `app_settings` table + Fernet
- Date: 2026-05-17
- Status: accepted
- Decision: Per-deployment user-facing settings (active LLM/embedding provider, model overrides, API keys) live in a `app_settings(key, value, is_secret, updated_at)` table. Secrets are encrypted with Fernet keyed on env-supplied `MASTER_KEY`. Settings override `.env` at provider-factory cache invalidation time.
- Why: Closes the gap with Constitution III's "Settings UI" requirement and IV's "encrypted-at-rest" rule. Persistent across container restarts; rotatable from the UI; never serialised to the frontend except as redacted (last-4-chars) fingerprints.
- Notes: `MASTER_KEY` lives only in env (never persisted). Bad/missing key blocks credential WRITES, not reads. Whitelisted key set is small and stable; expanding requires only a code-side whitelist entry.
```

**Rationale**: §II requires an ADR for "AI provider config" surfaces; this is the first time we persist provider config outside `.env`. ADR-008 is its charter.

**Alternatives**: keep settings env-only — rejected, contradicts §III's "Settings UI" requirement.

---

## R10: Prompt-tune delta + snapshot-test update

**Decision**: The new SYSTEM string is the 003 SYSTEM string + three additions, appended **inside** the existing rule list:

1. After rule 3 (severity meanings), insert a new rule **3a — Blocker tier**:
   > "Findings that describe any of the following MUST use severity `blocker`: hardcoded credentials or API keys; SQL injection (string concatenation into a SQL query); `eval()` / `exec()` / `compile()` of user input; deserialisation of untrusted data; remote-code-execution vectors; arbitrary-shell-command execution. Do not downgrade these to `major`."
2. After existing rule 5 (base findings on real changes), insert **5a — Line-number anchor**:
   > "The `line` field in every finding MUST refer to the new-file line number visible in the diff's `@@ -A,B +C,D @@` hunk headers, not to a position inside the diff text. If the diff shows `@@ -0,0 +1,71 @@` then the first added line in that hunk is line 1 of the new file."
3. Append a new section **Example** at the end of SYSTEM:

   ```
   Example finding for a hardcoded credential:
   {"verdict": "request_changes", "findings": [{
       "file": "samples/login_service.py",
       "line": 14,
       "severity": "blocker",
       "message": "ADMIN_API_KEY is hardcoded at module level. Anyone with read access to source can extract it.",
       "suggestion": "ADMIN_API_KEY = os.environ['ADMIN_API_KEY']"
   }]}
   ```

USER template, parser contract, and `LLMProvider.chat(...)` call-args are unchanged.

**Snapshot test update**: `test_review_prompt.py::test_system_message_starts_with_role` keeps passing. Add new pins: `assert "severity `blocker`" in SYSTEM_MESSAGE` (catches future drift), `assert "new-file line number" in SYSTEM_MESSAGE`, `assert "Example finding for a hardcoded credential" in SYSTEM_MESSAGE`. The whole SYSTEM string is **not** hash-snapshotted (overly brittle for prompt iteration); we pin only the rules whose absence is a regression.

**Rationale**:
- Two rules + one example is the smallest addition that addresses both severity miscalibration (R3-derived SC-005) and line-number drift (SC-006).
- Snapshot-pinning *content fragments* instead of *full hashes* keeps the test maintainable when we tweak the example wording later.

**Alternatives**:
- Few-shot with multiple examples (RCE, SQLi, eval) — rejected for MVP, increases token usage on every review without proportional quality gain; one example is enough to calibrate.
- Full SHA snapshot of SYSTEM_MESSAGE — rejected, every typo fix breaks the test.
