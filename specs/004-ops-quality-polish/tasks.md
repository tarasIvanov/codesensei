---

description: "Task list — 004-ops-quality-polish"
---

# Tasks: Ops & Quality Polish (queue, settings UI, prompt tune)

**Input**: Design documents from `/specs/004-ops-quality-polish/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/api_jobs.md, contracts/api_settings.md, contracts/healthz_worker.md, contracts/llm_prompt_v2.md, quickstart.md

**Tests**: INCLUDED. Constitution §test-first names "parsing structured LLM output" (still in scope for the prompt-v2 snapshot test) and treats new critical paths the same way; here that extends to crypto (Fernet round-trip) and the settings store (CRUD + redaction). Trivial plumbing (router registration, compose service add, frontend topnav link) is exempt.

**Organization**: Tasks grouped by user story (US1 queue P1, US2 settings P2, US3 prompt P3). Each story is independently demonstrable per `spec.md`.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Different file from other [P] tasks in the same group → safe to parallelise
- **[Story]**: Maps to US1/US2/US3 from `spec.md`
- Paths follow the web-app layout from 001–003: `backend/src/codesensei/`, `frontend/src/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project-level scaffolding before any production code lands. Two ADRs are part of this phase because Constitution §II requires them **before** implementation.

- [X] T001 Add `arq>=0.26` and `cryptography>=44` to the main `dependencies` block of `backend/pyproject.toml`; run `uv lock` from `backend/` to refresh the lockfile.
- [X] T002 [P] Append three settings fields to `backend/src/codesensei/config.py`: `master_key: str = ""`, `worker_heartbeat_stale_s: int = 60`, `job_result_ttl_s: int = 3600`.
- [X] T003 [P] Extend `.env.example` with a new "Ops & quality (004)" section containing `MASTER_KEY=`, `WORKER_HEARTBEAT_STALE_S=`, `JOB_RESULT_TTL_S=` — all values blank so the defaults from `config.py` apply.
- [X] T004 Append **ADR-007** ("Async task queue — arq + Redis") to `../_decision_log.md` using the verbatim text from `research.md` R2.
- [X] T005 Append **ADR-008** ("Persisted app settings via `app_settings` table + Fernet") to `../_decision_log.md` using the verbatim text from `research.md` R9.

**Checkpoint**: Backend has new deps and three new settings; ADR-007 + ADR-008 are merged into the decision log. No new code yet; nothing observable from the outside.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Migration + crypto primitive + envelope-shape stub. Every user story below needs at least one of these.

**⚠️ CRITICAL**: No US-tagged task may start until Phase 2 finishes.

- [X] T006 Create alembic revision `backend/alembic/versions/002_app_settings.py`: `upgrade()` creates `app_settings(key text primary key, value text not null, is_secret bool not null, updated_at timestamptz not null default now())`; `downgrade()` drops the table. Set `down_revision = "001_enable_pgvector"`.
- [X] T007 [P] Create `backend/src/codesensei/settings_store/__init__.py` (empty package init).
- [X] T008 [P] Create `backend/src/codesensei/settings_store/models.py` with the SQLAlchemy 2.x async-style `AppSetting` mapped class targeting the `app_settings` table per `data-model.md`.
- [X] T009 [P] Create `backend/src/codesensei/settings_store/crypto.py` exposing `encrypt(plaintext: str) -> str`, `decrypt(ciphertext: str) -> str`, and `is_master_key_valid() -> bool`. Each function reads `settings.master_key` lazily; missing-key behaviour matches `research.md` R4. Define a `SettingsCryptoError` sentinel raised on missing/invalid key during `encrypt(...)`.
- [X] T010 [P] Create `backend/src/codesensei/tasks/__init__.py` (empty package init).
- [X] T011 Patch `backend/src/codesensei/healthcheck.py`: add `worker: Literal["ok", "down", "unreachable"]` to the envelope returned by `build_envelope(...)` and append it to the per-component summary, with a default placeholder `"unreachable"`. The real probe lands in T020 — for now `build_envelope` accepts a `worker_state` argument that defaults to that placeholder, and the existing handler keeps passing it through.
- [X] T012 [P] Update `backend/tests/unit/test_healthcheck_logic.py` to pass the new `worker_state` kwarg in `build_envelope` calls; assert FR-005 (worker state never enters `failing[]`, never flips `status`). Run; should pass after T011.

**Checkpoint**: DB has `app_settings`; crypto helpers compile against tests; healthz envelope shape has `worker` but always reports `"unreachable"` until US1 wires the probe.

---

## Phase 3: User Story 1 — Async job queue is wired up and demonstrable (Priority: P1) 🎯

**Goal**: `POST /api/jobs/ping` enqueues, `GET /api/jobs/{id}` polls, `worker` badge on `/healthz` reads `"ok"`. Stop the worker container → badge flips `"down"` without affecting overall status.

**Independent Test** (spec US1): with stack up, enqueue ping; within 5 s poll returns `complete` + a timestamp. Stop `worker` service; healthz `worker` reads `down` within `worker_heartbeat_stale_s + ~5s`; `status` stays `ok`.

### Tests for User Story 1 (write FIRST)

- [X] T013 [P] [US1] `backend/tests/unit/test_tasks_ping.py`: import `ping_job` from `tasks.ping`; call with a stub `ctx`; assert returns `{"stamped_at": <ISO-8601 string in UTC>}` and that the timestamp is within ±2s of `datetime.now(timezone.utc)`.
- [X] T014 [P] [US1] `backend/tests/integration/test_jobs_endpoint.py`: with arq client mocked at the `tasks.enqueue` module surface, `POST /api/jobs/ping` → 202 with `job_id` + `submitted_at`; `GET /api/jobs/<known-id>` → 200 with status `complete` and result payload; `GET /api/jobs/<unknown-id>` → 404 with shape per `contracts/api_jobs.md`; Redis down (mock raises `RedisError`) → 502 `queue_unavailable, retryable=true`.
- [X] T015 [P] [US1] `backend/tests/integration/test_healthz_worker.py`: monkey-patch `probe_worker` to return each of `"ok"` / `"down"` / `"unreachable"` and assert (a) envelope's `worker` field reflects it; (b) overall `status` stays `"ok"` in every case; (c) `failing[]` never contains `worker`.

### Implementation for User Story 1

- [X] T016 [P] [US1] `backend/src/codesensei/tasks/ping.py`: `async def ping_job(ctx) -> dict[str, str]` returning `{"stamped_at": datetime.now(timezone.utc).isoformat()}`.
- [X] T017 [P] [US1] `backend/src/codesensei/tasks/worker.py`: define `WorkerSettings` class with `functions = [ping_job]`, `redis_settings = RedisSettings.from_dsn(settings.redis_url)`, `keep_result_seconds = settings.job_result_ttl_s`, `health_check_key = "arq:health-check:default"`.
- [X] T018 [P] [US1] `backend/src/codesensei/tasks/enqueue.py`: thin async wrapper around `arq.create_pool(...)` exposing `enqueue_ping() -> tuple[str, datetime]` (job_id + submitted_at) and `lookup_job(job_id: str) -> dict`. Raises `ReviewError(queue_unavailable, retryable=True)` (or a new `JobError` sibling — pick the **same envelope shape** as 003) on `RedisError`.
- [X] T019 [US1] `backend/src/codesensei/tasks/api.py`: `APIRouter(prefix="/jobs", tags=["jobs"])` exposing `POST /ping` (calls `enqueue_ping`, returns 202 body per contract) and `GET /{job_id}` (calls `lookup_job`, returns 200/404 per contract). Depends on T018.
- [X] T020 [US1] `backend/src/codesensei/healthcheck.py`: implement the real `probe_worker()` using the strategy from `contracts/healthz_worker.md` (read `arq:health-check:default` from Redis with 1s timeout, compare timestamp to `worker_heartbeat_stale_s`). Plug it into the `asyncio.gather` of probes; pass result into `build_envelope` via the `worker_state` arg already added in T011.
- [X] T021 [US1] `backend/src/codesensei/main.py`: include the jobs router at `prefix="/api"`. Depends on T019.
- [X] T022 [US1] `docker-compose.yml`: add a `worker` service definition — `build: ./backend`, `image: codesensei-api:dev`, `command: ["uv", "run", "arq", "codesensei.tasks.worker.WorkerSettings"]`, same env block as `api` (so it sees `REDIS_URL`, `MASTER_KEY`, etc.), `depends_on: redis: {condition: service_healthy}`, `restart: unless-stopped`. No port mapping (the worker doesn't speak HTTP).
- [X] T023 [P] [US1] `frontend/src/pages/HealthPage.vue`: extend the local `HealthEnvelope` type with `worker: 'ok' | 'down' | 'unreachable' | 'pending'`; add a sixth `<li>` badge between `embedding` and the error block; reuse the existing `colorFor()` (treat `down`/`unreachable` as red, `ok` as green). 

**Checkpoint**: `docker compose up -d` brings up `worker` next to `api`. `POST /api/jobs/ping` returns a job_id; within 5s `GET /api/jobs/{id}` returns `complete`. Stopping `worker` container flips badge to `down` after ~60s. All three integration tests pass.

---

## Phase 4: User Story 2 — Switch providers from a Settings page (Priority: P2)

**Goal**: `/settings` page lets the operator swap active LLM provider, drop in new keys, save; the next review uses the new provider — no container restart, secrets encrypted at rest, never visible in full from any endpoint.

**Independent Test** (spec US2): with `MASTER_KEY` set, open `/settings`, change active LLM provider, paste an Anthropic key, click Save; `POST /api/review` immediately uses Anthropic. Without `MASTER_KEY`, the same Save returns 503 `settings_locked` and stores nothing.

### Tests for User Story 2 (write FIRST)

- [X] T024 [P] [US2] `backend/tests/unit/test_settings_crypto.py`: with a valid `MASTER_KEY` env, `encrypt(x); decrypt(...)` is a no-op round-trip; missing key → `encrypt` raises `SettingsCryptoError`; invalid key shape → `encrypt` raises; `is_master_key_valid()` flips false/true correctly across the three states.
- [X] T025 [P] [US2] `backend/tests/unit/test_settings_store.py`: against the test db, `set_setting('LLM_PROVIDER', 'anthropic', is_secret=False)` then `get_setting(...)` returns `'anthropic'`; `set_setting('OPENAI_API_KEY', 'sk-xyz', is_secret=True)` then a `get_setting_redacted(...)` returns `'…o-xyz'` (or last-4 form); `set_setting('OPENAI_API_KEY', '', ...)` deletes the row; `get_effective_settings()` merges db rows on top of env defaults; `app_settings` rows never contain plaintext for `is_secret=true`.
- [X] T026 [P] [US2] `backend/tests/integration/test_settings_endpoint.py`: `GET /api/settings` returns the shape from `contracts/api_settings.md` (no plaintext anywhere); `POST` with an unknown field → 400 `invalid_input`; `POST` with `active_embedding_provider: "anthropic"` → 400 with the exact 002 message; `POST` with a secret field but `MASTER_KEY=""` → 503 `settings_locked`; valid `POST` → 200 + new state + grep verifies `caplog` has no key plaintext.
- [X] T027 [P] [US2] Extend `backend/tests/unit/test_provider_factory.py`: with a stored `LLM_PROVIDER=anthropic` row, factory returns the Anthropic provider even when env says `openai`; cache-clear after `set_setting` is verified.

### Implementation for User Story 2

- [X] T028 [P] [US2] `backend/src/codesensei/settings_store/store.py`: async functions `get_setting(key) -> str | None`, `set_setting(key, value, is_secret) -> None`, `delete_setting(key) -> None`, `get_setting_redacted(key) -> str | None`, `get_effective_settings() -> dict[str, str | None]`. `set_setting(...)` with `is_secret=True` uses `crypto.encrypt`; `get_setting(...)` returns plaintext for non-secret rows and decrypted plaintext for secret rows (catching `InvalidToken` → `None` + log). Whitelist enforcement raises `ReviewError(invalid_input, ...)` on unknown keys.
- [X] T029 [US2] `backend/src/codesensei/providers/factory.py` PATCH: at the top of `get_llm_provider()` / `get_embedding_provider()`, call `settings_store.get_effective_settings()` and use the resulting `LLM_PROVIDER` / `EMBEDDING_PROVIDER` (and per-provider key/model overrides) before the env-only fallback. Preserve the existing `lru_cache` behaviour; add a `bust_provider_cache()` helper that clears both factory caches. Depends on T028.
- [X] T030 [US2] `backend/src/codesensei/settings_store/api.py`: `APIRouter(prefix="/settings", tags=["settings"])` exposing `GET /` (calls `store.get_effective_settings()` + redacts secrets) and `POST /` (validates whitelist, applies updates, then `bust_provider_cache()` and `get_settings.cache_clear()` before returning the GET-shape body). Errors per `contracts/api_settings.md`. Depends on T029.
- [X] T031 [US2] `backend/src/codesensei/main.py`: include the settings router at `prefix="/api"`. Depends on T030.
- [X] T032 [P] [US2] `frontend/src/api/settings.ts`: typed wrapper exposing `getSettings(): Promise<SettingsState>`, `saveSettings(body: SettingsUpdate): Promise<SettingsState>`. Reuses the `ReviewApiError` envelope shape from 003 (rename to a shared `ApiError` if convenient).
- [X] T033 [P] [US2] `frontend/src/pages/SettingsPage.vue`: a form with two `<select>`s (active providers), three `<input>`s for model overrides + `ollama_base_url`, three `<input type="password">`s for API keys (placeholder `"…cdef"` when a key exists), a Save button. Show a banner if `master_key_present === false` ("Settings storage is locked — set MASTER_KEY before saving credentials") and disable secret fields. Depends on T032.
- [X] T034 [US2] `frontend/src/router.ts` + `frontend/src/App.vue`: add `{ path: '/settings', name: 'settings', component: SettingsPage }` and a `<RouterLink to="/settings">Settings</RouterLink>` entry in the topnav. Depends on T033.

**Checkpoint**: visit `/settings`, save a change → it survives a container restart and the next `/review` call uses the new provider; secrets never appear unredacted in any response or log. All four test files green.

---

## Phase 5: User Story 3 — Calibrated severities + line-anchor (Priority: P3)

**Goal**: re-running PR #8 through `/review` tags hardcoded credential / SQLi / `eval()` findings as `blocker` (not `major`) and lines land within ±1 of file lines.

**Independent Test** (spec US3): re-run PR #8 → in the response, the three security findings carry `"severity": "blocker"`; reported line numbers match file lines within ±1.

### Tests for User Story 3 (write FIRST)

- [X] T035 [P] [US3] `backend/tests/unit/test_review_prompt.py` UPDATE: add new pins per `contracts/llm_prompt_v2.md` (P5–P11). Carry-over assertions (P1–P4) remain. `build_messages(...)` call-args still `temperature=0.1`, `max_tokens=4096`.

### Implementation for User Story 3

- [X] T036 [US3] `backend/src/codesensei/review/prompt.py` PATCH: replace `SYSTEM_MESSAGE` with the verbatim text from `contracts/llm_prompt_v2.md`. `USER_TEMPLATE` and `build_messages(...)` unchanged.

**Checkpoint**: T035 passes against T036; live re-run of PR #8 shows `blocker`-tagged findings.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T037 [P] `cd backend && uv run ruff check . && uv run ruff format --check .` clean.
- [X] T038 [P] `cd frontend && COREPACK_INTEGRITY_KEYS=0 corepack pnpm exec vue-tsc -b` clean.
- [X] T039 [P] `cd backend && uv run pytest -q` — all 149 pre-existing tests pass plus the ~10 new tests added in Phases 3–5; total green.
- [X] T040 Update `README.md` with a short "Settings UI" line pointing to `specs/004-ops-quality-polish/quickstart.md`.
- [X] T041 Manually run `quickstart.md` Scenarios A–D against the running stack; capture a one-paragraph "verification notes" inside the PR description.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 Setup** — no dependencies. T001 must finish before T006 (alembic runs need new image). T002 + T003 [P]. T004 + T005 [P].
- **Phase 2 Foundational** — depends on Phase 1.
  - T007 + T008 + T009 + T010 [P] after T001.
  - T006 depends on T001.
  - T011 depends on the healthcheck.py current state (no Phase-1 dep beyond config additions); T012 follows T011.
- **Phase 3 US1** — depends on Phase 2.
  - All tests T013–T015 [P], drafted FAILING.
  - T016 + T017 + T018 [P]; T019 depends on T018; T020 needs T011 (envelope already accepts the arg); T021 depends on T019; T022 depends on T017 (compose `command:` matches the WorkerSettings path); T023 frontend is [P] after the envelope shape is settled.
- **Phase 4 US2** — depends on Phase 2 (uses crypto + AppSetting model + alembic-applied table).
  - T024 + T025 + T026 + T027 [P] FAILING.
  - T028 depends on T008 + T009; T029 depends on T028; T030 depends on T029; T031 follows T030; T032 + T033 [P] frontend after the GET/POST contract is settled; T034 follows T033.
- **Phase 5 US3** — depends on Phase 2 (technically only on the existing 003 module). T035 + T036 sequential.
- **Phase 6 Polish** — depends on Phases 3–5.

### Within Each Story

- Tests committed FAILING before implementation (constitution §test-first applies to crypto + prompt v2 + service-layer surfaces).
- Models / migrations before services; services before endpoints; endpoints before frontend wiring.

### Parallel Opportunities

- Phase 1: T002, T003, T004, T005 in any combination.
- Phase 2: T007, T008, T009, T010 simultaneously after T001.
- Phase 3 tests T013–T015 [P]; impl T016–T018 [P]; T023 frontend in parallel with backend.
- Phase 4 tests T024–T027 [P]; T032 + T033 in parallel with the backend handlers.

---

## Parallel Example: Phase 3 tests

```bash
Task: "Write backend/tests/unit/test_tasks_ping.py per data-model.md PingJobResult"
Task: "Write backend/tests/integration/test_jobs_endpoint.py per contracts/api_jobs.md"
Task: "Write backend/tests/integration/test_healthz_worker.py per contracts/healthz_worker.md"
```

Three disjoint files; commit failing, then implement T016–T020.

---

## Implementation Strategy

### MVP First (US1 alone)

1. Land Phase 1 + Phase 2.
2. Land Phase 3 (US1). At this checkpoint, `worker` is provably alive end-to-end. PR-grade if you want a partial checkpoint commit.

### Incremental Delivery

1. Land Phase 3 (US1) → demo `quickstart.md` Scenarios A + D.
2. Land Phase 4 (US2) → demo Scenario B.
3. Land Phase 5 (US3) → demo Scenario C with calibrated severities.
4. Phase 6 polish before opening the PR for merge.

### Single-Developer Strategy

There is no team here; "parallel" means "task selection during the same focused session" rather than "two devs at once". [P] markers help pick the next non-blocking task.

---

## Notes

- [P] = different file, no incomplete-sibling dependency.
- [Story] tag required only on Phase 3–5 tasks.
- All tasks list exact file paths.
- Two ADRs (T004 + T005) are **non-negotiable**: per Constitution §II they must land before any implementation task touches the queue or the credential-storage surface.
- The queue is **not** wired into `/api/review` in this feature — review stays synchronous per spec. The async-review wiring is a candidate for feature 005+.
