---

description: "Task list for feature 005 — Repo indexing + RAG-augmented review"
---

# Tasks: Repo indexing + RAG-augmented review

**Input**: Design documents from `/specs/005-rag-indexing/`
**Prerequisites**: `plan.md`, `spec.md`, `research.md` (R1–R10), `data-model.md`, `contracts/{api_index,api_review_v2,llm_prompt_v3,retrieval_algorithm,index_repo_job}.md`, `quickstart.md`

**Tests**: Included. Constitution §"Test-first for critical paths" mandates failing tests committed before AST chunking, retrieval, and prompt-assembly implementation.

**Organisation**: One phase per user story; each story is independently testable.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Different file, no dependency on incomplete tasks → can run in parallel.
- **[Story]**: User-story tag (US1…US4); omitted for Setup/Foundational/Polish.
- Every task names exact file paths.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: pre-implementation ADRs, dependency additions, and image-level changes that every later phase depends on.

- [ ] T001 Append ADR-009 "RAG retrieval strategy = per-hunk semantic queries, top-K=5 cosine, 3 000-token budget" to `../_decision_log.md` (full body in `specs/005-rag-indexing/research.md` §R1).
- [ ] T002 [P] Append ADR-010 "Sync indexing threshold = 200 source files, async via 004's arq queue, no review-job migration" to `../_decision_log.md` (body in `specs/005-rag-indexing/research.md` §R4).
- [ ] T003 [P] Add `tiktoken>=0.7` and `aiofiles>=24` to `backend/pyproject.toml` under `[project].dependencies`; run `uv lock` (refreshes `backend/uv.lock`).
- [ ] T004 [P] Edit `backend/Dockerfile` so the `api` image installs `git` (single line: `RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*`). The `worker` reuses the same image — no separate change.

**Checkpoint**: dependencies declared, image-level git available, ADRs filed. Foundational work can start.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: schema, ORM models, error envelope, router stub — every user story depends on these.

**⚠️ CRITICAL**: No US-tagged task may start until this phase is complete.

- [ ] T005 Create alembic migration `backend/alembic/versions/003_repos_chunks.py` per `data-model.md` (two tables, BTREE on `repos(source)` UNIQUE, BTREE on `code_chunks(repo_id)`, HNSW on `code_chunks.embedding USING hnsw (embedding vector_cosine_ops)`).
- [ ] T006 [P] Create `backend/src/codesensei/indexing/__init__.py` (empty package marker).
- [ ] T007 [P] Create SQLAlchemy mapped classes `Repo` and `CodeChunk` in `backend/src/codesensei/indexing/models.py`; reuse the `DeclarativeBase` registry already imported by `codesensei.settings_store.models` so alembic autogen sees them (re-export the same `Base`).
- [ ] T008 [P] Create `backend/src/codesensei/indexing/errors.py` — `IndexErrorCategory` `StrEnum` (`invalid_input`, `payload_too_large`, `already_indexing`, `clone_failed`, `embedding_failed`, `embedding_dimension_mismatch`, `embedding_mismatch`, `delete_during_index`, `queue_unavailable`, `not_found`, `internal`), `HTTP_FOR_INDEX_CATEGORY` map (400/413/409/502/502/500/422/409/502/404/500), and `IndexError(category, message, retryable=False)` with `to_envelope()`.
- [ ] T009 Mount `indexing_router` (placeholder, exposes nothing yet) and register an `IndexError` exception handler in `backend/src/codesensei/main.py` under `prefix="/api"`.

**Checkpoint**: migration runs cleanly (`uv run alembic upgrade head` on a fresh DB), ORM models import without errors, `IndexError` envelopes serialise. User stories unblocked.

---

## Phase 3: User Story 1 — Index a small repository synchronously (Priority: P1) 🎯 MVP

**Goal**: a reviewer submits a repo (URL or local path) and immediately gets back `repo_id` + `chunk_count` + `indexed_at`. Re-indexing, listing, deletion all work. No queue involvement.

**Independent Test**: with the system fresh, `POST /api/index {"source": "/app"}` returns 201 with `chunk_count > 0` and `mode: "sync"`; `GET /api/repos` lists exactly that row; `DELETE /api/repos/{id}` returns 204 and the listing goes back to empty.

### Tests for User Story 1 (write-first per Constitution)

- [ ] T010 [P] [US1] `backend/tests/unit/test_indexing_chunker.py` — covers Python AST splitter (one chunk per top-level def/class + a "module preamble" chunk), Markdown heading split, sliding-window fallback (80-line window, 10-line overlap), binary skip (NUL byte in first 8 KB), oversize-file skip (>200 KB), and that `start_line`/`end_line` are correct and 1-indexed.
- [ ] T011 [P] [US1] `backend/tests/unit/test_indexing_service.py` — orchestrator unit tests with `AsyncMock` of `EmbeddingProvider.embed`: happy path produces a repo row + N chunks with the correct provider/model captured; pre-scan above 5 000-chunk projection returns `IndexError(payload_too_large)` and writes **no** rows; embedding-provider raises mid-pass → no orphan chunks, no `indexed_at` set, `last_error` populated, repo row deleted iff it was newly created by this request.
- [ ] T012 [P] [US1] `backend/tests/unit/test_indexing_store.py` — atomic chunk-replacement T2 swap pattern: a re-index pass inserts new chunks (with synthetic `pass_id` in memory), commits the deletion of `id NOT IN (...)` for the same `repo_id`, and assertions verify the resulting count equals the second pass's count (not the sum) and the new `indexed_at` is fresh.
- [ ] T013 [P] [US1] `backend/tests/integration/test_index_endpoint.py` (sync subset) — `POST /api/index {"source": "<temp clone of this very repo>"}` → 201 sync; oversized request → 413 with `payload_too_large`; bad URL → 502 `clone_failed`; SSH URL → 400 `invalid_input`.
- [ ] T014 [P] [US1] `backend/tests/integration/test_repos_endpoint.py` — `GET /api/repos` returns empty list on a clean DB; after two `POST /api/index` calls returns them ordered by `indexed_at DESC`; `DELETE /api/repos/{id}` returns 204 and cascades the chunks (count via direct SQL = 0); deleting an unknown id → 404.

### Implementation for User Story 1

- [ ] T015 [US1] Implement async git clone via subprocess in `backend/src/codesensei/indexing/clone.py` — `clone(source: str, source_kind: Literal["https","local"], default_branch: str | None) -> AsyncContextManager[Path]` that yields a `Path` to the materialised working tree; for `local`, just yield the path; for `https`, `git clone --depth 1 --filter=blob:none -b $branch <url> <tmpdir>` via `asyncio.create_subprocess_exec`; tmpdir cleaned up in the context-manager `__aexit__`. Maps `git`'s non-zero exit + first stderr line into `IndexError(clone_failed)`.
- [ ] T016 [P] [US1] Implement the three chunkers in `backend/src/codesensei/indexing/chunker.py`: `chunk_python(content, file_path) -> list[ChunkSpec]` using `ast.parse` + `ast.walk` filtering `FunctionDef|AsyncFunctionDef|ClassDef` at module level; `chunk_markdown(content, file_path) -> list[ChunkSpec]` splitting on `^#{1,2}\s` boundaries; `chunk_sliding(content, file_path, window=80, overlap=10) -> list[ChunkSpec]`; `dispatch_chunker(file_path) -> callable` picking by extension per `research.md` §R2; `iter_source_files(root: Path) -> Iterator[Path]` walking the tree, honouring `.gitignore` (use `pathspec` only if already present — otherwise stdlib `.gitignore`-aware via simple line-match; per R2 we accept "basic honouring" only). Binary-detection helper `is_binary(bytes_: bytes) -> bool` checks for a NUL byte in the first 8 KB.
- [ ] T017 [US1] Implement atomic chunk replacement in `backend/src/codesensei/indexing/store.py`: `replace_chunks(session, repo_id, new_chunks: list[CodeChunkInsert]) -> int` that opens one transaction, INSERTs all new chunks with `RETURNING id`, then deletes `WHERE repo_id = $repo_id AND id <> ALL($new_ids::uuid[])`, finally `UPDATE repos SET indexed_at = now(), chunk_count = …, embedding_provider = …, embedding_model = …, last_error = NULL` in the same transaction. Returns the new chunk count. (T011/T012 are the gate.)
- [ ] T018 [US1] Implement the indexing orchestrator in `backend/src/codesensei/indexing/service.py`: `IndexingService.run_sync(source, source_kind, default_branch) -> RepoSnapshot` that: (1) normalises the source URL/path, (2) creates-or-fetches a `repos` row (UNIQUE on `source`), (3) calls `clone(...)` as an async context manager, (4) calls the chunkers to produce `(ChunkSpec, source_file_contents)` list, (5) counts projected chunks; if > 5 000 raises `IndexError(payload_too_large)`, (6) calls `embedding_provider.embed(batch_of_100)` until all chunks have vectors, (7) calls `store.replace_chunks(...)`, (8) emits `indexing.complete` structlog line with `provider/model/files_scanned/chunks/embedding_seconds/total_seconds`. On any exception during steps 3–7, set `repos.last_error` and re-raise as an `IndexError`; on the **specific** case where this request created a brand-new row (no prior `indexed_at`, no prior `last_error`), delete the row instead of leaving a tombstone.
- [ ] T019 [US1] Implement HTTP endpoints in `backend/src/codesensei/indexing/api.py`: `POST /api/index` accepts the request body, routes to `IndexingService.run_sync(...)` (US1 only — async dispatch comes in US3); on success returns `201 {"repo_id":…, "chunk_count":…, "indexed_at":…, "mode": "sync"}`. `GET /api/repos` queries the registry (no chunks join — only the metadata + derived `status`) and returns the listing. `DELETE /api/repos/{repo_id}` runs a `DELETE FROM repos WHERE id = $1` (cascade handles chunks); 204 on success, 404 on unknown, 409 `delete_during_index` if `indexed_at IS NULL AND last_error IS NULL`.
- [ ] T020 [US1] Wire the `indexing_router` defined in T009 to the implementations in T019; remove the placeholder stub.
- [ ] T021 [US1] Update `backend/src/codesensei/main.py` lifespan: no-op for indexing (the migration is the only initialisation step); ensure `IndexingService` is instantiated per-request (no singleton — embedding provider may change between requests via the 004 Settings store).

**Checkpoint**: Sync indexing flow is end-to-end. `POST /api/index` against `/app` works; `GET /api/repos` lists it; `DELETE` cascades. T010–T014 all pass.

---

## Phase 4: User Story 2 — Review a diff with repository context (Priority: P2)

**Goal**: `POST /api/review` accepts optional `repo_id`; when present, derives semantic queries from the diff, retrieves top-K chunks under a token budget, injects them into the prompt, and surfaces `context_files` in the response. Diff-only behaviour preserved when `repo_id` is absent.

**Independent Test**: with a repo indexed (US1 done), POST a diff with `repo_id` set → response includes `context_files` non-empty; POST the same diff without `repo_id` → response is byte-equivalent to 004's; POST with an unknown UUID → 400 with `invalid_input` and no LLM call.

### Tests for User Story 2

- [ ] T022 [P] [US2] `backend/tests/unit/test_retrieval.py` — hunk parser produces one query per non-deletion hunk, includes ±10 lines of new-file context; token-budget trim deterministically drops lowest-scored chunks; score floor (distance > 1.5) drops poor matches; dedup across queries keeps best score; embedding-provider failure during retrieval raises `ReviewError(provider_unavailable, retryable=True)` rather than silently falling back.
- [ ] T023 [P] [US2] `backend/tests/unit/test_review_prompt_v3.py` — snapshot test for `render_user_message(diff=…, retrieved_chunks=[…])` per `contracts/llm_prompt_v3.md`; when `retrieved_chunks` is empty/None the output is byte-equivalent to 003/004's snapshot.
- [ ] T024 [P] [US2] `backend/tests/unit/test_review_with_context.py` — `ReviewService.run_for_diff(diff, repo_id=…)` with `AsyncMock`ed LLM and retrieval: response carries `context_files`, the `retrieval.done` log line is emitted with the right counts, and embedding-mismatch (active vs persisted) refuses with HTTP 422.
- [ ] T025 [P] [US2] `backend/tests/integration/test_review_with_repo.py` — with one indexed repo (created in the test fixture via `IndexingService.run_sync` against a small fixture directory), `POST /api/review {"diff": <changes a file from the fixture>, "repo_id": <id>}` → 200 with `context_files` non-empty; unknown `repo_id` → 400; `repo_id` for a repo whose `indexed_at IS NULL` → 409 `repo_not_ready`.
- [ ] T026 [P] [US2] `backend/tests/integration/test_pgvector_search.py` — one real-pgvector test (skip on CI without DB) that inserts 50 synthetic chunks with hand-crafted embeddings, runs the retrieval SQL, and asserts the HNSW ordering matches the cosine distance computed in Python.

### Implementation for User Story 2

- [ ] T027 [US2] Implement the retrieval module in `backend/src/codesensei/indexing/retrieval.py` per `contracts/retrieval_algorithm.md`: `derive_queries(diff: str) -> list[str]`, `RetrievalService.search(repo_id: UUID, diff: str, *, top_k=5, token_budget=3000) -> RetrievalResult`, the SQL with `embedding <=> $1::vector ORDER BY embedding <=> $1::vector LIMIT $top_k`, the dedup + trim algorithm, and the embedding-mismatch check that raises `ReviewError(category=invalid_input, message="…embedding_mismatch…")` with HTTP 422 mapping.
- [ ] T028 [P] [US2] Extend the review wire shape in `backend/src/codesensei/review/schema.py`: `ReviewRequest.repo_id: UUID | None = None`; `ReviewResult.context_files: list[str] | None = None`; serialisation rule: omit `context_files` from the dict if it is `None` (so the diff-only response stays byte-equivalent to 004's).
- [ ] T029 [US2] Update `backend/src/codesensei/review/prompt.py`: SYSTEM message unchanged (still v2 from 004); USER template gets the optional `{repository_context_block}` per `contracts/llm_prompt_v3.md`; add `render_user_message(diff, retrieved_chunks)` helper that handles both the empty and non-empty cases and asserts the total token count stays ≤ the model's safe window.
- [ ] T030 [US2] Update `backend/src/codesensei/review/service.py`: `run_for_diff(...)` accepts `repo_id: UUID | None`; if present, calls `RetrievalService.search(...)`, builds `context_files` from `result.selected`, passes `result.selected` to `render_user_message(...)`; emits `retrieval.started` and `retrieval.done` structlog lines; surfaces 422 on embedding-mismatch and 409 on `repo_not_ready`; surfaces 400 on unknown `repo_id`.
- [ ] T031 [US2] Update the router exception handler in `backend/src/codesensei/main.py` so 422 (`embedding_mismatch`) and 409 (`repo_not_ready`) map onto the existing review error envelope without leaking the `IndexError` envelope shape (both errors are surfaced as `ReviewError` to keep `/api/review` responses consistent).

**Checkpoint**: RAG review works end-to-end against an indexed repo; the diff-only path is unchanged at the byte level. T022–T026 pass.

---

## Phase 5: User Story 3 — Index a larger repository asynchronously (Priority: P3)

**Goal**: when a pre-scan finds > 200 source files, `POST /api/index` returns 202 with a `job_id`; the existing `/api/jobs/{id}` polling surface (from feature 004) shows the indexing progress; on completion the repo row is finalised; re-indexing replaces chunks atomically.

**Independent Test**: with the system fresh, `POST /api/index {"source": "https://github.com/pallets/flask.git"}` returns 202 with `job_id`; polling `/api/jobs/{job_id}` shows pending → in_progress → complete; `/api/repos` then shows the flask repo with chunk_count > 100 and a recent indexed_at.

### Tests for User Story 3

- [ ] T032 [P] [US3] `backend/tests/unit/test_index_repo_job.py` — `index_repo_job(ctx, repo_id, source, source_kind, default_branch)` returns the success dict on happy path; sets `repos.last_error` and returns the failure dict on `IndexingService` exception; idempotent: running twice for the same `repo_id` does not double the chunks (the atomic swap from T017 covers this).
- [ ] T033 [P] [US3] `backend/tests/integration/test_index_endpoint.py` — async subset: `POST /api/index` with a fake pre-scan returning 800 → 202 with `job_id`; enqueue failure (Redis down) → 502 `queue_unavailable`; concurrent re-submission of the same `source` while `indexed_at IS NULL AND last_error IS NULL` → 409 `already_indexing` carrying the existing `repo_id`.

### Implementation for User Story 3

- [ ] T034 [US3] Implement `backend/src/codesensei/indexing/tasks.py`: `async def index_repo_job(ctx, repo_id, source, source_kind, default_branch) -> dict` that delegates to `IndexingService.run_async(repo_id, source, source_kind, default_branch)` and wraps exceptions per `contracts/index_repo_job.md`.
- [ ] T035 [P] [US3] Add `run_async` method to `IndexingService` in `backend/src/codesensei/indexing/service.py` — same orchestration as `run_sync` but takes an existing `repo_id` (the row was created at enqueue time by the HTTP handler) and writes outcomes back to it; on success returns the success dict; on failure writes `last_error` and **does not** delete the row (the row was pre-existing because of the async-dispatch flow, so deletion would race the user's `/api/repos` polling).
- [ ] T036 [US3] Register `index_repo_job` in `backend/src/codesensei/tasks/worker.py` by appending it to `WorkerSettings.functions`; ensure the import path is `codesensei.indexing.tasks.index_repo_job` so arq's module-scan picks it up.
- [ ] T037 [US3] Extend `POST /api/index` in `backend/src/codesensei/indexing/api.py` with a pre-scan dispatcher: count source files (via `iter_source_files` from T016) without reading bodies; if `≤ 200` → run `IndexingService.run_sync(...)`; else: create the `repos` row (or fetch it), enqueue `index_repo_job` via `codesensei.tasks.enqueue.enqueue_index_repo(...)`, return 202 with `{"repo_id", "job_id", "mode": "async"}`. Map Redis errors to `IndexError(queue_unavailable)`.
- [ ] T038 [P] [US3] Add `enqueue_index_repo(repo_id, source, source_kind, default_branch) -> str` helper in `backend/src/codesensei/tasks/enqueue.py` (mirrors `enqueue_ping` from 004); raises `JobError(QUEUE_UNAVAILABLE)` on Redis failure.

**Checkpoint**: Async path works end-to-end; idempotency confirmed. T032–T033 pass; quickstart Scenario 3 (Flask clone) succeeds.

---

## Phase 6: User Story 4 — Manage indexed repositories from the UI (Priority: P3)

**Goal**: `/repos` page lets the reviewer submit/re-index/delete repos. `/review` page shows a "Use context from repository" selector when ≥ 1 repo is `ready`. Both pages handle empty states gracefully.

**Independent Test**: open `http://localhost:5173/repos`, submit `https://github.com/pallets/flask.git`, watch the row's status progress from `indexing` to `ready`, click `Delete`, confirm the row vanishes; open `/review`, pick the remaining indexed repo from the selector, run a review, see the `context_files` panel render.

### Tests for User Story 4

- (Frontend tests are out-of-scope for V1 per project conventions — `vue-tsc --noEmit` is the only frontend gate; component tests deferred.)

### Implementation for User Story 4

- [ ] T039 [US4] Create `frontend/src/api/repos.ts` — typed `listRepos()`, `createIndex({source, default_branch})`, `deleteRepo(repo_id)`, `pollJob(job_id)`; types match `contracts/api_index.md` shapes.
- [ ] T040 [P] [US4] Update `frontend/src/api/review.ts` — `runReview` accepts optional `repo_id`; result type includes optional `context_files: string[] | null`; `ReviewApiError` recognises new categories `repo_not_ready`, `embedding_mismatch`.
- [ ] T041 [P] [US4] Create `frontend/src/components/RepoForm.vue` — single form with URL/local-path input, optional `default_branch`, submit button; disables submit while in-flight; surfaces the API error envelope as a readable message.
- [ ] T042 [P] [US4] Create `frontend/src/components/RepoList.vue` — table with columns Source, Status (`ready`/`indexing`/`failed` pill), Chunk count, Indexed at, Actions (Re-index, Delete with confirm); when `status === "indexing"`, polls `/api/jobs/{job_id}` every 2 s until terminal.
- [ ] T043 [P] [US4] Create `frontend/src/components/ContextFilesPanel.vue` — collapsible block under the review verdict, hidden when `context_files === null`, visible with a "no context retrieved" hint when `context_files === []`.
- [ ] T044 [US4] Create `frontend/src/pages/ReposPage.vue` — composes `RepoForm` + `RepoList`; after a successful sync `createIndex` call, refreshes the list immediately; after an async response, pushes the pending row to the list and starts polling.
- [ ] T045 [US4] Update `frontend/src/pages/ReviewPage.vue` — adds the "Use context from repository" `<select>` populated from `listRepos()` filtered to `status === "ready"`; default option is `"(none)"`; selection prokoses through to `runReview(..., repo_id)`. When the list is empty, the selector is hidden and a small hint is shown.
- [ ] T046 [US4] Update `frontend/src/router.ts` and `frontend/src/App.vue` — register `/repos` route; add a topnav `RouterLink` next to `/review` and `/settings`.

**Checkpoint**: UI flow works end-to-end against the live API; quickstart Scenario 4 passes.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: documentation, observability sanity check, integration validation.

- [ ] T047 [P] Run `cd backend && uv run pytest -x -q`; ensure the full suite passes including new tests T010–T026, T032–T033.
- [ ] T048 [P] Run `cd frontend && npx vue-tsc --noEmit`; ensure 0 errors.
- [ ] T049 [P] Run `cd backend && uv run ruff check .` and `uv run ruff format --check .`; fix any drift.
- [ ] T050 Update `README.md` Quick Start: add a `/repos` bullet to the three-page list ("`/repos` — index source repositories so reviews can pull retrieved context"); add a short pointer to `specs/005-rag-indexing/quickstart.md`.
- [ ] T051 Execute every scenario from `specs/005-rag-indexing/quickstart.md` against a `docker compose up --build -d` stack; record the actual chunk counts and `retrieval.done` log lines (these become evidence for the SC-004 / SC-005 measurements).
- [ ] T052 Re-evaluate Constitution Check in `plan.md` after the implementation lands: confirm that no direct OpenAI/Anthropic/Ollama imports leaked into `codesensei.indexing.*` (grep), confirm that the `indexing.complete` and `retrieval.done` log lines carry no chunk/prompt content (grep the test outputs), confirm that the only Dockerfile change is the `git` install.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no deps — start immediately. T002, T003, T004 parallelisable; T001 also.
- **Foundational (Phase 2)**: depends on Phase 1 (T003 must finish so SQLAlchemy can resolve `tiktoken` import in tests; T004 must finish so `docker compose build` doesn't fail mid-run). Within Phase 2, T006/T007/T008 are parallelisable; T005 is sequential (alembic head); T009 depends on T008.
- **US1 (Phase 3)**: depends on Foundational. Within US1, tests T010–T014 are parallelisable; impl T015 stands alone; T016 stands alone; T017 depends on T007 (model); T018 depends on T015+T016+T017; T019 depends on T008+T018; T020 depends on T009+T019; T021 depends on T018.
- **US2 (Phase 4)**: depends on US1 (you need indexed repos to retrieve from). Within US2, tests T022–T026 are parallelisable; T027 depends on T007+T017; T028 stands alone; T029 depends on T027 (chunk shape needed); T030 depends on T027+T028+T029; T031 depends on T008+T030.
- **US3 (Phase 5)**: depends on US1 (reuses `IndexingService`). Within US3, T032/T033 parallelisable; T034 depends on T018; T035 depends on T018; T036 depends on T034; T037 depends on T035+T038+T019; T038 stands alone.
- **US4 (Phase 6)**: depends on US1, US2, US3 (UI surfaces all three). All tasks T039–T046 are parallelisable except T044 (depends on T039+T041+T042), T045 (depends on T040+T043), and T046 (depends on T044+T045).
- **Polish (Phase 7)**: depends on US1+US2+US3+US4.

### Parallel Opportunities (highlights)

- T002/T003/T004 in Phase 1.
- T006/T007/T008 in Phase 2.
- All five test tasks T010–T014 in US1.
- All four test tasks T022–T025 + T026 in US2.
- T039/T040/T041/T042/T043 in US4.
- T047/T048/T049 in Polish.

### Parallel Example: User Story 1 tests

```bash
# Launch all five test tasks together (different files):
Task: "Write backend/tests/unit/test_indexing_chunker.py covering ast/markdown/sliding/binary/oversize."
Task: "Write backend/tests/unit/test_indexing_service.py with AsyncMock embedding provider, cap enforcement, error rollback."
Task: "Write backend/tests/unit/test_indexing_store.py for the atomic T2 swap pattern."
Task: "Write backend/tests/integration/test_index_endpoint.py for the sync path 201/413/502/400."
Task: "Write backend/tests/integration/test_repos_endpoint.py for the listing/ordering/delete-cascade."
```

---

## Implementation Strategy

### MVP scope (User Story 1 only)

1. Phase 1 (Setup) — T001–T004.
2. Phase 2 (Foundational) — T005–T009.
3. Phase 3 (US1) — T010–T021.
4. STOP and validate: index this very project; list it; delete it; reindex it. Demo.

US1 alone delivers a usable indexing pipeline (no review augmentation, no UI, no async) — enough for a thesis chapter on "we can index code". US2 unlocks the actual review augmentation. US3 unlocks scale. US4 wraps it for the demo.

### Incremental delivery

1. MVP (US1) → demo: "look, I can index a repo".
2. + US2 → demo: "look, the review uses retrieved context".
3. + US3 → demo: "and it scales to a real-sized repo".
4. + US4 → demo: "and the operator never has to touch curl".
5. Polish → measurements feed into thesis SC-002/SC-003/SC-004 numbers.

### Solo developer rhythm (you)

- Phase 1+2 in one sitting (≤ 1 h). Commit.
- US1 in one sitting (~3 h). Commit; smoke-test.
- US2 in one sitting (~2 h). Commit.
- US3 in one sitting (~1.5 h). Commit.
- US4 in one sitting (~2 h). Commit.
- Polish (~30 min). Final commit.

Five commits, one PR, one merge.

---

## Notes

- `[P]` means different files, no incomplete-task dependency — safe to fan out.
- `[Story]` label maps to spec.md user stories for traceability.
- Tests are write-first for every chunker/retrieval/store/prompt artefact (Constitution mandate). Glue code (e.g. T020 wiring) doesn't need a write-first gate but the test suite must still be green after.
- Commit at every phase boundary at the latest; intermediate commits welcome.
- The `_decision_log.md` ADR appends in T001/T002 must land **before** any retrieval or async code is written (Constitution II), so they sit in Phase 1.
- Avoid touching `codesensei.providers.factory` / `codesensei.config` / `codesensei.tasks.worker.HEALTH_CHECK_KEY` — those are 002/004 surfaces and a change there is a scope creep that needs a separate ADR.
