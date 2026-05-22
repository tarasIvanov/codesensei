# Implementation Plan: AST-Based Chunking for All Supported Languages

**Branch**: `015-ast-chunker` | **Date**: 2026-05-22 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/015-ast-chunker/spec.md`

## Summary

Replace the heuristic dispatch in `backend/src/codesensei/indexing/chunker.py` — which today only runs a true AST splitter for Python (stdlib `ast`) and a heading splitter for Markdown, and silently sliding-windows everything else — with a unified **cAST** (Concrete AST) chunker driven by `tree-sitter` + `tree-sitter-language-pack`. The new path greedy-merges sibling structural declarations into chunks up to a ~1024-token target, recursively splits oversize declarations, and emits non-trivial interstitial content (imports, module-level constants) as its own chunks. `chunk_sliding` stays in the codebase as the only fallback. Markdown gets `tree-sitter-markdown` if available, else keeps the existing heading splitter. The public surface (`ChunkSpec`, `dispatch_chunker`, `chunk_repo`, `count_source_files`, `iter_source_files`, `SUPPORTED_EXTS`, `language_for`, `read_text_safely`) stays bit-compatible so the worker job, indexing service, WS progress stream, and vector store need no changes. The service-level `MAX_CHUNK_TOKENS=7000` halver is intentionally left in place as the upstream hard cap.

## Technical Context

**Language/Version**: Python 3.12 (backend); Vue 3.5 + TypeScript 5.7 (frontend, untouched by this feature).
**Primary Dependencies**: FastAPI 0.115, SQLAlchemy 2.x async, asyncpg, alembic, arq + Redis, tiktoken, structlog, aiofiles. **NEW**: `tree-sitter>=0.23` + `tree-sitter-language-pack>=0.2` (prebuilt wheels for ~100 grammars; no system-level toolchain required).
**Storage**: PostgreSQL 16 + pgvector. **No schema change**: chunk rows live in the existing `code_chunks` table; the column shape (`file_path`, `language`, `start_line`, `end_line`, `content`, `embedding`, `token_count`) is unchanged. Existing rows are not migrated; users re-index to pick up the new chunker (FR-011).
**Testing**: pytest 8.3 + pytest-asyncio. New file `backend/tests/unit/test_ast_chunker.py` (~9 cases). Existing `tests/unit/test_indexing_chunker.py` + `tests/unit/test_indexing_service.py` + `tests/unit/test_codesensei_ignore.py` + integration suite MUST stay green; per-language chunk-count assertions in the existing chunker test get updated only where greedy merging legitimately changes the count.
**Target Platform**: Linux server inside the existing `backend` docker image (Python 3.12-slim base). `tree-sitter-language-pack` ships manylinux wheels — no `apt install build-essential` needed.
**Project Type**: web — `backend/` only for this feature; `frontend/` untouched.
**Performance Goals**: SC-002 (mean chunk tokens ≤ 1.5× target, p95 ≤ MAX_CHUNK_TOKENS=7000). SC-003 (≤ 2× throughput regression vs. current heuristic on a 100k-LOC fixture; parser construction is cached, encoding is `cl100k_base` shared, dominant cost is tree walk).
**Constraints**: SC-006 (backend image grows ≤ 100 MB vs. current baseline). No new outbound network (FR-012). `target_tokens=1024` is a code-internal constant inside `ast_chunker.py`. No new env var. No new compose service. No alembic migration.
**Scale/Scope**: typical indexed repo is ≤ 200 source files (sync threshold per ADR-010), upper bound by `MAX_FILE_BYTES=200 KB`. Per-language node-type sets cover the FR-009 minimum: Python, TypeScript, JavaScript, Go, Rust, Java, Markdown; default set applies to other registered grammars so the dispatch dictionary is the only edit point when extending coverage.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Rationale |
|-----------|--------|-----------|
| **I — Spec-Driven Development (NON-NEGOTIABLE)** | PASS | `spec.md` + this `plan.md` + the to-be-generated `tasks.md` cover the change end-to-end before any production code. |
| **II — ADR-Driven Architectural Decisions (NON-NEGOTIABLE)** | SOFT TRIGGER | The principle text enumerates "database schema or engine, queue system, web framework, AI provider or embedding model, deployment shape, PR-comment posting" as the hard list. Chunking strategy is NOT enumerated, but the cAST switch IS a core architectural change to a Pluggable indexing component (Principle III alignment) and inflates the backend image (Principle V proximity). **Mitigation**: draft **ADR-017** ("Adopt cAST + tree-sitter-language-pack for multi-language structural chunking") as the first non-test task; the ADR records rationale, the per-language node-type set as the new pluggable extension point, image-size impact, and the no-DB-migration / re-index-required backward-compat note. Implementation MUST NOT start before ADR-017 is written and committed. |
| **III — Pluggable AI Provider Boundaries** | PASS | No LLM/embedding adapter is touched. The per-language node-type map (`_NODE_TYPES_PER_LANG`) is the new code-internal pluggable point; adding a language is a one-line edit, mirroring the Pluggable spirit. |
| **IV — Privacy & Credentials Discipline** | PASS | No new outbound network (FR-012). Grammars are baked into the image at build time via `uv sync`. No credentials touched. Chunk content shape unchanged ⇒ existing secret-scrubbing assumptions in `## Assumptions` of prior specs continue to hold. |
| **V — Single-Command Deployment** | ATTENTION | `docker compose up --build -d` MUST continue to work. The language-pack wheels are pure Python + bundled native binaries, so no Dockerfile changes are expected; an early task verifies a clean image build and measures size delta to enforce SC-006 (≤ 100 MB growth). If the growth exceeds 100 MB, ADR-017 records the actual delta and justifies it; the deploy story does NOT degrade because no new compose service is introduced. |

**Verdict**: PASS with the explicit ADR-017 prerequisite. No `Complexity Tracking` entries required — the architectural shift is in scope of a single well-bounded module (`ast_chunker.py`) with the public chunker surface preserved.

**Test-first discipline (Workflow §3)**: chunking is enumerated by the constitution as a critical path requiring failing tests before implementation. `test_ast_chunker.py` is committed (failing on the missing module) before `ast_chunker.py` itself; per-test execution order is captured in `tasks.md`.

## Project Structure

### Documentation (this feature)

```text
specs/015-ast-chunker/
├── plan.md                                          # This file
├── research.md                                       # Phase 0 — research decisions
├── data-model.md                                     # Phase 1 — entities (routing event + node-type map)
├── quickstart.md                                     # Phase 1 — manual smoke walkthrough
├── checklists/
│   └── requirements.md                               # From /speckit-specify, all PASS
├── contracts/
│   └── ast_chunker_module.md                         # Phase 1 — module contract
└── tasks.md                                          # Phase 2 — generated by /speckit-tasks
```

### Source Code (repository root)

```text
backend/
├── pyproject.toml                                    # MODIFIED — add tree-sitter + tree-sitter-language-pack deps
├── src/codesensei/indexing/
│   ├── chunker.py                                    # MODIFIED — dispatch_chunker rewires to ast_chunker; chunk_python kept as inner fallback for the py grammar path
│   ├── ast_chunker.py                                # NEW — cAST engine + per-language node-type maps + parser cache
│   ├── ignore.py                                     # UNCHANGED
│   ├── service.py                                    # UNCHANGED (MAX_CHUNK_TOKENS=7000 halver stays untouched)
│   └── store.py                                      # UNCHANGED
└── tests/
    ├── unit/
    │   ├── test_ast_chunker.py                       # NEW — ~9 cases (see spec US3)
    │   └── test_indexing_chunker.py                  # MODIFIED — update chunk-count assertions only where greedy merge legitimately changes them
    └── integration/
        └── (no new file; existing test_jobs_endpoint.py + test_review_with_temporal.py must stay green)

frontend/                                              # UNCHANGED — no UI surface
.../_decision_log.md                                  # MODIFIED — add ADR-017
```

**Structure Decision**: Web app (Option 2). Backend-only change for feature 015. The `ast_chunker.py` module is a sibling of the existing `chunker.py` within the `indexing` package so the call sites (worker, service) keep their import paths.

## Phase 0: Outline & Research

See [research.md](./research.md). Resolved questions:

1. Why `tree-sitter-language-pack` over hand-curating grammars per language?
2. What are the per-language splittable-node-type sets for the FR-009 minimum (python/typescript/javascript/go/rust/java/markdown)?
3. How is parser construction cost amortised across an indexing run?
4. How do we anchor 1-based line ranges accurately given tree-sitter's `start_point.row` is 0-based?
5. How does the cAST greedy-merge + recursive-split algorithm interact with the existing service-level `MAX_CHUNK_TOKENS=7000` halver?
6. What does `ChunkSpec.language` carry under the new path — the same full-name labels (`"python"`, `"typescript"`) the code uses today, or short labels (`"py"`, `"ts"`)?

## Phase 1: Design & Contracts

See [data-model.md](./data-model.md) for entities (chunk routing event, per-language splittable-node-type map), [contracts/ast_chunker_module.md](./contracts/ast_chunker_module.md) for the new module's exported surface and dispatch contract, and [quickstart.md](./quickstart.md) for the manual smoke walkthrough.

### Constitution Re-check (post-design)

- ADR-017 prerequisite still binds the implementation phase.
- `data-model.md` confirms NO database column change.
- `contracts/ast_chunker_module.md` confirms `dispatch_chunker` keeps the same signature.
- Image-size measurement is added as an explicit task in `tasks.md`.

**Verdict**: PASS, no new violations introduced by the design phase.

## Complexity Tracking

Not required — no Constitution violations are accepted without justification. ADR-017 covers the soft-trigger on Principle II as a record-keeping requirement, not a violation.
