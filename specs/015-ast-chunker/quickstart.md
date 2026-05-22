# Quickstart Smoke Test: AST-Based Chunking

**Feature**: 015 ast-chunker
**Date**: 2026-05-22

Manual walkthrough to verify the new chunker end-to-end via the running stack.

## Preconditions

- The branch `015-ast-chunker` is checked out and the implementation has landed (ADR-017 + ast_chunker.py + chunker.py rewire + new dep in pyproject.toml + new tests passing).
- `docker compose down -v` has been run to wipe any previously-indexed repos (so the new chunker handles them from scratch).
- Backend image rebuilt: `docker compose build backend worker` succeeded.
- `.env` is populated with a valid OpenAI key (or any provider you've configured in Settings).

## 1. Stack up

```bash
docker compose up -d
docker compose ps                       # all healthy
docker compose logs backend | tail -50  # no startup errors
```

Expected: `backend` and `worker` containers `Up (healthy)`. No `ModuleNotFoundError` for `tree_sitter` or `tree_sitter_language_pack`.

## 2. Image-size sanity check (SC-006)

```bash
docker images codesensei-backend --format '{{.Size}}'
```

Expected: ≤ baseline (pre-015) + ~100 MB. Record the actual delta in the ADR-017 entry if you haven't already.

## 3. Index a TypeScript repo

In the browser at `http://localhost:5173/repos`:

1. Click **Add repo**.
2. Source: any small public TypeScript repo, e.g. `https://github.com/lodash/lodash.git`. Or use a local path that mounts a small TS project.
3. Click **Index**.

The progress bar should stream init → progress → complete via the WebSocket (feature 013 unchanged). On a small repo (≤ 100 source files), this finishes in well under a minute.

## 4. Verify AST chunks in the database

```bash
docker compose exec postgres psql -U codesensei -d codesensei -c "
  SELECT file_path, language, start_line, end_line, length(content) AS bytes
  FROM code_chunks
  WHERE language = 'typescript'
  ORDER BY file_path, start_line
  LIMIT 20;
"
```

Expected:
- `language` is `"typescript"` for every TS file (not `None`, not `"other"`).
- `start_line` / `end_line` ranges are SHORT (often 5–80 lines, depending on the declaration), not uniformly 80-line slabs.
- Adjacent chunks for the same file do NOT have identical `(end_line, start_line)` deltas (e.g. you should see ranges like `1–14`, `16–47`, `49–88`, not `1–80`, `71–150`, `141–220`).

## 5. Verify routing in the structured logs

```bash
docker compose logs worker | grep chunker_routing | tail -20
```

Expected:
- One `chunker_routing` event per indexable file.
- Most TS / JS / Python files show `mode="ast"`.
- Any unusual files (e.g. a broken `.ts` with deliberate syntax errors) show `mode="sliding_parse_failed"`.
- Files in a language without a grammar (e.g. `.toml`, `.yaml` — if they end up in `SUPPORTED_EXTS`) show `mode="sliding_no_grammar"`.

Per-run summary:

```bash
docker compose logs worker | grep chunker_run_summary | tail -5
```

Expected: one line per indexing run, like:

```
chunker_run_summary  total=143 by_mode={'ast': 142, 'sliding_no_grammar': 1}
```

## 6. Verify chunk-size distribution (SC-002)

```bash
docker compose exec postgres psql -U codesensei -d codesensei -c "
  SELECT
    language,
    count(*) AS n,
    round(avg(token_count)::numeric, 1) AS mean_tokens,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY token_count) AS p50,
    percentile_cont(0.95) WITHIN GROUP (ORDER BY token_count) AS p95,
    max(token_count) AS max_tokens
  FROM code_chunks
  GROUP BY language
  ORDER BY n DESC;
"
```

Expected:
- `mean_tokens` ≤ ~1500 (≤ 1.5 × `target_tokens=1024`).
- `p95` ≤ 7000 (the upstream `MAX_CHUNK_TOKENS` halver).
- `max_tokens` may equal or slightly exceed 1024 for rare large leaves; if it exceeds 7000 the upstream halver should have fired during indexing — if it didn't, that's a bug.

## 7. End-to-end review still works

In the browser at `http://localhost:5173/review`:

1. Paste a PR URL for an OPEN PR on the repo you just indexed.
2. Click **Run review**.
3. Wait for the response.

Expected: findings render with file/line references that resolve to actual lines in the new chunks. No 500s. No "embedding shape mismatch" errors. `/history` shows the new run with normal token + cost numbers.

## 8. Re-index an already-indexed repo

On `/repos`:

1. Find the TS repo you indexed in step 3.
2. Click **Re-index**.

Expected:
- Status flips to `INDEXING…` and the WS progress bar streams.
- On complete, `chunk_count` reflects the NEW chunker's count (typically lower than the old 80/10 slabs for the same source).
- Embedding tokens (from feature 014) reflect the new token totals.

## 9. Fallback path sanity (US2)

Stage a deliberately broken `.ts` file inside a fixture repo:

```bash
mkdir -p /tmp/badts && cd /tmp/badts
git init -q
cat > a.ts <<'EOF'
function ok() { return 1 }
EOF
cat > b.ts <<'EOF'
function broken(
    THIS IS NOT TYPESCRIPT &&& %%%
EOF
git add . && git commit -qm "fixture"
```

Index `/tmp/badts` via `/repos`. Expected:
- Indexing completes successfully (no job failure).
- Logs show `chunker_routing path="a.ts" mode="ast"` and `chunker_routing path="b.ts" mode="ast"` OR `mode="sliding_parse_failed"` — tree-sitter is quite forgiving so even malformed TS often parses with `has_error=True` but still yields named nodes.
- If the broken file produced no splittable nodes, the log shows `mode="sliding_parse_failed"` and the row in `code_chunks` for `b.ts` has `language="typescript"` and slab-shaped line ranges (the sliding fallback).

## 10. Tear down

```bash
docker compose down -v
```

This wipes the test indexes — leaving no residue from the smoke run.

## Acceptance Summary

| Spec criterion | Verified in step |
|---------------|------------------|
| SC-001 (≥ 90 % AST coverage on a TS repo) | 4 + 5 |
| SC-002 (mean ≤ 1.5× target, p95 ≤ hard cap) | 6 |
| SC-003 (≤ 2× throughput regression) | 3 (indexing speed) |
| SC-004 (per-lang AST + sliding modes observable) | 5 |
| SC-005 (full test suite green) | (run `uv run pytest` separately) |
| SC-006 (image growth ≤ 100 MB) | 2 |
| SC-007 (summary log answers "AST vs fallback?") | 5 |
