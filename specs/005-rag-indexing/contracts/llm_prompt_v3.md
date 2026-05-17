# Contract: LLM prompt v3 (RAG-augmented)

Companion to `api_review_v2.md`. The SYSTEM message is **unchanged** from 004's v2 (Blocker tier + line-number anchor + few-shot example all stay verbatim). The USER message gains one optional section, inserted **before** the diff, whose presence is gated on whether `repo_id` was supplied.

## USER template (v3)

```text
{repository_context_block}Review this PR diff:

{diff_text}
```

where `{repository_context_block}` is either the empty string (when no `repo_id` was supplied, or when retrieval found no matches above the floor) or:

```text
Relevant context from repository (top-{n} chunks, total {tokens} tokens):

--- {file_path_1} (lines {start}-{end}) ---
{chunk_content_1}

--- {file_path_2} (lines {start}-{end}) ---
{chunk_content_2}

…

End of repository context.

```

Chunks are listed in **descending similarity score order** so the most-relevant chunk is highest in the prompt (mitigating the "lost-in-the-middle" effect for long contexts).

## Snapshot test

The unit test `test_review_prompt.py::test_v3_prompt_with_context_snapshot` pins the exact rendered string for one canonical input:

```python
chunks = [
    RetrievedChunk(file_path="billing.py", start_line=10, end_line=24,
                   content="def compute_total(items):\n    return sum(i.price for i in items)",
                   token_count=42, score=0.91),
    RetrievedChunk(file_path="billing.py", start_line=100, end_line=110,
                   content="class Invoice:\n    def __init__(self, lines):\n        self.lines = lines",
                   token_count=37, score=0.78),
]
diff = "diff --git a/billing.py b/billing.py\n@@ -10,7 +10,7 @@\n-    return sum(i.price for i in items)\n+    return sum(i.price * 1.2 for i in items)\n"

rendered = render_user_message(diff=diff, retrieved_chunks=chunks)
assert rendered == EXPECTED_SNAPSHOT  # exact-equal pin
```

Any future drift in template wording requires updating the snapshot intentionally — it is the explicit gate against silent prompt regressions.

## Token-budget enforcement

`render_user_message` does **not** itself enforce the 3 000-token budget — that is done by the retrieval layer, which produces only chunks that already fit. The renderer asserts (via `tiktoken`) that the resulting USER message stays ≤ the model's safe input window and raises `ReviewError(provider_malformed_output, retryable=False, "Prompt exceeded model window after retrieval — open a bug")` if not. This assertion is a defence-in-depth invariant, not a normal error path.

## Backward compatibility

When `retrieved_chunks` is empty or `None`, `render_user_message` produces the **exact** string that 003's renderer produces (byte-for-byte). The 003 snapshot test continues to pass unchanged.
