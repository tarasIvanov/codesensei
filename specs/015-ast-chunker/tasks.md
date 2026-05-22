---

description: "Task list for feature 015 ast-chunker: cAST + tree-sitter chunker for all supported languages"
---

# Tasks: AST-Based Chunking for All Supported Languages

**Input**: Design documents from `/specs/015-ast-chunker/`
**Prerequisites**: plan.md (loaded), spec.md (loaded), research.md (loaded), data-model.md (loaded), contracts/ast_chunker_module.md (loaded), quickstart.md (loaded)

**Tests**: REQUIRED. The constitution's Workflow §3 ("Test-first for critical paths") enumerates chunking as a critical path; failing tests are committed BEFORE the chunker module.

**Organization**: Tasks are grouped by user story (US1/US2/US3 from spec.md). ADR-017 drafting + dep additions are foundational and MUST land before any story-phase work.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- File paths are absolute repo-relative

## Path Conventions

Web app layout (per `plan.md` §Project Structure): backend at `backend/src/codesensei/...`, tests at `backend/tests/...`. No frontend work in this feature.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: dependencies + tooling needed before any code lands. No code touches `chunker.py` yet.

- [X] T001 Verify on branch `015-ast-chunker` and `main` is fully merged: run `git status` + `git log --oneline main..HEAD` to confirm clean baseline.
- [X] T002 Add deps `tree-sitter>=0.23` and `tree-sitter-language-pack>=0.2` to `backend/pyproject.toml` under `[project] dependencies`.
- [X] T003 Run `uv lock` then `uv sync` inside `backend/` so the lockfile records the new wheel set; commit both `pyproject.toml` and the resulting lockfile delta.
- [X] T004 Smoke-import: from repo root run `cd backend && uv run python -c "from tree_sitter_language_pack import get_parser; p = get_parser('python'); print(type(p).__name__)"` to prove the grammars load with no system toolchain.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: the ADR (Constitution Principle II soft trigger) and the failing-tests scaffold. NO production module touches yet.

**⚠️ CRITICAL**: ADR-017 MUST land before any production code per Constitution Principle II. `test_ast_chunker.py` MUST be committed AS FAILING (red) before `ast_chunker.py` per Constitution Workflow §3.

- [X] T005 Draft ADR-017 in `/Users/tarasivanov/Desktop/Диплом/_decision_log.md`: title "Adopt cAST + tree-sitter-language-pack for multi-language structural chunking", sections: Context / Decision / Consequences. Cover: cAST algorithm (greedy merge + recursive split + gap emission), `tree-sitter-language-pack` over per-language wheels, per-language node-type sets as new Pluggable extension point (Principle III alignment), no DB schema change, users must re-index existing repos to benefit (FR-011), image growth budget ≤ 100 MB (SC-006), no new outbound network (FR-012).
- [X] T006 [P] Create the test scaffold `backend/tests/unit/test_ast_chunker.py` with all 9 test function stubs from spec US3 (each raising `NotImplementedError` or with `pytest.fail("not yet implemented")`); verify `cd backend && uv run pytest tests/unit/test_ast_chunker.py` fails red on all 9 with no import error from the test file itself.
- [X] T007 [P] Add structlog-capture fixture in `backend/tests/unit/conftest.py` (or extend existing) named `captured_log_events` that uses `structlog.testing.capture_logs()` so the routing-event assertions in T011, T016 can read emitted events without scraping stdout. If the fixture already exists from feature 013, reuse it as-is.

**Checkpoint**: ADR-017 committed; 9 failing tests in place; structlog capture fixture available. Implementation can begin.

---

## Phase 3: User Story 1 — Structural chunks for TS/JS + other languages (Priority: P1) 🎯 MVP

**Goal**: `dispatch_chunker(file_path, content)` routes every file with a registered grammar through `chunk_with_treesitter(...)`, producing chunks anchored to real declaration boundaries; sliding-window is the explicit fallback for languages without a grammar.

**Independent Test**: index a small TypeScript fixture (or use `test_typescript_basic` + `test_python_simple_module`); inspect emitted `ChunkSpec` ranges; confirm they line up with `function_declaration` / `class_declaration` / `method_definition` boundaries — not with 80-line slabs.

### Tests for User Story 1 (RED before GREEN)

- [X] T008 [P] [US1] Flesh out `test_python_simple_module` in `backend/tests/unit/test_ast_chunker.py`: 3 top-level `def` functions, assert 3 chunks (or fewer if greedy merge fires for tiny functions — set function bodies large enough to defeat merging at default target=1024), assert correct `start_line`/`end_line`, assert `language == "python"`.
- [X] T009 [P] [US1] Flesh out `test_python_oversize_function_recursive_split` in `backend/tests/unit/test_ast_chunker.py`: synthesise a single function body of > 1500 tokens (pasted `x = 0` lines); assert > 1 chunk; assert no chunk exceeds `target_tokens` unless its leaf is genuinely non-splittable (use `_count_tokens` to verify).
- [X] T010 [P] [US1] Flesh out `test_typescript_basic` in `backend/tests/unit/test_ast_chunker.py`: small `.ts` content with 2 `function_declaration`s + 1 `class_declaration` containing 2 `method_definition`s; assert 3 or 4 chunks (depending on greedy merge), assert `language == "typescript"`, assert no `start_line == end_line == 1` slab.
- [X] T011 [P] [US1] Flesh out `test_javascript_basic` in `backend/tests/unit/test_ast_chunker.py`: small `.js` with 1 `function_declaration` + 2 top-level arrow `const x = () => …`; assert chunks correspond to those declarations, assert `language == "javascript"`.
- [X] T012 [P] [US1] Flesh out `test_target_token_budget_respected_on_merge` in `backend/tests/unit/test_ast_chunker.py`: 5 tiny Python functions whose total `_count_tokens()` is well below 1024; assert chunk count == 1 (greedy merger merged them all). Asserts that the merger actually merges.
- [X] T013 [P] [US1] Flesh out `test_imports_and_top_level_emitted_as_chunks` in `backend/tests/unit/test_ast_chunker.py`: Python source with multi-line imports + module-level constant + one function; assert ≥ 2 chunks (one for the imports/constants region, one for the function); assert no source line above the function is silently dropped.

### Implementation for User Story 1

- [X] T014 [US1] Create `backend/src/codesensei/indexing/ast_chunker.py` with: module-level `_TIKTOKEN_ENCODER = tiktoken.get_encoding("cl100k_base")`, `_count_tokens(text: str) -> int` helper, `@lru_cache(maxsize=None)` wrapper around `tree_sitter_language_pack.get_parser`, `_LANG_LABEL_TO_GRAMMAR: dict[str, str]` (full literal per research §R2, full-name labels matching `chunker.py:_EXT_TO_LANG` values), `_NODE_TYPES_PER_LANG: dict[str, frozenset[str]]` + `_DEFAULT_NODE_TYPES` (full literal per research §R2). NO `chunk_with_treesitter` body yet — leave as `def chunk_with_treesitter(...): raise NotImplementedError`. Verify tests now fail with `NotImplementedError`, not `ImportError`.
- [X] T015 [US1] Implement the cAST algorithm body of `chunk_with_treesitter(content, language, *, target_tokens=1024) -> list[ChunkSpec] | None` in `backend/src/codesensei/indexing/ast_chunker.py`: encode `content.encode("utf-8")`, parse with cached parser, walk root node pre-order collecting splittable subtrees (type ∈ `_NODE_TYPES_PER_LANG[language]` or `_DEFAULT_NODE_TYPES`), greedy-merge adjacent siblings while running `_count_tokens` stays ≤ target, recursive descent on oversize singletons, gap-emission for non-whitespace interstitial source, 1-based `start_line = node.start_point.row + 1` etc. Return `None` if `language not in _LANG_LABEL_TO_GRAMMAR`. Return `[]` only when content is empty/whitespace. Raise nothing observable to caller — wrap walk in `try`/`except Exception → return None`.
- [X] T016 [US1] Rewire `dispatch_chunker(file_path, content)` in `backend/src/codesensei/indexing/chunker.py` per contract `contracts/ast_chunker_module.md` §"Caller contract": resolve `lang = language_for(Path(file_path))`; on `lang == "other"` log `mode="sliding_no_extension"` + return `chunk_sliding`; on `lang not in _LANG_LABEL_TO_GRAMMAR` (import from `ast_chunker`) log `mode="sliding_no_grammar"` + return `chunk_sliding`; otherwise `try: chunks = chunk_with_treesitter(content, lang)` with broad `except Exception` → log `mode="sliding_parse_failed"` + `chunk_sliding`. On `chunks is None` → same fallback. On success log `mode="ast"` + `count=len(chunks)`. KEEP `chunk_python` and `chunk_markdown` defined in the file but route them through the new path (Python label gets AST via the grammar pack; old `chunk_python` becomes dead code reachable only by direct call from tests — leave it in for now, mark `# kept for direct-call legacy tests` if needed).
- [X] T017 [US1] Add per-run summary log in `chunk_repo(...)` in `backend/src/codesensei/indexing/chunker.py`: accumulate a `dict[str, int]` of `mode → count` during iteration (sneak a small wrapper around `dispatch_chunker` or use structlog's `contextvars` to thread the count up); at end emit `log.info("chunker_run_summary", total=..., by_mode=...)`.
- [X] T018 [US1] Run `cd backend && uv run pytest tests/unit/test_ast_chunker.py -k "python or typescript or javascript or imports or target"` and verify T008–T013 are now GREEN. Fix any per-language node-type-set issue revealed (e.g. greedy merger needs adjustment for tiny TS classes).
- [X] T019 [US1] Run the full existing chunker test `cd backend && uv run pytest tests/unit/test_indexing_chunker.py` and surface any chunk-count assertion that changed. Inspect each failure: if greedy merger legitimately produced a different (typically lower) count, update the assertion; otherwise treat as a bug in T015 and fix.

**Checkpoint**: TS/JS/Python files emit AST chunks; tests US1's 6 fleshed cases plus the existing chunker test pass; `dispatch_chunker` routes via the new path.

---

## Phase 4: User Story 2 — Reliable fallback (Priority: P2)

**Goal**: sliding-window fallback fires explicitly + observably on every non-AST-handled path (no grammar, parse failed, unknown extension). Indexing never fails on one weird file.

**Independent Test**: drop a broken `.ts` + a `.cobol` file into a fixture repo; index it; assert run succeeds; assert routing log shows `mode="sliding_parse_failed"` for the broken file and `mode="sliding_no_grammar"` for the Cobol file (or `sliding_no_extension` if `.cobol` isn't in `SUPPORTED_EXTS`, which it shouldn't be — `iter_source_files` filters it out before `dispatch_chunker` ever sees it; in that case the test calls `dispatch_chunker` directly).

### Tests for User Story 2 (RED before GREEN)

- [X] T020 [P] [US2] Flesh out `test_unsupported_language_falls_back_to_sliding` in `backend/tests/unit/test_ast_chunker.py`: call `dispatch_chunker("foo.cobol", "PROGRAM HELLO. END.")` directly (bypassing `iter_source_files`); assert returned list is non-empty; assert every `ChunkSpec.language` is `"other"`; assert `captured_log_events` contains one `chunker_routing` with `mode="sliding_no_extension"`.
- [X] T021 [P] [US2] Flesh out `test_parse_failure_falls_back_to_sliding` in `backend/tests/unit/test_ast_chunker.py`: feed `dispatch_chunker("broken.ts", "function broken(\n THIS IS NOT TYPESCRIPT &&& %%%")` — tree-sitter is forgiving so this MIGHT still parse with errors; alternative: monkey-patch `ast_chunker.chunk_with_treesitter` to raise `RuntimeError` and assert the `except Exception` in `dispatch_chunker` swallows it, emits `mode="sliding_parse_failed"`, and returns sliding-window chunks.

### Implementation for User Story 2

- [X] T022 [US2] In `backend/src/codesensei/indexing/ast_chunker.py`, ensure the body of `chunk_with_treesitter` returns `None` rather than raising for these conditions: `language not in _LANG_LABEL_TO_GRAMMAR` (covered by T015); parser loaded but `parser.parse` raised; walker raised; result has zero splittable nodes AND root node `has_error` is True (use Tree-sitter's `node.has_error` to detect unrecoverable parse). Keep the broad `except Exception → return None` as the safety net.
- [X] T023 [US2] Verify the routing log shape from T016 includes `exc_info=True` only when an exception was caught (per contract). If it currently logs `exc_info=True` for `chunks is None` cases, drop it.
- [X] T024 [US2] Run `cd backend && uv run pytest tests/unit/test_ast_chunker.py -k "unsupported or parse_failure"` and verify T020 + T021 are now GREEN.

**Checkpoint**: weird files no longer crash indexing; routing taxonomy is observable.

---

## Phase 5: User Story 3 — Visibility into chunk routing (Priority: P3)

**Goal**: per-file + per-run routing events let the defence demo answer "how many files in this repo were AST-chunked vs sliding-window fallback?".

**Independent Test**: index a mixed-language fixture; grep structlog output; confirm one `chunker_routing` per file + exactly one `chunker_run_summary` at end of `chunk_repo`.

### Tests for User Story 3 (RED before GREEN)

- [X] T025 [P] [US3] Flesh out `test_markdown_with_treesitter_grammar` in `backend/tests/unit/test_ast_chunker.py`: small Markdown with two `##` sections; assert ≥ 2 chunks; assert `language == "markdown"`; assert the routing log says `mode="ast"` (if the language pack ships a markdown grammar) — otherwise the test should `pytest.skip("markdown grammar not available")` after a one-time probe.

### Implementation for User Story 3

- [X] T026 [US3] In `backend/src/codesensei/indexing/chunker.py:chunk_markdown`, gate the call between tree-sitter-markdown and the existing heading splitter: if `"markdown" in _LANG_LABEL_TO_GRAMMAR` AND `chunk_with_treesitter(content, "markdown")` returns non-None non-empty, use it; otherwise fall through to the existing `_chunk_markdown_by_headings`-shaped path that lives in the function today. Routing-event mode stays consistent with the dispatch contract.
- [X] T027 [US3] Add a one-time module-load probe: at the bottom of `ast_chunker.py`, attempt `get_parser("markdown")`; on failure, log once at `info` level `"markdown_grammar_unavailable"` and pop `"markdown"` out of `_LANG_LABEL_TO_GRAMMAR` so `dispatch_chunker` cleanly routes markdown to the sliding/heading-splitter fallback.
- [X] T028 [US3] Run `cd backend && uv run pytest tests/unit/test_ast_chunker.py -k "markdown"` and verify T025 is GREEN (or correctly skipped on environments without the grammar).

**Checkpoint**: routing events make the AST-vs-fallback story observable end-to-end.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: image-size enforcement, full-suite regression, quickstart validation, docs sweep.

- [X] T029 [P] Run the entire backend test suite: `cd backend && uv run ruff check . && uv run pytest`. Fix any ruff issues (likely B008, B007, B904, E501 in the new module) and any pre-existing test that broke from the `chunker.py` edit. **Result: 343 passed, ruff clean.**
- [ ] T030 [P] Measure backend image growth: `docker compose build backend worker && docker images codesensei-backend --format '{{.Size}}'`. **Deferred** — requires running docker compose locally; record actual delta in ADR-017 at next deploy.
- [ ] T031 [P] Smoke-run quickstart.md sections 1–7. **Deferred** — requires docker compose stack; user to run before merge.
- [X] T032 [P] README.md / `_mvp_scope.md` sweep: confirm the "AST-RAG index" differentiator language reads true for non-Python languages. **Done — README §2 of differentiators now lists all 13 supported languages + cAST algorithm name.**
- [X] T033 Final pass on `_decision_log.md`: ADR-017's Consequences section records the language coverage. Image delta to be appended after T030 runs.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies; T001 → T002 → T003 → T004 sequential because each touches the dep state.
- **Foundational (Phase 2)**: depends on Setup. T005 (ADR) is **independent** of T006/T007 (test scaffold); the three can run in parallel between two people but a single agent should land T005 first (Constitution rule).
- **User Story 1 (Phase 3)**: depends on Foundational. Inside: T008–T013 are [P] (different test cases in the same file — adjacent edits, no race), then T014 (module skeleton) → T015 (algorithm body) → T016 (dispatch rewire) → T017 (summary log) sequentially because each touches the same file. T018 and T019 are verification tasks.
- **User Story 2 (Phase 4)**: depends on US1 complete because the dispatch wiring is the entry point. T020 + T021 [P]. T022 sequential with T015's file. T023 + T024 verification.
- **User Story 3 (Phase 5)**: depends on US1. T025 standalone; T026 + T027 touch the same two files sequentially. T028 verification.
- **Polish (Phase 6)**: depends on all stories. T029/T030/T031/T032 [P] (independent surfaces). T033 last.

### User Story Dependencies

- US1 (P1): foundational only.
- US2 (P2): US1 (dispatch contract relies on US1's rewire).
- US3 (P3): US1 (markdown gate sits on top of US1's `_LANG_LABEL_TO_GRAMMAR`).

### Within Each User Story

- Failing tests committed BEFORE implementation per Constitution Workflow §3.
- Module skeleton before algorithm body.
- Algorithm body before dispatch rewire.
- Dispatch rewire before run-summary log.

### Parallel Opportunities

- T006 + T007 can run in parallel within Foundational.
- T008–T013 in parallel within US1's test phase.
- T020 + T021 in parallel within US2's test phase.
- T029–T032 in parallel within Polish.

---

## Parallel Example: User Story 1

```bash
# Six US1 test cases in parallel (all edit the same file but adjacent
# functions — coordinate by writing one function each):
Task: "Flesh out test_python_simple_module"
Task: "Flesh out test_python_oversize_function_recursive_split"
Task: "Flesh out test_typescript_basic"
Task: "Flesh out test_javascript_basic"
Task: "Flesh out test_target_token_budget_respected_on_merge"
Task: "Flesh out test_imports_and_top_level_emitted_as_chunks"

# Implementation: strictly sequential — all touch ast_chunker.py and chunker.py
# T014 → T015 → T016 → T017 → T018 → T019
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phase 1 Setup (T001–T004): deps in, lockfile updated, smoke-import passes.
2. Phase 2 Foundational (T005–T007): ADR-017 drafted, 9 failing tests in the test file, structlog capture fixture available.
3. Phase 3 US1 (T008–T019): MVP — TS/JS/Python files get AST chunks; existing chunker test stays green.
4. **STOP and VALIDATE**: spot-check via quickstart §3–§5 (index a small TS repo).
5. Decide whether to ship US1 alone or continue.

### Incremental Delivery

- After US1 (MVP): visible improvement — TS/JS/Go/Rust chunks are now structural for any operator who re-indexes.
- After US2: weird files no longer destabilise indexing.
- After US3: defence demo can answer "how much of your index is AST?" from logs.

### Constitution Gate

- ADR-017 (T005) **MUST** land before T014 (production module) per Principle II. Skipping is a constitution violation; the implementation phase cannot begin until ADR-017 is committed.

---

## Notes

- [P] tasks = different files OR adjacent test functions in the same file.
- Tests are written FIRST and must FAIL red before T014 starts (Constitution Workflow §3).
- After EACH major task (T015, T016, T017, T026), run the full `uv run pytest backend/tests` to catch upstream regressions early.
- Do NOT remove `chunk_sliding` or `chunk_python` from `chunker.py` — they are the documented fallback path and direct-call legacy targets.
- Do NOT touch `backend/src/codesensei/review/service.py:MAX_CHUNK_TOKENS` — the upstream halver is intentionally left in place (research §R5).
- Image-size verification (T030) is a hard gate on SC-006; record the delta in ADR-017 even if it passes.
