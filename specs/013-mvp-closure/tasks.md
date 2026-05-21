---
description: "Task list for 013-mvp-closure"
---

# Tasks: MVP closure — custom-ignore + live index progress

**Input**: Design documents from `/specs/013-mvp-closure/`
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

- [X] T001 Verify branch `013-mvp-closure` is checked out and clean of unrelated edits via `git status -s` (working tree may contain only `specs/013-mvp-closure/*` + `.specify/feature.json` + `CLAUDE.md` marker bumps from /speckit-plan).
- [X] T002 Draft ADR-016 "Operator-facing index controls — `.codesensei-ignore` + live progress stream" in `/Users/tarasivanov/Desktop/Диплом/_decision_log.md` using the prose from `specs/013-mvp-closure/research.md §Decision: ADR-016 contents`. Insert as a new entry directly above ADR-015. Status: accepted. Supersedes nothing. **HARD GATE — Constitution Principle II: NO production code below until this lands.**

**Checkpoint**: ADR-016 merged into decision log → unblocks all foundational tasks.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Schema migration. Required by every US that persists ignore patterns.

**⚠️ CRITICAL**: No user-story task starts until Phase 2 is complete.

- [X] T003 Write alembic migration `backend/alembic/versions/006_repos_codesensei_ignore.py` with `revision = "006_repos_codesensei_ignore"`, `down_revision = "005_review_run_tokens"`. `upgrade()`: one `op.add_column` call on `repos` — `codesensei_ignore_patterns JSONB NULL`. `downgrade()`: one `op.drop_column` call.
- [X] T004 Apply migration locally — `docker compose exec api alembic upgrade head` (or rebuild api+worker: `docker compose up -d --build api worker`); confirm `alembic current` reports `006_repos_codesensei_ignore (head)`.

**Checkpoint**: schema extended → user-story phases may run in parallel where marked [P].

---

## Phase 3: User Story 1 — `.codesensei-ignore` honoured at index time (Priority: P1) 🎯 MVP

**Goal**: every successful `POST /api/index` reads `<repo_root>/.codesensei-ignore` (when present), filters the walked tree by the parsed patterns, persists the pattern list on the `repos` row, and surfaces it on the response.

**Independent Test**: place `.codesensei-ignore` at a test repo root with `vendor/`, trigger indexing, confirm zero `vendor/`-pathed chunks AND response `codesensei_ignore_patterns == ["vendor/"]`. Quickstart Step 1.

### Tests for User Story 1

- [X] T005 [P] [US1] Write unit tests in `backend/tests/unit/test_codesensei_ignore.py` covering: parse happy path (3 patterns + comment + blank); comment-line drops; blank-line drops; trailing-slash → directory flag; truncation at 200 patterns emits `codesensei_ignore_truncated` warning; oversize file (>4 KB) → returns None + `codesensei_ignore_oversize` warning; `path_matches_any` for `vendor/` (dir-pattern), `*.generated.ts` (filename-pattern), `dist/` (dir-pattern), `**/*.snap` (path-pattern); empty-file → None.
- [X] T006 [P] [US1] Extend `backend/tests/integration/test_indexing_endpoint.py` — add `test_index_honors_codesensei_ignore`: tmp_path repo containing `.codesensei-ignore: "vendor/\n"`, one `vendor/skip.py`, one `src/keep.py`. Trigger `POST /api/index` (or call `_run_index_inline` directly with stub embedder). Assert response carries `codesensei_ignore_patterns == ["vendor/"]` AND no chunk has `file_path` starting with `vendor/`. Add `test_index_no_ignore_file_keeps_field_null`: same fixture without the file, assert response `codesensei_ignore_patterns is None`.

### Implementation for User Story 1

- [X] T007 [P] [US1] Create `backend/src/codesensei/indexing/ignore.py` per `contracts/codesensei_ignore_file.md`. Exports `IgnoreSpec` frozen dataclass + `parse_ignore_file(root: Path) -> IgnoreSpec | None` + `path_matches_any(path: Path, spec: IgnoreSpec, root: Path) -> bool`. Stdlib only (`pathlib`, `fnmatch`, `dataclasses`, `structlog`). Hard caps: 4 KB / 200 patterns; warnings via `structlog.get_logger(__name__).warning(...)`.
- [X] T008 [P] [US1] Modify `backend/src/codesensei/indexing/chunker.py:iter_source_files` — extend signature to `iter_source_files(root: Path, *, extra_skip_globs: IgnoreSpec | None = None)`. Inside the loop, after the existing `skip_dirs` check and BEFORE the extension whitelist check, call `if extra_skip_globs is not None and path_matches_any(path, extra_skip_globs, root): continue`. Import `IgnoreSpec` + `path_matches_any` from `codesensei.indexing.ignore`.
- [X] T009 [P] [US1] Modify `backend/src/codesensei/indexing/models.py:Repo` — add `codesensei_ignore_patterns: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)`.
- [X] T010 [P] [US1] Modify `backend/src/codesensei/indexing/schema.py` — add `codesensei_ignore_patterns: list[str] | None = None` to BOTH `RepoSummary` and `RepoDetail` (whichever exact class names exist; mirror `contracts/repos_response.md`).
- [X] T011 [P] [US1] Modify `backend/src/codesensei/indexing/api.py` `_row_to_summary` / `_row_to_detail` (or equivalent helpers) to emit `codesensei_ignore_patterns=row.codesensei_ignore_patterns`.
- [X] T012 [US1] Modify `backend/src/codesensei/indexing/service.py` — at the start of `_run_index_inline` AND inside the arq worker entry path (whichever the call site is for the existing tree walk), call `spec = parse_ignore_file(root)`; pass `extra_skip_globs=spec` into `iter_source_files`. After the chunk-store swap commits, update the `Repo` row with `codesensei_ignore_patterns = list(spec.patterns) if spec is not None and spec.patterns else None` inside the same async session. Depends on T007, T008, T009. Import `parse_ignore_file` from `codesensei.indexing.ignore`.
- [X] T013 [P] [US1] Extend frontend type `RepoEntry` in `frontend/src/api/repos.ts` with `codesensei_ignore_patterns?: string[] | null`. (No UI rendering yet — that's US3.)

**Checkpoint**: indexing a repo with `.codesensei-ignore: vendor/` produces a `Repo` whose response field carries the pattern list and whose chunk store has no `vendor/`-prefixed paths.

---

## Phase 4: User Story 2 — Live indexing progress via WebSocket (Priority: P1)

**Goal**: arq worker fans progress events out via Redis pub/sub; SPA subscribes via `WS /api/jobs/{job_id}/stream`; existing polling stays as fallback.

**Independent Test**: open `/repos`, click Re-index on a 50-file fixture repo, observe progress card updating ≤ 1 s after each worker file-completion; DevTools shows one WebSocket frame stream, no recurring `GET /api/jobs/<id>` calls. Quickstart Step 3.

### Tests for User Story 2

- [X] T014 [P] [US2] Write unit tests in `backend/tests/unit/test_jobs_stream_publisher.py` — using `fakeredis.aioredis.FakeRedis`, instantiate the redis client, await `publisher.publish(redis, job_id, frame)`. Assert the published message hits channel `codesensei:job:<job_id>` with JSON-encoded body equal to the frame. Cover three frame kinds: `init`, `progress`, `complete`. Include a throttling assertion: publishing two `progress` frames within 0.3 s drops the second (if throttle is implemented in publisher; if in worker, defer the assertion to T020's integration test).
- [X] T015 [P] [US2] Write integration tests in `backend/tests/integration/test_jobs_stream_ws.py` (NEW). Three cases:
  1. **Happy path**: spawn the app via `TestClient`; open WS to `/api/jobs/<existing-job-id>/stream`; in another coroutine, publish `init` + 3 × `progress` + `complete` to the fake redis. Assert client receives all 5 frames in order; assert connection closes with code 1000 after `complete`.
  2. **Unknown job**: open WS to `/api/jobs/<random-uuid>/stream`. Assert close code 4404 + reason `"job_not_found"`.
  3. **Mid-stream disconnect**: client closes after receiving 2 progress frames. Assert server-side `pubsub.unsubscribe()` is called, no exception leaks to worker logs.

### Implementation for User Story 2

- [X] T016 [P] [US2] Create `backend/src/codesensei/jobs_stream/__init__.py` (empty) + `backend/src/codesensei/jobs_stream/schema.py` with three `TypedDict` classes (`InitFrame`, `ProgressFrame`, `CompleteFrame`) per `contracts/jobs_stream_ws.md` + `data-model.md §Entity 4`. Use `Literal["init"|"progress"|"complete"]` for the discriminator.
- [X] T017 [P] [US2] Create `backend/src/codesensei/jobs_stream/publisher.py` exposing `async def publish(redis, job_id: UUID, frame: dict) -> None`: `await redis.publish(f"codesensei:job:{job_id}", json.dumps(frame))`. Add channel-name helper `def channel_for(job_id) -> str`.
- [X] T018 [P] [US2] Create `backend/src/codesensei/jobs_stream/router.py` — FastAPI `APIRouter()` with one route `@router.websocket("/api/jobs/{job_id}/stream")`. Body: `await ws.accept()`; open pubsub on channel; look up arq job state via `arq.jobs.Job(str(job_id), get_redis_pool()).status()`; if not-found → `await ws.close(code=4404, reason="job_not_found")`; else send `InitFrame` reflecting current state. Then `async for message in pubsub.listen(): await ws.send_text(message["data"])`. Break + close(1000) when forwarded frame's `kind == "complete"`. Use try/finally to call `await pubsub.unsubscribe(channel); await pubsub.aclose()`.
- [X] T019 [US2] Modify `backend/src/codesensei/main.py` — `from codesensei.jobs_stream.router import router as jobs_stream_router` + `app.include_router(jobs_stream_router)`. Depends on T018.
- [X] T020 [US2] Modify `backend/src/codesensei/tasks.py:index_repo_job` — track `last_publish_ts = 0.0` local. At each existing `_logger.info("indexing_progress", ...)` site, compute `now = time.monotonic()`; if `now - last_publish_ts > 0.5`: `await publisher.publish(ctx["redis"], job_id, {"kind":"progress", "files_done": ..., "files_total": ..., "chunks_done": ..., "current_file": ...})`; set `last_publish_ts = now`. At terminal state (both success and exception paths): `await publisher.publish(ctx["redis"], job_id, {"kind":"complete", "state": ..., "error_category": ..., "error_message": ..., "final_files": ..., "final_chunks": ...})`. Import `publisher` from `codesensei.jobs_stream`. Depends on T017.
- [X] T021 [P] [US2] Create `frontend/src/composables/useJobStream.ts` per `research.md §Decision 5`. Signature: `function useJobStream(jobId: Ref<string | null>, onFrame: (frame: any) => void): { fallbackToPolling: Ref<boolean>; close: () => void }`. Construct WS URL via `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/api/jobs/${jobId.value}/stream`. `onopen` → `fallbackToPolling.value = false`. `onmessage` → `onFrame(JSON.parse(event.data))`. `onclose` with `code !== 1000` → `fallbackToPolling.value = true`. `onerror` → same as non-1000 close. Watch `jobId`: rebuild socket on change; close on null.
- [X] T022 [US2] Modify `frontend/src/pages/ReposPage.vue` — for each repo row that has an in-flight `job_id`, call `useJobStream(jobId, applyFrame)`. Watch `fallbackToPolling`: when `false`, suspend the existing polling timer for that job; when `true`, resume. `applyFrame` updates the local progress state (files_done, chunks_done, current_file). Depends on T021.
- [X] T023 [P] [US2] Verify the frontend nginx config inside `frontend/Dockerfile` (or `frontend/nginx.conf`) forwards WebSocket upgrade headers on `/api/` per `research.md §Decision 6`: `proxy_http_version 1.1`, `proxy_set_header Upgrade $http_upgrade`, `proxy_set_header Connection "upgrade"`, `proxy_read_timeout 3600s`. If missing → add. If already present → no edit.
- [X] T024 [US2] Add `fakeredis` to `backend/pyproject.toml` `[project.optional-dependencies]` group `test` (or wherever dev deps live). Needed by T014, T015 in CI; runtime installs via `pip install -q fakeredis` in the T029 pytest task line. Depends on T014.

**Checkpoint**: an index run on `/repos` shows live progress via WS; if frontend container restarts mid-run, the SPA falls back to polling within 5 s without an error toast.

---

## Phase 5: User Story 3 — `.codesensei-ignore` UI affordance (Priority: P2)

**Goal**: `/repos` shows a badge with parsed pattern list; Settings page documents the file format.

**Independent Test**: index a repo with 3-pattern file → repo card shows `🚫 3 custom ignores` badge with tooltip listing all three; Settings page has a static help section copy-pasteable by an operator. Quickstart Step 2, Step 8.

- [X] T025 [P] [US3] Modify `frontend/src/pages/ReposPage.vue` — for each repo card with `repo.codesensei_ignore_patterns?.length > 0`, render a Badge `🚫 {count} custom ignores` (or non-emoji equivalent — match existing badge style). On hover/focus, render Tooltip with the first 20 patterns + `+{N-20} more` summary when N > 20. Depends on T013 (type) + T011 (backend emission).
- [X] T026 [P] [US3] Modify `frontend/src/pages/SettingsPage.vue` — add a static help `<details>` (or Card) titled "`.codesensei-ignore` syntax". Body: 1-screen explanation copy-paste from `contracts/codesensei_ignore_file.md §File format` + a worked example (`vendor/`, `*.generated.ts`, `dist/`). No backend wiring.
- [X] T027 [US3] Manual smoke verification — confirm steps 2 + 8 from `quickstart.md` produce the badge + help section as described. Depends on T025, T026.

**Checkpoint**: operator can author + audit `.codesensei-ignore` without dropping to source code or backend logs.

---

## Phase 6: Polish & Cross-Cutting

**Purpose**: verification, lint, manual smoke, marker bumps.

- [X] T028 Run `docker compose exec api alembic current` — verify revision is `006_repos_codesensei_ignore`.
- [X] T029 Run backend test suite via `docker compose run --rm -v "$(pwd)/backend/tests:/app/tests" -e OPENAI_API_KEY= -e ANTHROPIC_API_KEY= -e GITHUB_TOKEN= -e MASTER_KEY= -e MASTER_KEY_FILE= api sh -c "/opt/venv/bin/python -m ensurepip && /opt/venv/bin/python -m pip install -q pytest pytest-asyncio respx fakeredis && cd /app && /opt/venv/bin/python -m pytest --tb=short -q"`. Expect all green including the new `test_codesensei_ignore.py` + `test_jobs_stream_publisher.py` + `test_jobs_stream_ws.py` + extended `test_indexing_endpoint.py`.
- [X] T030 Run `docker compose run --rm -v "$(pwd)/backend/tests:/app/tests" api sh -c "/opt/venv/bin/python -m ensurepip && /opt/venv/bin/python -m pip install -q ruff && /opt/venv/bin/python -m ruff check src tests"`. Expect `All checks passed!`.
- [X] T031 Run `cd frontend && npx vue-tsc --noEmit && npx vite build`. Both must be clean.
- [X] T032 `docker compose up -d --build api worker frontend` to bake the migration + WS routing + nginx WS-upgrade config into running images.
- [X] T033 Manual smoke per `specs/013-mvp-closure/quickstart.md` Steps 1–8. Verify ignore-honoured + badge + live WS progress + polling fallback + truncation/oversize warnings.
- [X] T034 Verify `.specify/feature.json` points at `specs/013-mvp-closure` (was updated during /speckit-plan); verify `CLAUDE.md` SPECKIT marker also bumped (was updated during /speckit-plan). Idempotent check.

**Checkpoint**: all green → ready for single-commit pipeline boundary + PR.

---

## Dependencies

```text
Phase 1 (T001-T002)
  → Phase 2 (T003 → T004)
    → Phase 3 (US1)
       └─ T005, T006, T007, T008, T009, T010, T011, T013 parallel
       └─ T012 depends on T007, T008, T009
    → Phase 4 (US2)
       └─ T014, T015, T016, T017, T018, T021, T023, T024 parallel
       └─ T019 depends on T018
       └─ T020 depends on T017
       └─ T022 depends on T021
    → Phase 5 (US3)
       └─ T025, T026 parallel (depend on T013 + T011 for type/payload)
       └─ T027 depends on T025, T026
    → Phase 6 (Polish — sequential)
```

US1 and US2 are independent at the file level (different modules); both extend the same `Repo` row but at orthogonal lifecycle moments (US1 writes a column at index-end; US2 publishes events during the index). Stories can be developed in parallel up to the integration test (T015 sees the full WS path; T006 sees the full ignore path).

## Parallel Execution Examples

**Phase 2 kickoff** (after T002 ADR lands):
- T003 (migration) → T004 (apply) — sequential.

**Phase 3 implementation parallelism** (after T004 migration applied):
- T005, T006, T007, T008, T009, T010, T011, T013 can run in parallel — distinct files.
- T012 is the integration point (service.py wires `parse_ignore_file` + persists patterns).

**Phase 4 implementation parallelism**:
- T014, T015, T016, T017, T018, T021, T023, T024 — distinct files, no shared state.
- T019 (main.py include router) waits on T018; T020 (worker publish) waits on T017; T022 (ReposPage wire) waits on T021.

**Phase 5 parallelism**:
- T025 (ReposPage badge) + T026 (SettingsPage help) — distinct files.

## Implementation Strategy

**MVP slice**: T001–T013 alone delivers the `.codesensei-ignore` honour-at-index path. Phase 4 (live WS progress) ships same-day at P1 to avoid wire-vs-history shape drift, but if time-boxed, Phase 4 can land as a same-day follow-up without breaking Phase 3.

**Single-commit pipeline boundary**: all phases commit as one feature commit (`feat(013-mvp-closure): ...`) per project commit-granularity convention. Branch already exists as `013-mvp-closure`. Push to remote + open PR with quickstart-aligned test plan at Phase 6 completion.
