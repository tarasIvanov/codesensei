# Feature Specification: Ops & Quality Polish (queue, settings UI, prompt tune)

**Feature Branch**: `004-ops-quality-polish`
**Created**: 2026-05-17
**Status**: Draft
**Input**: User description: "004 Ops & quality polish before RAG — three orthogonal concerns in one feature: (1) arq + worker container scaffold; (2) Settings UI for runtime provider switching; (3) prompt tuning for the 003 review pipeline."

> **Note on scope**: This feature bundles three small-to-medium concerns into one delivery cycle. They share no business logic, but together they harden the product surface in preparation for the RAG indexing work (feature 005+). Each concern is captured as its own user story below — they are independently shippable, but the merge is one PR.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Async job queue is wired up and demonstrable (Priority: P1) 🎯

The operator running CodeSensei wants visible proof that the system's async job queue is set up and working, so that later features (indexing, long-running reviews, scheduled scans) can build on top of it without re-discovering basic plumbing. They expose a trivial "ping" job (it just returns the current timestamp), can enqueue it via an HTTP call, can poll its result by job-id, and can see a new badge on the health page reporting whether the worker process is alive.

**Why this priority**: P1 because (a) the project's constitution and ADR-005 have promised an async queue since day one but it doesn't exist yet — this closes that gap; (b) all future long-running work (RAG indexing, batch reviews) depends on the queue existing. Visible "ping job" is the smallest end-to-end slice that proves it works.

**Independent Test**: With the stack running, `POST /api/jobs/ping` returns a job-id; within a second or two, `GET /api/jobs/{id}` returns the timestamp the worker stamped. The new `worker` badge on the health page reads `ok`. Stopping the worker container flips the badge to `down`/`unreachable` without crashing the rest of the app.

**Acceptance Scenarios**:

1. **Given** the full stack is up, **When** the operator submits a ping-job request, **Then** they receive a job-id immediately and, on polling, see the job's result populated with a recent timestamp.
2. **Given** the worker is healthy, **When** the operator visits the health page, **Then** a new badge shows the worker's state and the page's overall status remains green.
3. **Given** the worker container is intentionally stopped, **When** the operator visits the health page, **Then** the worker badge shows it is down/unreachable and the overall status is **still** green (per the existing pattern for provider badges — worker is informational, not gating).
4. **Given** the operator polls a job-id that does not exist, **When** the lookup runs, **Then** the response is a clearly categorised "not found" error, not a generic 500.

---

### User Story 2 — Switch providers from a Settings page, without editing `.env` (Priority: P2)

The same operator wants to swap the active LLM provider (e.g. from OpenAI to Anthropic, or to a local Ollama instance), supply or rotate API keys, and tweak optional model overrides — all from the web UI, without SSHing to the host to edit `.env` and recreate the api container. After saving, the next review or health probe must pick up the new settings on its own.

**Why this priority**: P2 because it removes the most painful operational papercut left after 003 (need to recreate the api container to load a new key). It also pulls the project into line with the constitution's "switching providers MUST be a configuration change, not a code change" — and a Settings UI is what "configuration change" looks like to a non-developer.

**Independent Test**: Open `/settings`, change the **Active LLM provider** to one already configured with a key, click **Save**, then immediately run a review against the demo PR (US3 of feature 003). The review uses the newly selected provider — visible in the `provider` field of the review response — without restarting any container.

**Acceptance Scenarios**:

1. **Given** the operator has API keys stored, **When** they open the Settings page, **Then** they see the current active LLM provider, the current active embedding provider, and **redacted** versions of any stored API keys (the last four characters of each key are visible; the rest is masked).
2. **Given** the operator changes the active LLM provider and clicks Save, **When** the next review runs, **Then** the new provider is used — without restarting the API container.
3. **Given** the operator pastes a new API key into the form, **When** they click Save, **Then** the key is stored encrypted at rest and only the redacted form is ever readable from any API response or rendered page.
4. **Given** the operator clears an API key field (empties it explicitly), **When** they click Save, **Then** the stored key is removed (cleared, not blanked); subsequent probes of that provider report `unconfigured` again.
5. **Given** the master encryption secret is missing or invalid at startup, **When** the operator opens the Settings page, **Then** they see a clear "settings storage is locked — set MASTER_KEY before saving credentials" message; reads of redacted current settings still work because they're public-facing booleans/strings, but writes are blocked.

---

### User Story 3 — Review verdict severities are calibrated for real bugs (Priority: P3)

The reviewer (the developer pasting a PR URL into `/review` from feature 003) wants the severity tags on findings to reflect actual bug severity, especially for security-class defects. After running the existing demo PR through the reviewer, hardcoded credentials, SQL injection, and `eval()` of user input must come back tagged **blocker**, not **major**. Line numbers should also line up with the file's line numbers, not be shifted by N because the LLM is counting from the start of the diff.

**Why this priority**: P3 because it improves the product quality of an already-shipping feature (003) rather than unlocking anything new. Tactical polish.

**Independent Test**: Re-run the demo PR (the toy `samples/login_service.py` from PR #8) through `/review`. Expect the hardcoded API key, the SQL injection, and the `eval()` call to be reported as **blocker** severity. Expect the reported line numbers to land on the actual offending lines in the file, within ±1 line.

**Acceptance Scenarios**:

1. **Given** the operator re-runs the demo PR through `/review`, **When** the response renders, **Then** every finding that names a hardcoded credential, an SQL injection, an `eval` / `exec` / RCE vector, or a code-execution risk is tagged with the highest severity tier, not a milder one.
2. **Given** the operator re-runs the demo PR through `/review`, **When** they spot-check the reported line numbers against the actual file, **Then** the numbers refer to the file's own lines (matching what they'd see in a GitHub diff view), not offset by the diff header line count.
3. **Given** a parser-snapshot test of the system prompt is in place, **When** someone edits the prompt without updating the snapshot, **Then** the test fails — the prompt contract is the same kind of frozen artefact it was after 003.

---

### Edge Cases

- **Queue (US1)**: Redis is briefly unreachable while a job is enqueued → submission returns a clearly categorised error (not a hung request); enqueue is **not** retried automatically server-side (consistent with 003's "no hidden retries" rule).
- **Queue (US1)**: A job-id from a previous run is polled after the worker container has been restarted → returns "not found" rather than reviving stale state. Job results are short-lived (Redis-TTL bounded, e.g. one hour). The operator is not promised durable history.
- **Settings (US2)**: Two operators in two browser tabs both save different values at the same time → last-write-wins, the page reload shows the merged state. No optimistic-locking ceremony for a single-tenant MVP.
- **Settings (US2)**: The operator selects an embedding-provider value that is not supported (e.g. `EMBEDDING_PROVIDER=anthropic`, which feature 002 explicitly rejects) → the Save action is rejected with the exact same message feature 002 already surfaces, no silent acceptance.
- **Settings (US2)**: Encryption key (`MASTER_KEY`) is rotated → existing encrypted credentials become unreadable; the UI shows that affected credentials need to be re-entered, and the system **never** silently re-encrypts with the new key without the operator re-providing the secret.
- **Prompt (US3)**: A reviewer with a chatty LLM returns dozens of findings, including some on lines outside the diff (commentary on unchanged context) → those still render (already handled by 003) but should still be tagged with the new severity rules.

## Requirements *(mandatory)*

### Functional Requirements

**Async queue (US1)**

- **FR-001**: The system MUST run a dedicated worker process, separate from the API process, that executes background jobs from a queue.
- **FR-002**: The system MUST expose an endpoint that enqueues a trivial "ping" job and immediately returns a job identifier the operator can later use to look up the job's result.
- **FR-003**: The system MUST expose an endpoint that, given a job identifier, returns the job's current state (`pending` / `in_progress` / `complete` / `not_found`) and, when complete, the result payload.
- **FR-004**: The system MUST expose a new health-page badge that reports whether the worker process is reachable and consuming jobs.
- **FR-005**: The worker badge MUST follow the same "informational, not gating" rule established for provider badges in feature 002: its state contributes to the per-component breakdown but does **not** flip the overall health status.
- **FR-006**: When the queue's backing service (the same Redis already used by the rest of the system) is unreachable, the enqueue endpoint MUST surface a clearly categorised, machine-readable error and MUST NOT silently retry.
- **FR-007**: Job results MUST be retrievable for a bounded period after completion; older results MUST be discarded automatically. The exact retention is a configuration value; the default is a single-digit number of hours so a single-tenant deployment does not accumulate state forever.

**Settings UI (US2)**

- **FR-008**: The system MUST expose a Settings page in the SPA at `/settings` where the operator can view and edit the active LLM provider, the active embedding provider, and any provider-specific credentials and tuning knobs that the current adapter set understands (LLM model override, embedding model override, Ollama base URL).
- **FR-009**: The system MUST persist these settings durably so that they survive an api-container restart, **without** modifying the `.env` file on disk.
- **FR-010**: API credentials (every field that carries a secret) MUST be stored encrypted at rest using a symmetric key sourced from an environment variable; the plaintext value MUST never leave the database row in any direction except into the adapter call that consumes it.
- **FR-011**: Any read of stored settings (whether served to the UI, included in health probes, or returned by debug endpoints) MUST redact secret values down to a short fingerprint (no more than the last four characters); the full plaintext credential MUST NOT appear in any API response, log line, or rendered HTML.
- **FR-012**: Persisted settings MUST override the values from environment variables (`.env`) on the next factory-cache miss; existing call sites that go through the provider factory do not need code changes — the factory transparently consults the persisted store first.
- **FR-013**: When the operator submits a value that the adapter layer already rejects (e.g. an embedding provider with no embedding implementation), the system MUST reject the Save with the same exact category and message that the adapter would surface — no parallel validation tree.
- **FR-014**: When the encryption key is missing or invalid at startup, the system MUST refuse to write any new credential (clear, user-facing error) but MUST still allow reads of non-secret settings so the operator can see what's configured.
- **FR-015**: Clearing a credential field MUST delete the stored secret, not store an empty string under encryption; subsequent provider probes MUST then report that provider as unconfigured.

**Prompt tune (US3)**

- **FR-016**: The system prompt sent to the LLM during a review MUST explicitly instruct the model to tag any finding that describes a hardcoded credential, an SQL injection, an `eval`/`exec` of user input, a remote-code-execution vector, or an equivalent class of defect at the highest severity tier — not a milder tier.
- **FR-017**: The system prompt MUST explicitly anchor the meaning of "line number" to the new-file line numbering shown in the unified-diff hunk headers, so the model's numbers line up with what a human sees in a GitHub diff view.
- **FR-018**: The system prompt MUST include at least one worked example demonstrating the severity-calibration rule (a security-class finding marked at the highest severity, with its corresponding suggestion); the example MUST be inside the prompt itself, not in tests.
- **FR-019**: The snapshot-style test that pins the prompt's content (added in feature 003) MUST be updated so that the new content is locked in; any future drift from this new text MUST fail the test.

**Constraints carried over from 002 / 003**

- **FR-020**: This feature MUST NOT introduce a new direct dependency on any specific LLM vendor SDK outside the adapter layer established in feature 002. All provider switching goes through the existing adapter contract.
- **FR-021**: This feature MUST NOT break the single-command `docker compose up` deployment contract. Any new long-running process is a new compose service; any new credential lives in `.env.example` with an empty default; nothing requires host-side manual setup.
- **FR-022**: The new queue and Settings UI MUST NOT log or surface secret values (credentials, master keys, redis URLs that embed passwords) in any error message, response body, or log line.

### Key Entities

- **PingJob**: A trivial background job whose only purpose is to demonstrate the queue is alive. Attributes: a job-id, a submission timestamp, a completion timestamp, the resulting "pong" payload (e.g. the current UTC time).
- **JobStatus**: A simple state machine for any background job: `pending → in_progress → complete`, plus `not_found` as a lookup outcome. Used for both ping (US1) and any future job class.
- **AppSetting**: A single persisted configuration entry. Attributes: a stable key (matching the known set of provider/model environment variables), a value, an "is-secret" flag that controls whether the value is encrypted at rest and redacted on read, and a timestamp of last update.
- **Worker probe result**: The shape returned by the new health-page badge: a state of `ok` / `unreachable` (no fourth state, no spinner state besides the existing client-side `pending`).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An operator can enqueue a ping job and poll its result within 5 seconds end-to-end, on a default deployment, with no other load on the queue.
- **SC-002**: Stopping the worker container produces a visible "worker down" signal on the health page within 5 seconds and does not flip the overall status to red.
- **SC-003**: An operator can swap the active LLM provider from one configured option to another by filling in a single form and clicking Save — no terminal, no file edit, no container restart. The next review uses the new provider.
- **SC-004**: No stored credential field is ever returned in full from any API response or rendered page; only a redacted fingerprint is visible. This is verifiable by grep across all observable surfaces.
- **SC-005**: After re-running the demo PR (the toy `samples/login_service.py`) through the reviewer, every finding that describes a hardcoded credential, an SQL injection, or an `eval` of user input is tagged at the highest severity tier — improved from the post-003 baseline of "all such findings tagged at the middle tier".
- **SC-006**: After re-running the demo PR through the reviewer, the reported line numbers land on the actual offending lines in the file, within ±1 line (improved from the post-003 baseline drift of ~6–7 lines).

## Assumptions

- The existing single-tenant, single-user deployment shape from features 001/002/003 is unchanged — no auth, no per-user state.
- The queue's backing store is the same Redis instance already wired by 001; no new datastore is introduced.
- The master encryption secret is supplied by the operator at deploy time, the same way other secrets are supplied today (an environment variable read at api-container startup). Key rotation, key escrow, and HSM-style management are out of scope.
- The Settings UI does not attempt to validate keys by calling the upstream provider — it accepts the values, persists them, and lets the next real call surface any vendor-side issue. (Adding a "test connection" button is a nice-to-have that is **not** in scope for this feature.)
- The prompt-tune story improves the existing `/review` page from feature 003; it does not introduce a new page or change the request/response contract for `POST /api/review`.
- Settings written through the UI override `.env` values on the next provider-factory cache miss. The cache is short-lived (per-request lifetime in practice for this codebase), so "next miss" effectively means "next call after Save". No explicit cache-invalidation API is exposed in this feature.
- Job result retention is bounded by Redis TTL on the result key; long-term audit history of jobs is **not** in scope.
- The new queue is **not** wired into the existing `POST /api/review` endpoint in this feature; reviews remain synchronous. The queue exists only to be exercised by the ping job and to be ready for the indexing work in feature 005.
