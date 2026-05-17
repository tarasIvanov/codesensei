# Quickstart: Repo indexing + RAG-augmented review

These are the demo scenarios that prove the feature works. Each one is independently runnable; you don't have to do them in order, but US1 is the cheapest first check.

## Prerequisites

- `docker compose up --build -d` has rebuilt the `api` and `worker` images (they now have `git` installed) and the alembic `003_repos_chunks` migration has run.
- `MASTER_KEY` is set if you intend to use API-key credentials from the `/settings` page (feature 004); otherwise `OPENAI_API_KEY` in `.env` is enough.
- `EMBEDDING_PROVIDER=openai` and `EMBEDDING_MODEL=text-embedding-3-small` (the documented defaults).

Cost note: each scenario embeds at most a handful of files; the OpenAI bill for running this whole quickstart end-to-end is a few cents. If you want to use a fully local stack, set `EMBEDDING_PROVIDER=ollama` and `EMBEDDING_MODEL=nomic-embed-text` in `/settings` — but be aware that the V1 schema hard-codes 1536d vectors, so you'll get an `embedding_dimension_mismatch` until the column is widened (deferred to feature 006).

## Scenario 1 — Index a small repository synchronously (US1)

```bash
# Index the local mounted working tree (every demo machine has it)
curl -sS -X POST http://localhost:8000/api/index \
  -H 'content-type: application/json' \
  -d '{"source": "/app", "default_branch": null}' \
  | jq

# Expect: {"repo_id": "...", "chunk_count": <int>, "indexed_at": "...", "mode": "sync"}

curl -sS http://localhost:8000/api/repos | jq
# Expect: one entry with status "ready", chunk_count > 0, recent indexed_at
```

Validation:
- `chunk_count` is at least the number of Python files in `backend/src/codesensei/` (each contributes ≥ 1 chunk).
- The `embedding_provider` / `embedding_model` fields on the listing match the currently-configured pair.

## Scenario 2 — Run a review with retrieved context (US2)

Open `/review` in the browser at http://localhost:5173/review. With one repo already indexed (from Scenario 1), the page now shows a "Use context from repository" selector at the top.

Pick the repo you indexed. Paste a PR URL from this very project (e.g. `https://github.com/tarasIvanov/codesensei/pull/9` once it's open). Submit.

Expect:
- The findings panel renders as before.
- A new collapsible "Files that contributed context" block appears under the verdict, listing 1–5 paths.
- At least one of those paths is a file the PR diff actually touches or is semantically related to.

Negative check: clear the selector ("(none)"), re-submit the same PR. The "Files that contributed context" block does **not** appear, and the findings are byte-identical to what 004 returned for the same diff.

## Scenario 3 — Index a larger repository asynchronously (US3)

```bash
curl -sS -X POST http://localhost:8000/api/index \
  -H 'content-type: application/json' \
  -d '{"source": "https://github.com/pallets/flask.git"}' \
  | jq

# Expect: {"repo_id": "...", "job_id": "...", "mode": "async"}
```

Poll the job until it completes:

```bash
JOB=<job_id from above>
watch -n 2 curl -sS http://localhost:8000/api/jobs/$JOB
# Expect status to progress: pending → in_progress → complete (or failed)
```

Then:

```bash
curl -sS http://localhost:8000/api/repos | jq '.repos[] | select(.source | contains("flask"))'
# Expect indexed_at non-null, chunk_count > 100
```

## Scenario 4 — Manage repositories from the UI (US4)

Open `/repos` at http://localhost:5173/repos. You should see Scenarios 1 and 3's repos listed.

- Click **Re-index** on the local repo. The row's status briefly switches to `indexing`, then back to `ready` with a fresh `indexed_at`.
- Click **Delete** on the Flask repo. Confirm. The row disappears.
- Go back to `/review`. The Flask repo no longer appears in the context-repo selector.

## Scenario 5 — Embedding-provider mismatch refusal (FR-021)

Open `/settings` (feature 004's page). Change `EMBEDDING_MODEL` from `text-embedding-3-small` to something else (e.g. `text-embedding-3-large`). Save.

Now submit a review with `repo_id` set to one of the previously-indexed repos:

```bash
curl -sS -X POST http://localhost:8000/api/review \
  -H 'content-type: application/json' \
  -d '{"diff": "...", "repo_id": "<uuid from earlier>"}' | jq
```

Expect HTTP 422 with `error.category = "embedding_mismatch"` and a message that names both the persisted pair and the active pair. No LLM call is made.

Revert the model in `/settings` and the review succeeds again.

## Scenario 6 — Stuck repo recovery

If a worker crashes mid-indexing (kill it with `docker compose kill worker`), the `repos` row will be stuck in `status: "indexing"`. Recover:

```bash
docker compose up -d worker
curl -sS -X DELETE http://localhost:8000/api/repos/<stuck-repo-id>
# 409 delete_during_index? No — because the row's last_error is still NULL.
# Workaround documented in api_index.md: the operator unsets the stuck row
# manually for V1 (`psql … UPDATE repos SET last_error='aborted by operator' …`).
```

This is the documented manual-recovery path; automating it is deferred to feature 006.

## What to check in logs

After each scenario, `docker compose logs api worker --tail=200 | grep -E 'indexing|retrieval'` should show:

- `indexing.complete repo_id=… provider=… model=… files_scanned=… chunks=… embedding_seconds=… total_seconds=…`
- `retrieval.done repo_id=… queries=… chunks_fetched=… chunks_used=… trimmed=… empty=…`

No chunk content. No prompt content. If you see either, that's a bug — file it.
