---
description: "Task list for 014-ux-polish-and-readme"
---

# Tasks: UX polish — drop Recent row, reformat tokens, write README

**Input**: Design documents from `/specs/014-ux-polish-and-readme/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md
**Tests**: pytest unit (per spec.md §Tests). No frontend Vitest.
**Organization**: Tasks grouped by user story for independent verification.

## Format

`- [ ] TID [P?] [Story?] Description with file path`

## Path Conventions

Web app — `backend/src/`, `backend/tests/`, `frontend/src/`, repo root for `README.md`. Repository root anchors all paths.

---

## Phase 1: Setup

**Purpose**: Branch placement (no Constitution II hard trigger).

- [X] T001 Verify branch `014-ux-polish-and-readme` is checked out and clean of unrelated edits via `git status -s` (working tree may contain only `specs/014-ux-polish-and-readme/*` + `.specify/feature.json` + `CLAUDE.md` marker bumps from /speckit-plan).

**Checkpoint**: branch verified → no ADR required → straight to user-story phases.

---

## Phase 2: Foundational

**Purpose**: NONE. No DB migration, no new env var, no infra change. Skipped.

---

## Phase 3: User Story 1 — Token usage shown where it matters (Priority: P1) 🎯 MVP

**Goal**: drop the token/cost line from `/review`; shorten `/history/<id>` to a single `N tokens · ~$X.XXXX` line; add `Embedding tokens` row to `/repos` sourced from `SUM(code_chunks.token_count) GROUP BY repo_id`.

**Independent Test**: run a review on `/review` → no `tokens`/`~$` line; open same run on `/history/<id>` → one combined-total line; visit `/repos` → each card shows comma-separated `Embedding tokens`. Quickstart Steps 1, 3, 5.

### Tests for User Story 1

- [X] T002 [P] [US1] Write unit tests in `backend/tests/unit/test_indexing_aggregates.py` (NEW). Three cases: (a) 1 Repo + 3 CodeChunks with token_count 100/200/300 → `get_embedding_token_counts(session, [repo.id]) == {repo.id: 600}`; (b) 2 repos (r1 with chunks 100+200, r2 with 0 chunks) → `{r1.id: 300, r2.id: 0}`; (c) empty `repo_ids` list → `{}`. Use the existing async fixture infrastructure (pattern from `tests/unit/test_indexing_service.py`); if no in-memory session fixture is reusable, monkeypatch the aggregate to verify the SQL shape via captured statement.

### Implementation for User Story 1

- [X] T003 [P] [US1] Add `async def get_embedding_token_counts(session: AsyncSession, repo_ids: Sequence[UUID]) -> dict[UUID, int]` to `backend/src/codesensei/indexing/store.py`. Body: `select(CodeChunk.repo_id, func.sum(CodeChunk.token_count).label("total")).where(CodeChunk.repo_id.in_(list(repo_ids))).group_by(CodeChunk.repo_id)`. Empty list → return `{}` without round-tripping. Wrap result as `{row.repo_id: int(row.total) for row in result.all()}`.
- [X] T004 [US1] Modify `backend/src/codesensei/indexing/service.py:list_repos`. After `rows = await list_repos_ordered(session)`, call `aggregates = await get_embedding_token_counts(session, [r.id for r in rows])`. Extend `_serialise_repo` signature with `*, embedding_token_count: int = 0`; include the field in the returned dict. Update `list_repos`'s comprehension to pass `embedding_token_count=aggregates.get(r.id, 0)`. Import `get_embedding_token_counts` from `codesensei.indexing.store`. Depends on T003.
- [X] T005 [P] [US1] Extend frontend type `RepoEntry` in `frontend/src/api/repos.ts` with `embedding_token_count?: number | null`.
- [X] T006 [P] [US1] Modify `frontend/src/components/RepoList.vue` — inside the existing per-repo `<dl>`, between the `Chunks` row and the `Indexed at` row, insert a new row: `<dt class="text-xs uppercase tracking-wide text-muted">Embedding tokens</dt><dd class="font-mono" :style="{ color: 'var(--color-text)' }">{{ formatThousands(r.embedding_token_count ?? 0) }} tokens</dd>`. Add a `function formatThousands(n: number): string { return n.toLocaleString('en-US') }` helper inside the existing `<script setup lang="ts">` block.
- [X] T007 [US1] Modify `frontend/src/pages/ReviewPage.vue` — delete three things: (a) the `<span v-if="result && resultTokenLine" class="text-xs font-mono" :style="{ color: 'var(--color-text-muted)' }">{{ resultTokenLine }}</span>` block beneath the `provider · {{ result.elapsed_ms }} ms` line; (b) the `function formatTokenLine(r)` helper + the `const resultTokenLine = computed(...)` ref inside `<script setup>`; (c) any visible "Recent:" chip-strip render block + the `recentPrs` ref usage that feeds it. KEEP: `RECENT_PR_KEY` constant, the `readList<string>(RECENT_PR_KEY)` initial load, the `<datalist>` element + binding to the URL input, the `pushToRecentList<string>(RECENT_PR_KEY, trimmed, 10)` call inside `submit()`.
- [X] T008 [P] [US1] Modify `frontend/src/pages/HistoryDetailPage.vue:formatTokenLine`. Replace the body with the total-only shape per `data-model.md §Entity 2`: read `pt`, `ct`, `cost`; if both tokens are non-null, compute `total = pt + ct` and return `"${total} tokens"` plus `" · ~$${cost.toFixed(4)}"` segment when cost is non-null; else return `"tokens N/A"` when any field is defined-but-null, else return `null`. Render path on the template stays unchanged.

**Checkpoint**: `/review` no longer shows the token line; `/history/<id>` shows the new single-line total + cost; `/repos` per-card carries an `Embedding tokens` row with the correct aggregate.

---

## Phase 4: User Story 2 — Drop "Recent:" chip strip on /review (Priority: P2)

**Goal**: remove the duplicate "Recent:" chip strip below the PR URL input on `/review`. The `<datalist>` autocomplete + the underlying persistence stay untouched.

**Independent Test**: open `/review`, confirm no "Recent:" element + no chip strip. Type into the URL input → autocomplete still lists recent PRs. Quickstart Step 2.

- [X] T009 [US2] Verify T007 (above) removed the visible "Recent:" chip strip from `frontend/src/pages/ReviewPage.vue` AND preserved the `<datalist>` + `readList` + `pushToRecentList` plumbing. No additional code change here — this task is a verification checkpoint that closes US2. (T007 covers both US1 and US2 because the chip-strip removal lives in the same `<template>` block as the token-line removal; consolidating the edit avoids two passes on the same file.)

**Checkpoint**: `/review` template renders without the chip strip; autocomplete works on the URL input.

---

## Phase 5: User Story 3 — Defence-grade README (Priority: P2)

**Goal**: rewrite `README.md` to thesis-defence quality per spec FR-006 / FR-007 / FR-008.

**Independent Test**: a fresh reader using only `README.md` answers "what is this project / how do I run it / where is deeper docs" without opening other files. Quickstart Step 8.

- [X] T010 [US3] Rewrite `/Users/tarasivanov/Desktop/Диплом/app/README.md` with sections per `data-model.md §Entity 3`, in order: (1) Title + tagline `CodeSensei — Self-hosted AI Code Reviewer`; (2) Thesis-context paragraph in Ukrainian (author: Тарас Іванов; bachelor thesis; project goal: self-hosted alternative to CodeRabbit/Greptile with deep RAG + git-temporal analysis) + one-sentence English summary; (3) Three differentiators per ADR-011 — self-hosted air-gapped LLM via Ollama (cloud opt-in OpenAI/Anthropic), persistent AST-RAG index (tree-sitter + pgvector HNSW), git-based temporal context analysis (`git log -L` + hotspot severity bump); (4) Quick start — five numbered steps: `git clone`, populate `.env` (or rely on `MASTER_KEY` auto-gen from ADR-014), `docker compose up --build -d`, open `http://localhost:5173`, configure provider keys at `/settings` and submit a PR URL at `/review`; (5) Architecture brief — 1 paragraph + bullet stack (Python 3.12 + FastAPI + SQLAlchemy 2.x async + pgvector + arq + Redis backend; Vue 3.5 + Vite 6 + Tailwind v4 frontend; OpenAI/Anthropic/Ollama LLM; OpenAI `text-embedding-3-small` / `BAAI/bge-m3` embedding); (6) Features overview — 1-line bullets covering PR review with structured findings, bot-mode posting, repo indexing with `.codesensei-ignore`, live WebSocket index progress with polling fallback, review history with token/cost tracking; (7) Project docs map — pointers to `_decision_log.md` (ADRs 001–016), `_mvp_scope.md`, `specs/` (per-feature spec/plan/tasks/research artefacts), `.specify/memory/constitution.md`; (8) License note — "Educational use — bachelor thesis project. Not yet open-source-licensed; see thesis defence outcome." Length target ~200–300 lines including code blocks. Tone: factual, no marketing fluff.

**Checkpoint**: README renders cleanly on GitHub; fresh reader can complete Quickstart Step 9.

---

## Phase 6: Polish & Cross-Cutting

**Purpose**: verification, lint, manual smoke, marker checks.

- [X] T011 Run backend test suite via `docker compose run --rm -v "$(pwd)/backend/tests:/app/tests" -v "$(pwd)/backend/src:/app/src" -e OPENAI_API_KEY= -e ANTHROPIC_API_KEY= -e GITHUB_TOKEN= -e MASTER_KEY= -e MASTER_KEY_FILE= api sh -c "/opt/venv/bin/python -m ensurepip >/dev/null 2>&1 && /opt/venv/bin/python -m pip install -q pytest pytest-asyncio respx fakeredis && cd /app && /opt/venv/bin/python -m pytest --tb=short -q"`. Expect all green including the new `test_indexing_aggregates.py`.
- [X] T012 Run `docker compose run --rm -v "$(pwd)/backend/tests:/app/tests" -v "$(pwd)/backend/src:/app/src" api sh -c "/opt/venv/bin/python -m ensurepip >/dev/null 2>&1 && /opt/venv/bin/python -m pip install -q ruff && /opt/venv/bin/python -m ruff check src tests"`. Expect `All checks passed!`.
- [X] T013 Run `cd frontend && npx vue-tsc --noEmit && npx vite build`. Both must be clean.
- [X] T014 `docker compose up -d --build api worker frontend` to bake the aggregate query + UI changes into running images.
- [X] T015 Manual smoke per `specs/014-ux-polish-and-readme/quickstart.md` Steps 1–9. Confirm: no token line on `/review`, no "Recent:" chip strip, total-only line on `/history/<id>`, `Embedding tokens` row on `/repos` with correct comma-separated number, README renders.
- [X] T016 Verify `.specify/feature.json` points at `specs/014-ux-polish-and-readme` (was updated during /speckit-plan); verify `CLAUDE.md` SPECKIT marker also bumped (was updated during /speckit-plan). Idempotent check.

**Checkpoint**: all green → single-commit pipeline boundary + PR.

---

## Dependencies

```text
Phase 1 (T001)
  → Phase 3 (US1)
     └─ T002, T003, T005, T006, T008 parallel
     └─ T004 depends on T003
     └─ T007 depends on T005 (type field) — T007 also closes US2 (Phase 4) via the same file edit
  → Phase 4 (US2)
     └─ T009 verification only (closes after T007 lands)
  → Phase 5 (US3 — docs)
     └─ T010 standalone
  → Phase 6 (Polish — sequential)
```

US1 and US3 are independent (different file scopes). US2's only code touch is consolidated into T007 since the chip-strip and token-line removals live in the same Vue template; consolidating prevents two separate edits to `ReviewPage.vue`.

## Parallel Execution Examples

**Phase 3 implementation parallelism**:
- T002 (test), T003 (store aggregate), T005 (frontend type), T006 (RepoList), T008 (HistoryDetailPage) all parallel — distinct files.
- T004 sequential after T003 (same file `service.py` + needs the new function).
- T007 sequential after T005 (frontend type defined first).

**Phase 5 standalone**:
- T010 (README) parallel to anything in Phase 3 — touches root `README.md` only.

## Implementation Strategy

**MVP slice**: T001–T008 alone (Phase 1 + Phase 3) delivers US1's three UI changes + the backend aggregate. Phase 4 (T009) is a verification checkpoint. Phase 5 (T010) is docs and ships in the same PR for one-shot defence-grade polish.

**Single-commit pipeline boundary**: all phases commit as one feature commit (`feat(014-ux-polish-and-readme): ...`) per project commit-granularity convention. Branch already exists as `014-ux-polish-and-readme`. Push to remote + open PR with quickstart-aligned test plan at Phase 6 completion.
