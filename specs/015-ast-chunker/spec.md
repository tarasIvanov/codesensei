# Feature Specification: AST-Based Chunking for All Supported Languages

**Feature Branch**: `015-ast-chunker`
**Created**: 2026-05-22
**Status**: Draft
**Input**: User description: "Replace the heuristic chunker (Python AST + Markdown headings + sliding-window for everything else) with structural AST chunking for every supported language, keeping the sliding window only as a fallback. Closes the chunker side of the project's #2 MVP differentiator: 'AST-RAG index'."

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Structural chunks for TypeScript/JavaScript and other indexed languages (Priority: P1)

A user opens `/repos`, points CodeSensei at a TypeScript or JavaScript repository, and clicks **Index**. Today the chunker hits the sliding-window fallback for everything except Python — chunks are arbitrary 80-line slabs that cut across function boundaries, so retrieval surfaces "the lines around offset N" instead of "the function `parseUserOptions`". The user expects, and the project's pitch (ADR-011 differentiator #2) promises, that chunks correspond to **real syntactic units**: a function, a method, a class, an interface, a type alias.

**Why this priority**: structural chunking is the headline indexing claim of the thesis. Until it works for the languages that show up in real-world PR review (TypeScript, JavaScript, Go, Rust, Java, …), the AST-RAG narrative is half-true. Every retrieval-based review on a non-Python repo today is reading 80-line slabs.

**Independent Test**: index a fresh small TypeScript repo (≤ 50 files) via `/repos`; inspect the `code_chunks` table; assert that for ≥ 90 % of chunks the line range `[start_line, end_line]` lines up with a top-level function declaration, class declaration, interface declaration, type alias, or a small adjacent group of them. None of the chunks should be a generic 80-line cut that begins mid-function.

**Acceptance Scenarios**:

1. **Given** a TypeScript file containing three short top-level functions and one class with two methods, **When** the indexer processes it, **Then** the chunker emits chunks whose `start_line`/`end_line` ranges correspond to the actual function and method boundaries — not to fixed 80-line offsets.
2. **Given** a JavaScript file containing one `function_declaration` and several top-level arrow-function constants, **When** indexed, **Then** each arrow function whose source spans ≥ 1 line is treated as a splittable declaration and lands in a structurally-aligned chunk.
3. **Given** a small Python module unchanged since today, **When** re-indexed under the new chunker, **Then** the resulting chunks are at least as semantically meaningful as today (each top-level function/class is still its own boundary; nothing regresses).
4. **Given** an indexed repository whose source is a mix of supported languages, **When** the user opens the new chunk-mode breakdown in indexing logs, **Then** every routed file is tagged with a clear mode (`ast`, `sliding_no_grammar`, `sliding_parse_failed`, or `sliding_no_extension`) so the user can see how many files actually got AST treatment.

---

### User Story 2 — Reliable fallback when AST parsing fails (Priority: P2)

A user indexes a repository that contains unusual or broken files: a stray Cobol file, a JavaScript file with a syntax error so severe that tree-sitter cannot meaningfully recover, a file written in a language we never claimed to support. The user expects the index to succeed for the rest of the repository — never to fail the job because of one weird file.

**Why this priority**: indexing is a batch operation. One unparseable file must not poison the run. Without an explicit, observable fallback path, the index becomes brittle the moment a real-world repo introduces an edge case.

**Independent Test**: drop a deliberately broken TypeScript file and an unrelated `.cobol` file into a fixture repository; index it; assert the indexing run completes successfully; assert both files are nevertheless chunked (via the sliding-window fallback); assert the routing log surfaces `mode="sliding_parse_failed"` for the broken file and `mode="sliding_no_grammar"` (or `sliding_no_extension`) for the Cobol file.

**Acceptance Scenarios**:

1. **Given** a syntactically broken TypeScript file in a repository, **When** indexing runs, **Then** the file is chunked by the sliding-window fallback and the broader indexing run completes without error.
2. **Given** a file in a language that has no tree-sitter grammar registered for it, **When** indexing runs, **Then** the file is chunked by the sliding-window fallback and recorded as such in the routing log.
3. **Given** a single oversized declaration (e.g. one generated function body of many thousand lines) that cannot be split further by descending into named children, **When** chunking runs, **Then** the chunker emits the node as a single chunk and lets the upstream service-level hard cap handle it — it does not crash and does not slice mid-line.

---

### User Story 3 — Visibility into chunk routing for thesis demonstration (Priority: P3)

The user (also the thesis author) wants to demonstrate during defence that the structural-chunker claim is real: that on a given indexed repository, X % of files went through the AST path and Y % fell back to the sliding window, with the reason for each fallback recorded. Today there is no such visibility — sliding-window vs. AST is hidden inside `dispatch_chunker`.

**Why this priority**: it does not change end-user behaviour, but it makes the architectural change observable. It is small and rides along naturally with US1/US2.

**Independent Test**: index a mixed-language fixture repository; tail the structured logs; confirm one routing event per file with mode ∈ {`ast`, `sliding_no_grammar`, `sliding_parse_failed`, `sliding_no_extension`} and that a per-mode summary count is logged at the end of `chunk_repo`.

**Acceptance Scenarios**:

1. **Given** an indexing run over a mixed-language repository, **When** the run completes, **Then** a structured-log summary lists how many files were routed via each mode.
2. **Given** the user opens any indexing run's logs in the host's log viewer, **When** they search for a specific file path, **Then** they find exactly one `chunker_routing` event for that file with a clear `mode` label.

---

### Edge Cases

- A supported language file is too short to contain any splittable declarations (e.g. a single top-level `export const X = 1`): the chunker emits one chunk covering the whole file, never returns zero chunks.
- A file is entirely a doc-string / module-level constants / imports with no function or class: the chunker emits the imports/constants region as its own chunk via the "gap" handling rule.
- A file under a supported extension is empty: the chunker returns an empty chunk list (existing behaviour; no regression).
- A node has children that are themselves splittable but every child is also oversize: recursion bottoms out at the leaf and the leaf is emitted as one chunk; the service-level hard cap halves it later if needed.
- Markdown files: if the language pack has a Markdown grammar, the AST path runs; otherwise the existing heading-based splitter runs. Either way, the per-file chunk count is comparable for a typical README.
- Existing indexed repositories: their stored chunks remain bit-for-bit unchanged in the database (no migration). Until the user clicks **Re-index** on a given repo, retrieval against that repo still uses the old chunks; after **Re-index**, the new chunks take their place atomically.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The chunker MUST route every indexable file to one of four explicit modes: `ast` (structural AST chunking succeeded), `sliding_no_grammar` (the language label has no registered grammar), `sliding_parse_failed` (the grammar loaded but parsing/walking the tree raised an exception), or `sliding_no_extension` (the file's extension is not registered as indexable — the file would not have been picked up in the first place; included only for completeness in the routing taxonomy).
- **FR-002**: For every language with a registered grammar, the chunker MUST produce chunks whose `start_line` and `end_line` correspond to actual declaration boundaries (function, method, class, interface, type alias, or equivalent for the grammar) — not to fixed line-window offsets.
- **FR-003**: Where two or more adjacent declarations are individually well below the per-chunk size target, the chunker MUST greedily merge them into a single chunk while the cumulative size stays under the target, so the index does not balloon with single-function chunks for tiny utility modules.
- **FR-004**: Where a single declaration alone exceeds the per-chunk size target, the chunker MUST recursively descend into its splittable children, emitting each as its own chunk. If recursion bottoms out at a leaf that is still oversize, the chunker MUST emit the leaf as one chunk and let the upstream service-level hard cap (existing) handle further halving — the chunker MUST NOT slice mid-line.
- **FR-005**: Where two adjacent splittable declarations are separated by non-trivial source content (imports, module-level constants, module-level docstrings), the chunker MUST emit that interstitial content as its own chunk before continuing — module-level context MUST NOT be silently dropped.
- **FR-006**: For every file the chunker handles, the chunker MUST emit at least one chunk if the file's content is non-empty.
- **FR-007**: The chunker MUST keep the sliding-window strategy available as the fallback for: any file in a language without a registered grammar; any file whose parse / tree walk raises an exception; any file whose extension is registered but for which the language label cannot be mapped to a grammar.
- **FR-008**: The chunker MUST log one structured routing event per indexable file (path, language, mode) and one per-run summary at the end of each indexing job — so a defence demo can show how many files actually got AST treatment.
- **FR-009**: The set of languages eligible for AST chunking MUST extend beyond Python to at minimum: TypeScript, JavaScript, Go, Rust, Java, Markdown — and SHOULD be straightforwardly extensible to any other language with a registered grammar without requiring a code change to the dispatch logic.
- **FR-010**: The publicly-used surface of the chunking module (the dispatch function, the chunk-spec data shape, the repo-walk helper, the extension whitelist accessor) MUST remain backwards-compatible so the rest of the indexing pipeline (worker job, service, WebSocket progress stream, vector store) needs no changes.
- **FR-011**: When the user re-indexes a repository that was indexed under the old chunker, the new chunks MUST replace the old chunks atomically (existing repo-swap semantics); the user MUST be informed (via README and/or release notes) that re-indexing is required to take advantage of the new chunker.
- **FR-012**: No new outbound network call MUST be introduced. Grammars MUST be loaded from a packaged distribution baked into the backend image at build time.

### Key Entities *(include if feature involves data)*

- **Chunk routing event**: per-file structured log entry recording the file path, the resolved language label, and the chunk-mode (`ast` / `sliding_no_grammar` / `sliding_parse_failed` / `sliding_no_extension`). Not persisted to the database — log-only.
- **Per-language splittable-node-type set**: a code-internal, code-reviewable mapping from "language label" to "the set of grammar node types that count as splittable structural declarations". New language ⇒ add an entry to this map; no other change required. Code-internal in v1; not configurable via the UI.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After indexing a TypeScript repository of ≤ 500 source files via `/repos`, ≥ 90 % of stored chunks for that repository have `start_line`/`end_line` ranges that map exactly onto a syntactic declaration boundary (function, method, class, interface, type alias, or an adjacent group of them).
- **SC-002**: Mean chunk token count is ≤ 1.5 × the per-chunk target; 95th-percentile chunk token count is ≤ the upstream service-level hard cap. The upstream halver runs on ≤ 1 % of chunks in the common case (down from "every oversize file" today).
- **SC-003**: Indexing throughput (files per second, on the dev machine, on a fixture repository of 100k source LOC) is no worse than 2× slower than today's heuristic chunker. (Parsing has a real cost; a 2× regression is the absolute ceiling.)
- **SC-004**: For every supported language listed in FR-009, an indexing run over a small fixture repository produces ≥ 1 chunk routed via `mode="ast"`. For an unsupported `.cobol` file in the same run, the routing log shows `mode="sliding_no_grammar"`.
- **SC-005**: The full backend test suite stays green after the migration. Specifically, no test asserting end-to-end indexing → retrieval → review behaviour regresses; any test whose chunk-count assertion changes does so because greedy merging legitimately produced a different (lower) count, not because of a logic bug.
- **SC-006**: `docker compose up --build -d` continues to work; the backend image size grows by no more than 100 MB compared to the current baseline.
- **SC-007**: A defence-time demo can answer "how many files in this repo were AST-chunked vs sliding-window-fallback?" from the routing summary log line without grepping per-file events.

## Assumptions

- The packaged grammar distribution chosen for this feature ships prebuilt wheels for every language listed in FR-009, removing the need for a system-level compiler toolchain inside the backend image.
- `tiktoken`'s `cl100k_base` encoder is already a backend dependency (used elsewhere for token counting) and continues to be the canonical token measure for "per-chunk size target".
- The per-chunk size target is an indexing-time concern only; it does not affect the upstream LLM-context hard cap in the review service, which keeps its existing value and behaviour.
- Existing repositories' chunks remain unchanged in the database until the user explicitly re-indexes; there is no automated mass re-embedding background job in scope here.
- The four chunk-mode labels (`ast`, `sliding_no_grammar`, `sliding_parse_failed`, `sliding_no_extension`) are sufficient for the defence demo's "how much of my repo was AST-chunked?" question — finer-grained reasons (e.g. "grammar loaded but no splittable declarations found") are not in scope and would fold into `ast` with a zero-declaration outcome anyway.
- The encoding for token measurement, the structlog logger name, and the structured-event keys (`chunker_routing`, `mode`, `path`, `lang`) are part of the operational contract for the defence demo and are stable for v1.
- The feature is delivered behind no feature flag; it ships as the default chunker. Old behaviour is reachable only by explicitly invoking `chunk_sliding(...)`, which remains in the codebase.
- Constitution Principle II ("ADR-driven architecture changes") is treated as triggered by this change even though it is not a database schema change: replacing the core chunking strategy is an architectural change to a pluggable indexing component. A new Architecture Decision Record is to be drafted before any production code lands.
