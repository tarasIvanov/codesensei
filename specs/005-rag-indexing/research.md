# Research: Repo indexing + RAG-augmented review

Companion to `plan.md`. Decisions are numbered (R1…); each has a one-line rationale and a record of what was rejected.

## R1 — Retrieval algorithm

**Decision**: For each hunk in the incoming diff, take the new-file content from `hunk_start - 10` to `hunk_end + 10` lines as the "query window", embed each window through the configured `EmbeddingProvider`, run `ORDER BY embedding <=> $query` over `code_chunks WHERE repo_id = ?` with `LIMIT 5`, union the resulting chunk-id sets across all queries (so a chunk hit by two hunks counts once), then trim by descending score until the cumulative `token_count` of selected chunks fits within the 3 000-token retrieval budget. Drops are logged (FR-018).

**Rationale**: Per-hunk queries are cheap (≤ 10 queries on a typical PR) and preserve locality — a chunk that's semantically near hunk A but distant from hunk B should still surface. Cosine (`<=>` with `vector_cosine_ops`) is the operator OpenAI's `text-embedding-3-small` is normalised for; L2 would give a slightly different (and slightly worse for normalised vectors) ranking.

**Alternatives rejected**:
- *One whole-diff query.* Cheaper but blurs locality — long diffs that touch unrelated areas of the codebase get one averaged vector that retrieves nothing useful.
- *File-level queries (one per changed file).* Slightly cheaper than per-hunk but loses precision when one file has multiple separate changes (e.g. a refactor that touches three independent functions).
- *MMR re-ranking on the top-K.* Helpful at K=20+ to diversify; at K=5 the diversity-vs-relevance tradeoff isn't worth the extra code path for V1.

**Recorded as**: ADR-009 (append to `../_decision_log.md` before any retrieval code).

## R2 — Chunking strategy

**Decision**: Three chunkers, dispatched on file extension.
- **Python (`.py`)**: parse with stdlib `ast`, emit one chunk per `FunctionDef` / `AsyncFunctionDef` / `ClassDef` at module top level; module-level statements outside any def get bundled into one "module-preamble" chunk. Each chunk carries its real `start_line`/`end_line` from `ast.lineno`/`ast.end_lineno`.
- **Markdown (`.md`)**: split on `^##\s` and `^# \s` boundaries; each section is one chunk, max 200 lines (oversize sections fall through to the sliding window).
- **Everything else** (`.ts`, `.tsx`, `.js`, `.jsx`, `.java`, `.go`, `.rs`, `.cpp`, `.c`, `.kt`, `.rb`, `.php`, `.sh`, `.yaml`, `.toml`, `.sql`): fixed 80-line sliding window with 10-line overlap.

Binary files (detected via NUL byte in first 8 KB) are skipped silently. Files larger than 200 KB are skipped silently — they tend to be vendored bundles or generated artifacts that pollute retrieval.

**Rationale**: `ast` is in stdlib and covers Python perfectly; for JS/TS we considered `tree-sitter-languages` (R2-alt) and rejected the build/binary footprint for thesis scope. The fixed-window fallback is "good enough" per the RAG literature for code retrieval at K=5 — token-similarity dominates at small K. Markdown gets its own splitter because heading-anchored chunks are dramatically more useful than line windows for prose.

**Alternatives rejected**:
- *`tree-sitter-languages` (compiled grammars).* Best chunk quality across languages but adds ~50 MB of binaries to the image and a compile-step on Alpine. Defer until a follow-up feature that has measurable retrieval-quality complaints.
- *Single sliding window for all files including Python.* Loses precise function boundaries; reviewers reading findings can't easily click through to "the function this referred to".

## R3 — Async file I/O during chunking

**Decision**: Use `aiofiles` for reading repository files. The chunker is an `async def` that iterates over a list of paths and `await`s each read.

**Rationale**: Chunking walks thousands of files per repo (the 200-file sync cap implies up to ~10× that in total file count after filters). Using `asyncio.to_thread` per file would spin up a thread for each — wasteful. `aiofiles` keeps the chunker on the main event loop and lets the embedding-API calls (which dominate wall-clock time) interleave with file reads.

**Alternatives rejected**:
- *Sync reads inside `asyncio.to_thread`.* Simpler to read but blocks one thread per file; for a 2 000-file repo the cost adds 30+ seconds.
- *Streaming reads via `anyio.Path`.* AnyIO not currently a stack dep; pulling it in for one use case isn't justified.

## R4 — Sync vs async threshold

**Decision**: Synchronous indexing iff the repository has **≤ 200 source files** after binary/extension filtering. Above that threshold, the API responds 202, persists a `repos` row with `indexed_at=NULL` and `chunk_count=0`, and enqueues `index_repo_job` against the arq queue from feature 004.

**Rationale**: A pre-scan that counts only source files (extension whitelist + filesize cap + binary heuristic) is fast (≤ 1 s for a 5 000-file checkout) and gives a deterministic, auditable threshold. Embedding ~200 files (worst-case ~600 chunks at 3 chunks/file) on OpenAI `text-embedding-3-small` at the documented 100-batch size = 6 API calls × ~0.5 s = ~3 s of network plus chunking; total well within the spec's "indexing under a minute" expectation. Above 200 files the HTTP timeout window of a typical reverse-proxy (60 s) becomes uncomfortable, hence the queue handoff.

**Alternatives rejected**:
- *Threshold by estimated chunk count.* More accurate but requires the chunker to run before the dispatcher can decide — defeats the point of the gate.
- *Always async.* Simpler dispatcher logic but a small-repo demo (the thesis demo's hot path) has to round-trip through arq + polling for no good reason. The sync path also makes the test suite simpler.

**Recorded as**: ADR-010 (append to `../_decision_log.md` before any indexing API code).

## R5 — pgvector operator class

**Decision**: HNSW index with `vector_cosine_ops` (`<=>` operator).

**Rationale**: OpenAI `text-embedding-3-small` returns L2-normalised vectors; cosine and L2 give identical rankings on normalised data, but cosine's [0, 2] distance range is easier to reason about for thresholds. ADR-004 names HNSW but is operator-agnostic, so this plan picks the operator that matches the default embedding provider without violating the ADR.

**Alternatives rejected**:
- *`vector_l2_ops` (`<->`).* Equivalent for the default provider; if a future provider returns non-normalised vectors the difference becomes meaningful and we'd have to migrate. Cosine is the robust default.
- *`vector_ip_ops` (`<#>`).* Inner-product is for unnormalised vectors and is the wrong default for OpenAI's embedding API; would need explicit normalisation at query time.

## R6 — Retrieval budget

**Decision**: 3 000 tokens of retrieved context, counted with `tiktoken`'s `cl100k_base` encoding (the OpenAI default; close enough for Anthropic/Ollama for budget purposes — over-counting is safer than under-counting). When `sum(token_count for selected chunks) > 3000`, drop chunks in descending score order (i.e. drop the **lowest-scored** ones first) until the sum fits.

**Rationale**: A typical `gpt-4o-mini` review prompt already runs ~2 000 tokens (SYSTEM + diff + few-shot example). 3 000 tokens of retrieved context leaves comfortable headroom under the 16K input window of the cheapest providers and below the per-request rate limits where token cost matters.

**Alternatives rejected**:
- *Token budget per provider.* More accurate but every settings change would need a recalculation; complexity not warranted.
- *Character budget (~12 000 chars).* Easier but a code-heavy chunk and a comment-heavy chunk are wildly different in token count.

## R7 — Top-K per query

**Decision**: K=5 per derived query, then deduplicate across queries before the token-budget trim.

**Rationale**: A larger K wastes embedding-API capacity on chunks the budget trim would discard anyway; a smaller K risks missing one of two semantically equally-good candidates. K=5 is the value the RAG literature (e.g. `lost-in-the-middle` follow-ups) treats as a useful default for code retrieval at modest budget.

**Alternatives rejected**:
- *K=10 + MMR rerank.* Better recall but extra code path; defer to feature 006 if SC-004 evaluation flags problems.
- *K=3.* Marginal cost savings but a known weak spot when two adjacent functions are both relevant.

## R8 — Index build & ANALYZE timing

**Decision**: Build the HNSW index during the alembic migration on an empty table (`CREATE INDEX … USING hnsw …`). Do **not** run an explicit `ANALYZE` after each indexing pass — let autovacuum handle stats refresh. For the V1 dataset (≤ 25 000 chunks total), cold planner stats are accurate enough.

**Rationale**: HNSW on an empty table builds in milliseconds and grows incrementally with each insert; the upfront cost is zero. An explicit `ANALYZE` after every reindex would add latency to the sync path for no measurable retrieval-quality gain at this scale.

**Alternatives rejected**:
- *IVFFlat with `lists=100`.* Faster build, faster query at small dataset sizes, but the recall floor at K=5 is meaningfully worse than HNSW on normalised vectors. ADR-004 already calls HNSW; respecting that ADR is the cheap choice.
- *Explicit `ANALYZE code_chunks` after each pass.* Cheap on the small dataset, but adds non-obvious moving parts. Revisit if the planner starts choosing sequential scans (it won't at our scale).

## R9 — Embedding-provider/model identity persistence

**Decision**: At indexing time, capture `EmbeddingProvider.provider_name()` and `EmbeddingProvider.model_name()` (both already on the 002 protocol) and persist them onto the `repos` row. Before any retrieval call, compare the persisted pair against the currently-active provider/model. Mismatch → HTTP 422 with `ReviewErrorCategory.INVALID_INPUT` and a message of the form `"This repository was indexed with {old}/{old_model}; the active embedding provider is {new}/{new_model}. Re-index the repository before retrieval."`.

**Rationale**: Two embedding models live in different vector spaces; cross-space nearest-neighbour lookups return nonsense. Detecting and refusing is mandatory (FR-021); silent failure is the failure mode RAG users complain about most.

**Alternatives rejected**:
- *Per-chunk provider/model stamp.* Wastes 50+ bytes per chunk; the repo-level stamp is sufficient since we always re-index atomically (FR-013).
- *Auto-reindex on mismatch.* Surprising behaviour; would re-spend the user's embedding budget without their consent. The error message tells them what to do.

## R10 — Indexing observability

**Decision**: One `structlog` `info` line per indexing pass at completion: `indexing.complete repo_id=… provider=… model=… files_scanned=… chunks=… embedding_seconds=… total_seconds=…`. One per retrieval pass: `retrieval.done repo_id=… queries=… chunks_fetched=… chunks_used=… trimmed=… empty=…`. **No chunk content** is ever logged.

**Rationale**: These two lines are the entire evidentiary surface the thesis evaluation needs for cost/quality discussion. Anything beyond them is noise; anything less risks an unverifiable claim.

**Alternatives rejected**:
- *Per-chunk log lines.* Would dwarf request logs and leak content.
- *No structured logging, rely on metrics.* Metrics don't carry the per-repo identification needed for the thesis tables.

---

## Resolved unknowns checklist

- ✅ Retrieval algorithm (R1)
- ✅ Chunking strategy (R2)
- ✅ Async I/O choice (R3)
- ✅ Sync/async threshold (R4)
- ✅ pgvector operator (R5)
- ✅ Retrieval budget (R6)
- ✅ Top-K (R7)
- ✅ Index/ANALYZE timing (R8)
- ✅ Provider-identity persistence (R9)
- ✅ Observability surface (R10)

No `NEEDS CLARIFICATION` markers remain. Plan is unblocked for Phase 1.
