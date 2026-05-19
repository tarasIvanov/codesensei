# Manual Smoke — 009 Review History & Reports

Walk-through that demonstrates every user-story (US1 / US2 / US3) end-to-end on a fresh `docker compose up` host.

## Prerequisites

- Stack running: `docker compose up --build -d`.
- API up at `http://localhost:8000`, SPA up at `http://localhost:5173`.
- A LLM provider configured in `/settings` (OpenAI default works).
- A small synthetic diff or a real public-repo PR URL handy.

## Walkthrough

### Step 1 — Run two reviews

1. Open `http://localhost:5173/review`.
2. Paste a synthetic diff (e.g. a 2-line `+`/`-` change in `x.py`); run review.
3. Wait for findings to render.
4. Paste a real PR URL on a repo you have indexed; run review again.

**Expected**: each run renders findings inline as before. The live `/review` flow is unchanged.

### Step 2 — Verify persistence in History (US1)

1. Open `http://localhost:5173/history`.

**Expected**: two rows, newest first. Each row shows: relative timestamp ("just now"), verdict pill, provider badge ("openai"), finding count, optional clickable PR URL.

### Step 3 — Open a detail view (US1)

1. Click the top row.

**Expected**: URL becomes `/history/<run_id>`. The page renders the same findings the live run did, including:
- Severity pills (`blocker`/`major`/`minor`/`nit`).
- Code-context snippets (when patch was available).
- Temporal History disclosures (for indexed-repo runs with non-empty history).
- Volatility "N changes" badges (for findings with ≥ 3 history entries).

API logs show **no** outbound LLM provider call for this open.

### Step 4 — Re-post from history (US2)

1. On the detail view of a PR-URL run, find the existing "Post to GitHub" panel.
2. Click "Post review".

**Expected**: same posting flow as on the live `/review` page. Toast confirms success; the PR comment appears on GitHub.

### Step 5 — Re-run from history (US2)

1. On any detail view, click the "Re-run" button.

**Expected**: a fresh `POST /api/review` fires; on completion, the new run appears at the top of `/history`. The original historical run stays in the list.

### Step 6 — Delete a run (US1)

1. On a detail view, click "Delete this run".
2. Confirm in the toast.

**Expected**: navigation returns to `/history`; the deleted row is gone; visiting the old detail URL (browser back) shows a friendly "Run not found" empty state.

### Step 7 — Verdict filter chips (US3)

1. On `/history` with several runs of mixed verdicts, click the "request_changes" filter chip.

**Expected**: only `request_changes` rows remain visible; URL reflects the filter (e.g. `?verdict=request_changes`). Click again to clear; full list returns. Refresh page → filter persists.

### Step 8 — Retention overflow (US3)

1. Programmatically POST 1005 reviews via a shell loop:
   ```bash
   for i in $(seq 1 1005); do
     curl -s -X POST http://localhost:8000/api/review \
       -H 'Content-Type: application/json' \
       -d '{"diff":"diff --git a/x b/x\n--- a/x\n+++ b/x\n@@ -1 +1 @@\n-old\n+new'$i'\n"}' > /dev/null
   done
   ```
2. Open `/history` → page shows top-50.
3. Hit `GET /api/reviews?limit=200` directly.

**Expected**: exactly 1000 rows in the DB; the 5 oldest are gone (their detail URLs return 404). API logs show `review_persisted` per call and the prune step ran with `pruned=N` non-zero.

## Cleanup

- `docker compose down -v` wipes the DB (including all stored history rows).
- Without `-v`, the volume persists; re-running `docker compose up` keeps the rows.
