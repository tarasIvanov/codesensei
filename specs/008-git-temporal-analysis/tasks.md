# Tasks — Feature 008: Git Temporal Analysis

**Feature**: `008-git-temporal-analysis`
**Plan**: [plan.md](./plan.md)
**Spec**: [spec.md](./spec.md)

Tests are in scope per plan.md: backend pytest unit (real-subprocess on tmp_path repo), backend pytest integration (mocked fetcher), backend pytest unit (prompt delta). Manual frontend smoke via [quickstart.md](./quickstart.md). No Vitest.

---

## Phase 1 — Setup

- [X] T001 Sync feature scaffolding: confirm `.specify/feature.json` points to `specs/008-git-temporal-analysis`, confirm CLAUDE.md SPECKIT marker points to `specs/008-git-temporal-analysis/plan.md`; both should already be set by `/speckit-plan` — this is a verify-and-fix-if-needed step.
- [X] T002 Verify the runtime environment will have `git` available inside the API container: read `backend/Dockerfile` and confirm `git` is in the apt-installed list (it is, for `indexing/clone.py`) — no change required, this is a documentation check captured in the task receipt.

## Phase 2 — Foundational (blocking prerequisites for all user stories)

- [X] T003 Add wire-shape Pydantic model `TemporalEntry` (+ `model_config = ConfigDict(extra="ignore")`) to `backend/src/codesensei/review/schema.py`; fields per [data-model.md](./data-model.md): `commit_sha: str`, `short_sha: str`, `author_email: str`, `author_date: str`, `subject: str`, `hunk_lines_changed: int`. Include a `_truncate`-based field validator on `subject` capping at 120 chars with `…` suffix.
- [X] T004 Extend `Finding` in `backend/src/codesensei/review/schema.py` with `temporal_context: list[TemporalEntry] | None = None`; configure model dump to `exclude_none=True` at the call site in `review/service.py` (do NOT change pydantic's default exclude behavior — call-site only).
- [X] T005 Add module-level dataclasses `TemporalEntry` (pure data) and `LineWindow` (`start_line: int`, `end_line: int`, both `frozen=True, slots=True`) to a brand-new file `backend/src/codesensei/review/git_temporal.py`; stub `async def fetch_temporal_context(...)` returning `[]` and `async def fetch_temporal_pool_for_review(...)` returning `({}, summary_zero)` so downstream code can import without circular issues during US1 implementation. Empty stubs only — real logic comes in T010–T013.
- [X] T006 Add module-private constants block to `backend/src/codesensei/review/git_temporal.py` exactly as in [contracts/git_temporal_module.md](./contracts/git_temporal_module.md) (`_CACHE_ROOT`, `_MAX_CACHED_REPOS=5`, `_CALL_TIMEOUT_S=1.5`, `_TOTAL_BUDGET_S=2.0`, `_STALE_CLONE_S=3600`, `_MAX_LINE_RANGE=200`, `_MAX_WINDOWS_PER_FILE=3`, `_MAX_ENTRIES_PER_WINDOW=5`, `_PRETTY_FORMAT`).
- [X] T007 Add module-level `_logger = structlog.get_logger(__name__)` and the `_clone_for_test: Callable[[str], Path] | None = None` test seam attribute to `backend/src/codesensei/review/git_temporal.py`.

---

## Phase 3 — User Story 1 (P1) — Collect history per line window + surface inline

**Goal**: After a review against an indexed repo, every finding with `(file, line)` carries a History disclosure when the diff range has history; the diff-only path is silent.

**Independent test**: index a public HTTPS repo, run a review with the indexed repo selected against a PR touching a file with history; expand any finding → History rows render. Run the same review without an indexed repo → no rows anywhere, response shape is byte-identical to pre-feature.

### Tests (TDD — failing tests committed first)

- [X] T008 [US1] Add `backend/tests/unit/test_git_temporal.py` with a `_make_git_repo` fixture that builds a synthetic git repo under pytest `tmp_path` via `subprocess.run(["git", ...], check=True)`: init repo, configure user.email/user.name, create a file `src/x.py` with 5 lines, commit, modify lines 2-3, commit, modify line 4, commit. Yield `Path`.
- [X] T009 [P] [US1] In `backend/tests/unit/test_git_temporal.py` add 7 test cases (all currently failing because T010–T013 stubs return empty): (a) happy 3-commit history returns 3 `TemporalEntry`s in newest-first order, (b) non-existent file returns `[]`, (c) line range outside file returns `[]`, (d) `max_commits=2` cap returns exactly 2 entries, (e) subject longer than 120 chars is truncated with `…`, (f) line window > 200 lines is clamped to start..start+199, (g) non-HTTPS source (`/local/path`) returns `[]` silently with no log. Use `monkeypatch.setattr(git_temporal, "_clone_for_test", lambda src: synthetic_repo_path)` to short-circuit clone.

### Implementation

- [X] T010 [US1] Implement `_clone_or_reuse(repo_source: str) -> Path | None` in `backend/src/codesensei/review/git_temporal.py`: return `_clone_for_test(repo_source)` when the seam is set; otherwise compute `sha1(repo_source.encode("utf-8")).hexdigest()`, derive `cache_dir = _CACHE_ROOT / digest`. If `cache_dir` does not exist, `await _clone(repo_source, cache_dir)`; if it exists and `time.time() - stat.st_mtime > _STALE_CLONE_S`, `await _fetch(cache_dir)`. Then `os.utime(cache_dir, None)`. Return cache_dir. Return `None` for non-HTTPS sources.
- [X] T011 [US1] Implement `_clone(source, dest)` in `backend/src/codesensei/review/git_temporal.py` using `asyncio.create_subprocess_exec("git", "clone", "--filter=blob:none", "--no-checkout", source, str(dest), env={"GIT_TERMINAL_PROMPT":"0","GIT_ASKPASS":"/bin/true","PATH":os.environ["PATH"]}, stdout=PIPE, stderr=PIPE)` with `await proc.communicate()`. On non-zero exit, raise `_TemporalSubprocessError(first_stderr_line)`. Implement `_fetch(cache_dir)` similarly with `["git", "-C", str(cache_dir), "fetch", "--all", "--prune", "--quiet"]`. Both wrapped in `asyncio.wait_for(timeout=_CALL_TIMEOUT_S)`.
- [X] T012 [US1] Implement an LRU eviction helper `_evict_if_needed()` in `backend/src/codesensei/review/git_temporal.py`: list `_CACHE_ROOT.iterdir()`, drop entries that aren't directories, sort by `st_mtime` asc, while `len > _MAX_CACHED_REPOS` `shutil.rmtree(oldest)`. Call it from `_clone_or_reuse` AFTER a successful clone but BEFORE returning.
- [X] T013 [US1] Implement the full `async def fetch_temporal_context(repo_source, file_path, window, *, max_commits=_MAX_ENTRIES_PER_WINDOW)` in `backend/src/codesensei/review/git_temporal.py`: clamp `window.end_line - window.start_line + 1` to `_MAX_LINE_RANGE`; resolve cache via `_clone_or_reuse`; if `None`, return `[]`; spawn `git -C <cache_dir> log -L <s>,<e>:<file> -n <max_commits> --pretty=format:<_PRETTY_FORMAT> --no-patch --no-color` wrapped in `asyncio.wait_for(_CALL_TIMEOUT_S)`; parse TAB-separated stdout → `list[TemporalEntry]`. On any of `OSError, asyncio.TimeoutError, _TemporalSubprocessError, UnicodeDecodeError, ValueError, IndexError`, return `[]` after one `_logger.warning("temporal_fetch_failed", repo_source=…, file_path=…, reason=str(e)[:200])`. Run the secondary `--unified=0` pass for the first ≤ 8 SHAs to populate `hunk_lines_changed`; on its failure, leave the field at 0 silently.
- [X] T014 [P] [US1] Implement `collapse_diff_to_windows(rhs_hunks_by_file)` in `backend/src/codesensei/review/git_temporal.py`: for each file, walk sorted hunks `(start, length)`, merge adjacent hunks whose gap ≤ 5 lines, clamp each merged range to ≤ 200 lines, keep the 3 lowest-line windows. Return `dict[str, list[LineWindow]]`.
- [X] T015 [US1] Implement `async def fetch_temporal_pool_for_review(*, repo_id, repo_source, windows_by_file)` in `backend/src/codesensei/review/git_temporal.py`: track `t0 = time.perf_counter()`; use `asyncio.TaskGroup` with one task per (file, window) pair calling `fetch_temporal_context`; before scheduling each child, check `(time.perf_counter() - t0) > _TOTAL_BUDGET_S` and short-circuit setting `summary.budget_exceeded = True`; collect results into `FileTemporalPool`; drop files whose every window-entries-list is empty; return `(pool, summary)`.
- [X] T016 [P] [US1] Add an async lock layer: `_clone_locks: WeakValueDictionary[str, asyncio.Lock] = WeakValueDictionary()` module-level; in `_clone_or_reuse` acquire `_clone_locks.setdefault(digest, asyncio.Lock())` around the clone-or-fetch transition (NOT around the `git log` read). Add a unit test in `backend/tests/unit/test_git_temporal.py` that fires 3 concurrent `fetch_temporal_context` calls for the same source and asserts the clone monkeypatch is invoked exactly once (use a counter wrapper around the `_clone_for_test` seam).
- [X] T017 [US1] Modify `backend/src/codesensei/review/service.py`:
  - After the existing RAG retrieval block (around the `_retrieve_context` call site), if `repo_id is not None`, fetch `repo = await repos_store.fetch_repo(repo_id)` (resolve the import — `from codesensei.indexing import store as repos_store`), call `windows = collapse_diff_to_windows(hunks_by_file)` (derive `hunks_by_file` from the existing diff parse — reuse `review/github_diff.py:parse_hunks`), then `pool, summary = await fetch_temporal_pool_for_review(repo_id=repo_id, repo_source=repo.source, windows_by_file=windows)`.
  - Emit `_logger.info("temporal_fetch", repo_id=repo_id, files_count=summary.files_count, entries_total=summary.entries_total, elapsed_ms=summary.elapsed_ms, budget_exceeded=summary.budget_exceeded)` exactly once on this path.
  - When `repo_id is None`, do NOT call any temporal code; do NOT log `temporal_fetch`.
- [X] T018 [US1] After the LLM returns findings in `backend/src/codesensei/review/service.py`, walk `findings` and for each `f` with `f.line is not None`: lookup `pool.get(f.file)`; if found, find the first `(window, entries)` whose `window.start_line ≤ f.line ≤ window.end_line` AND `entries`; convert each `TemporalEntry` dataclass to the pydantic `TemporalEntry` (constructor with `**asdict(entry)`); assign to `f.temporal_context`. Findings without match keep `None`.
- [X] T019 [P] [US1] Add `backend/tests/integration/test_review_with_temporal.py`: monkeypatch `codesensei.review.service.fetch_temporal_pool_for_review` to return a deterministic `FileTemporalPool` with one file `src/x.py` carrying one window `LineWindow(40, 60)` with 2 entries; monkeypatch `codesensei.review.service._run_chat`'s LLM call to emit 2 findings — one matching `(src/x.py, 45)` (should get `temporal_context`) and one matching `(src/y.py, 12)` (should get `None`). Drive end-to-end via the existing `async_client` fixture against `/api/review/run` with a fake `repo_id`. Assert response body shape per [contracts/review_response.md](./contracts/review_response.md).
- [X] T020 [P] [US1] Add the front-end TypeScript type: in `frontend/src/api/review.ts` (or wherever `Finding` is declared — locate via `grep -nE "interface Finding|type Finding" frontend/src/api/`), add `temporal_context?: TemporalEntry[] | null;` and define `interface TemporalEntry { commit_sha: string; short_sha: string; author_email: string; author_date: string; subject: string; hunk_lines_changed: number; }`. Keep snake_case. Do not rename existing fields.
- [X] T021 [US1] Modify `frontend/src/components/findings/FindingRow.vue`:
  - Import the in-tree `Collapsible` primitive from `@/components/primitives/Collapsible.vue` (it's the one shipped by 007).
  - After the existing code-context snippet block (or after the suggestion block if code-context is absent), render `<Collapsible v-if="finding.temporal_context && finding.temporal_context.length > 0" :title="\`History (${finding.temporal_context.length} changes)\`" :default-open="false">` and inside, a `<table class="text-xs">` with 4 columns: short SHA (tinted `text-muted`), date (slice `author_date.slice(0,10)` → YYYY-MM-DD), author local-part (split `author_email` on `@` first segment), subject (truncated to 80 chars + `…`).
  - Do NOT touch the severity-pill block (US3 will add the badge there).
- [X] T022 [US1] Frontend type-check guard: run `corepack pnpm -C frontend exec vue-tsc --noEmit` and confirm exit 0. (No new file — this is a verification task tied to T020/T021.)

**Checkpoint**: US1 complete → backend pytest green (unit + integration), frontend type-check clean. Reviewer can run a review against an indexed repo and see History disclosures on findings.

---

## Phase 4 — User Story 2 (P2) — LLM gets "Code history hints" in the prompt

**Goal**: When temporal collection produced ≥ 1 entry, the LLM prompt carries a "Code history hints" block before the diff; when zero entries, the block is omitted in full; the diff-only path is byte-identical to pre-feature.

**Independent test**: a pytest unit on `review/prompt.py:build_user_message(...)` exercising three branches (non-empty pool → block present and formatted; empty pool → block absent; same diff with `pool=None` → byte-equal to a captured pre-feature golden string).

### Tests

- [X] T023 [US2] Add `backend/tests/unit/test_prompt_temporal.py` with three cases: (a) non-empty pool of two files yields a prompt whose body contains "Code history hints" header followed by per-file blocks (assert literal strings), (b) empty pool yields a prompt that does NOT contain the header substring at all, (c) `pool=None` yields a prompt byte-identical to the pre-feature build (capture pre-feature output by calling the same function with `pool=None` and assert against a snapshot string in the test file body). All currently failing because T024 hasn't shipped.

### Implementation

- [X] T024 [US2] Modify `backend/src/codesensei/review/prompt.py`: locate the user-message builder (`build_user_message` / equivalent — find it with `grep -nE "user_message|user_prompt|def build" backend/src/codesensei/review/prompt.py`). Add a new keyword-only parameter `pool: FileTemporalPool | None = None`. When `pool` is non-empty (at least one file with ≥ 1 entry across its windows), render a block BEFORE the diff:

  ```text
  Code history hints (these lines have changed recently — consider whether your fix is consistent with recent intent):

  File: <path> (lines <start>-<end>)
  Recent commits touching these lines:
    - <short_sha> <YYYY-MM-DD> <author_email>: <subject>
    - …

  File: …
  ```

  When `pool` is `None` or every file is empty, append nothing — the prompt stays byte-identical to the pre-feature shape.
- [X] T025 [US2] Modify `backend/src/codesensei/review/service.py` to thread `pool` through to the prompt builder call (one keyword argument added). Verify the pool produced in T015 is available at that call site.

**Checkpoint**: US2 complete → `test_prompt_temporal.py` green; running a review against an indexed repo now shows `temporal_fetch` info in API logs alongside an LLM prompt that visibly contains the hints block (verifiable manually by tee-ing the prompt in a dev `_logger.debug` call — NOT shipped to production logs; only used by the developer during smoke).

---

## Phase 5 — User Story 3 (P3) — Volatility "N changes" badge on finding header

**Goal**: Findings with `temporal_context.length ≥ 3` show an inline "N changes" badge next to the severity pill; fewer → no badge. Text-based (no colour-only signal).

**Independent test**: Render two findings (one with 4 entries, one with 0) — visually confirm badge presence/absence on the right finding. (No additional pytest needed — this is a pure-UI delta.)

### Implementation

- [X] T026 [US3] In `frontend/src/components/findings/FindingRow.vue`, locate the severity-pill row in the finding header. Import the in-tree `Badge` primitive from `@/components/primitives/Badge.vue`. Render `<Badge v-if="finding.temporal_context && finding.temporal_context.length >= 3" variant="info">{{ finding.temporal_context.length }} changes</Badge>` immediately after the `<SeverityPill>`, inside the same flex row, with `class="text-xs"`. Do not change the severity pill itself.
- [X] T027 [US3] Frontend type-check + a manual visual smoke spot in `quickstart.md` Step 4 — confirm the badge renders with `N changes` text only (no colour-only marker) for colour-blind users.

**Checkpoint**: US3 complete → frontend type-check clean; `quickstart.md` Step 4 passes visually.

---

## Phase 6 — Polish & Cross-Cutting

- [X] T028 [P] Append a paragraph to ADR-011 *Notes* in `/Users/tarasivanov/Desktop/Диплом/_decision_log.md` documenting the soft-trigger shipping shape: runtime cache at `/var/tmp/codesensei-temporal/` (LRU 5 entries, mtime eviction, 1 h stale window, 1.5 s per-call timeout, 2.0 s per-review total budget, ≤ 3 windows × ≤ 200 lines × ≤ 5 entries per window). Note that this is a **soft-trigger** record because Constitution Principle II's hard triggers (schema/queue/framework/provider/deployment/posting) are not crossed.
- [X] T029 [P] Update `README.md` `/review` blurb: add a sentence that findings against indexed repositories now carry a collapsible "History (N changes)" block listing the recent commits that touched the same line range, and that high-volatility lines are flagged with a small inline badge. Append a link to `specs/008-git-temporal-analysis/quickstart.md`.
- [X] T030 Run backend lint + format gate from repo root: `cd backend && ruff check . && ruff format --check .` — fix any flagged files this feature introduced (do NOT format pre-existing files in unrelated paths). Then `cd backend && mypy src/codesensei/review/git_temporal.py` and confirm clean.
- [X] T031 Run backend test suite from repo root: `cd backend && pytest tests/unit/test_git_temporal.py tests/unit/test_prompt_temporal.py tests/integration/test_review_with_temporal.py -q` — confirm all green.
- [X] T032 Run full backend test suite (regression guard): `cd backend && pytest -q` — confirm green or only fail on tests that were already broken on `main` (none should be).
- [X] T033 Run frontend type check + build: `corepack pnpm -C frontend exec vue-tsc --noEmit && corepack pnpm -C frontend exec vite build` — confirm exit 0 on both and the resulting bundle does NOT regress beyond +5 KB gzipped JS vs feature 007's baseline.
- [X] T034 Manual smoke per `specs/008-git-temporal-analysis/quickstart.md` Steps 1–8 — **deferred to the user** per project convention (user runs smoke separately).
- [X] T035 Mark all task checkboxes `[X]` in this file at the end of `/speckit-implement` (this is the standard final-step convention).

---

## Dependencies

```
Phase 1 Setup (T001–T002) ─┐
Phase 2 Foundational (T003–T007) ─┤
                                  │
                                  ├─► Phase 3 US1 (T008–T022) ─┐
                                  │                            │
                                  └─► (no other dependency)    ├─► Phase 4 US2 (T023–T025)
                                                               │
                                                               └─► Phase 5 US3 (T026–T027)

Phase 6 Polish (T028–T035) requires all prior phases done.
```

- US2 depends on US1 because the prompt builder needs the pool entity defined in T015.
- US3 depends on US1 because it edits the same `FindingRow.vue` that US1 already populated.
- US2 and US3 do not depend on each other; they can ship in either order after US1.

## Parallel opportunities

- T009 + T019 + T020 can run in parallel (different files, no overlap).
- T028 + T029 can run in parallel (different files, doc-only).
- T030 / T033 are independent gates that can run in parallel.

## Implementation strategy

- **MVP scope = US1 only** (Phase 3). Ships the feature end-to-end: backend module + service wiring + Finding field + History disclosure. The LLM-prompt and volatility-badge slices are valuable but additive.
- After MVP, ship US2 (prompt hint) and US3 (volatility badge) in either order; they're independent.
- Polish (Phase 6) ships at the end of `/speckit-implement` together with the single commit at the pipeline boundary.

## Independent-test criteria per story

- **US1**: index a public repo, run a review with `repo_id` set against a PR that touches a file with history → at least one finding shows a History disclosure with ≥ 1 row. Run the same review without `repo_id` → zero disclosures anywhere, response body has `temporal_context` absent (or `null`) on every finding.
- **US2**: pytest `test_prompt_temporal.py` green; the three branches assert the prompt body is byte-correct.
- **US3**: open a review whose findings include ≥ 1 with `temporal_context.length ≥ 3` → that finding shows an "N changes" badge inline with its severity pill; another finding without enough history shows no badge.

## Format validation

All 35 tasks above start with `- [X]`, carry a `Txxx` ID, the appropriate `[P]` and `[US?]` markers, and reference at least one concrete file path (or contracted document). No "create model" without a path; no missing checkboxes.
