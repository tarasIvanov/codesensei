# Contract: Retrieval algorithm

Pure-function specification — given the inputs below, the output is deterministic up to floating-point rounding of distances returned by pgvector.

## Inputs

- `diff: str` — unified diff text. Required.
- `repo_id: UUID` — already validated to exist and to match the active embedding provider/model.
- `embedding_provider: EmbeddingProvider` — the active provider (the one that produced this repo's chunks).
- `top_k: int = 5` — per-query top-K.
- `token_budget: int = 3000` — total `tiktoken`-counted budget for retrieved chunks.

## Steps

### 1. Parse hunks

Use a regex over the diff to extract every hunk header line `@@ -A,B +C,D @@`. For each hunk:
- Compute `query_start = max(1, C - 10)`.
- Compute `query_end = C + D + 10` (so the window extends 10 lines past the hunk end on the new side).
- Gather the new-file lines (lines that don't start with `-` in the hunk body) in that window. If the hunk body extends across multiple hunks of the same file, treat each as a separate query.
- Skip hunks whose new-file body is empty (pure deletions add no signal for context retrieval).

The output is a `list[str]` — one query window per non-deletion hunk.

### 2. Embed queries

`vectors = await embedding_provider.embed(query_windows)` — one provider call, batched inside the provider implementation.

### 3. Search

For each query vector `v_i`:

```sql
SELECT id, repo_id, file_path, language, start_line, end_line, content, token_count,
       (embedding <=> $1::vector) AS distance
  FROM code_chunks
 WHERE repo_id = $2
 ORDER BY embedding <=> $1::vector
 LIMIT $3;
```

with parameters `($v_i, $repo_id, $top_k)`. `distance` is in `[0, 2]`; lower is better.

### 4. Deduplicate

Union the candidate sets across all queries. If the same `chunk_id` appears with multiple distances, keep the **smallest** distance (best match). Convert to a flat list sorted ascending by distance.

### 5. Trim by token budget

Walk the sorted list, accumulating `token_count`. Stop as soon as adding the next chunk would push the accumulator above `token_budget`. Everything kept is `selected`; everything skipped is `dropped` (counted, not bodied, into the log).

### 6. Score floor (FR-018 corner case)

After dedup, drop any chunk whose distance > 1.5 (cosine "very dissimilar" threshold). If `selected` becomes empty as a result, the retrieval returns an empty set — the review proceeds without a `repository_context_block` and `context_files` in the response is `[]`.

## Output

```python
@dataclass(frozen=True)
class RetrievalResult:
    selected: list[RetrievedChunk]      # in ascending-distance order
    queries_count: int
    chunks_fetched: int                 # before trim
    chunks_used: int                    # after trim
    trimmed: int                        # = chunks_fetched - chunks_used
    empty: bool                         # True if selected == []
```

`RetrievedChunk` = `(chunk_id, file_path, start_line, end_line, content, token_count, score)` where `score = 1 - distance / 2` (i.e. normalised similarity in [0, 1] for human readability in logs; not used algorithmically downstream).

## Determinism

Given identical inputs and the same pgvector index state, the output is bit-identical except for the `distance` floats. Test fixtures pin `tiktoken`'s token counts so the trim step is exact.

## Error paths

- pgvector unavailable → bubbles up as `ProviderError(provider="postgres", retryable=True)` from the SQLAlchemy layer; review service wraps it as `ReviewError(provider_unavailable)`.
- `embedding_provider.embed(...)` raises → `ReviewError(provider_unavailable, retryable=True, "Embedding provider failed during retrieval.")`. The review **must** fail, not silently fall back to diff-only, because that would mask a configuration problem.
- Empty `query_windows` (a diff of pure deletions, or a malformed diff with no `@@`) → return `RetrievalResult(selected=[], queries_count=0, …, empty=True)`. Review proceeds without context.
