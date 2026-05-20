# Manual Smoke — 013 MVP closure (`.codesensei-ignore` + live progress)

End-to-end walkthrough proving every user story works on a fresh `docker compose up` host.

## Prerequisites

- Stack running: `docker compose up --build -d`.
- API up at `http://localhost:8000`, SPA up at `http://localhost:5173`.
- OpenAI key configured in `/settings` (cheapest model: `text-embedding-3-small`).
- A small (≤ 200 files) public GitHub repo to index, e.g. `https://github.com/<your-handle>/codesensei` itself.
- Alembic revision `006_repos_codesensei_ignore` has run on container startup. Verify:
  ```bash
  docker compose exec api alembic current
  # → 006_repos_codesensei_ignore (head)
  ```

## Walkthrough

### Step 1 — `.codesensei-ignore` excludes a vendored directory (US1)

1. Pick a test repo on disk. Add a file at its root:
   ```bash
   cat > .codesensei-ignore <<EOF
   vendor/
   *.generated.ts
   dist/
   EOF
   ```
2. Push the file to the remote (or use a local path-mounted source if your `/repos` form supports it).
3. On `/repos`, click "Add Repository", paste the source URL, submit.
4. Wait for indexing to complete.

**Expected**:
- The repo card shows `Ready` with a `chunk_count` lower than the same repo would produce WITHOUT the file (no `vendor/`-pathed chunks).
- The repo card carries a new badge: `🚫 3 custom ignores`.
- Backend logs include a `repo_indexed` line; no `codesensei_ignore_truncated` or `codesensei_ignore_oversize` warnings.

### Step 2 — Badge tooltip lists the patterns (US3)

1. Hover the badge on the repo card (or click it on touch devices).

**Expected**: tooltip lists exactly `vendor/`, `*.generated.ts`, `dist/` in source order. No truncation indicator (since 3 < 20).

### Step 3 — Live WebSocket progress (US2)

1. Open browser DevTools → Network tab, filter `WS` (or `wss`).
2. On `/repos`, click "Re-index" on the repo from Step 1.
3. Watch the progress card.

**Expected**:
- DevTools shows ONE active `WebSocket` connection to `/api/jobs/<job_id>/stream`.
- The progress card updates smoothly as the worker advances; `files_done` / `chunks_done` advance without a 2 s lag.
- No recurring `GET /api/jobs/<job_id>` requests in the Network tab while the WS is open (Fetch/XHR filter should be empty for this URL).
- On completion, the card transitions to `Ready` and the WS connection closes cleanly (status `1000`).

### Step 4 — Graceful polling fallback (US2)

1. While indexing is running, open `docker compose restart frontend` in a terminal (drops the nginx proxy mid-stream).
2. Watch the progress card on the SPA.

**Expected**:
- The WebSocket closes with a non-1000 code (visible in DevTools Network → Frames).
- Within ~5 s, the SPA resumes calling `GET /api/jobs/<job_id>` at the existing 2 s interval.
- The progress card keeps advancing, no error toast surfaces.
- When the index completes, the card transitions to `Ready` normally.

### Step 5 — Pre-feature row has no badge (US1, FR-014 regression)

1. Open the `/repos` page.
2. Find a repo indexed BEFORE feature 013 (any row whose `created_at` predates the migration).

**Expected**: no `custom ignores` badge on its card (the row's `codesensei_ignore_patterns` column is `NULL`).

### Step 6 — Oversize `.codesensei-ignore` is silently ignored (US1, FR-005 boundary)

1. On the test repo, replace `.codesensei-ignore` with a 5 KB file:
   ```bash
   yes "some/glob/pattern" | head -n 500 > .codesensei-ignore  # ~ 9 KB
   ```
2. Push, re-index.

**Expected**:
- Indexing completes successfully (no chunks dropped by ignore patterns).
- Backend logs include a structured warning `codesensei_ignore_oversize` with the `repo_id` and `file_bytes`.
- The repo card shows NO badge after re-indexing (patterns column is `NULL`).

### Step 7 — Truncation at 200 patterns (US1, FR-004 boundary)

1. Replace `.codesensei-ignore` with exactly 350 valid patterns:
   ```bash
   for i in {1..350}; do echo "skip-${i}/*"; done > .codesensei-ignore
   ```
2. Re-index.

**Expected**:
- Indexing completes successfully.
- Backend logs include `codesensei_ignore_truncated` with `total_lines: 350`, `kept: 200`.
- The repo card badge shows `200 custom ignores`; tooltip shows the first 20 patterns followed by `+180 more`.

### Step 8 — Settings page help section (US3, FR-015)

1. Open `/settings`.
2. Scroll to the `.codesensei-ignore` section.

**Expected**: a static text panel documents the file format (location, comments, blank lines, trailing `/`, file/glob patterns, hard caps 4 KB / 200 patterns). Operator can author a correct file from this page alone.

## What to check in logs

```bash
docker compose logs api worker | grep -E "codesensei_ignore|indexing_progress|repo_indexed" | tail -30
```

Each indexing run emits:
- One `codesensei_ignore_parsed` line with `pattern_count` (or absent when no file).
- Many `indexing_progress` lines (one per file processed).
- One `repo_indexed` line with `chunk_count` + `codesensei_ignore_pattern_count`.
- Warnings (`codesensei_ignore_truncated` / `codesensei_ignore_oversize`) only on boundary inputs.

```bash
docker compose exec redis redis-cli pubsub channels 'codesensei:*'
```

During an active index run, lists `codesensei:job:<job_id>`. Empty when no job is active.

## Cleanup

`docker compose down -v` wipes the DB (including the `repos.codesensei_ignore_patterns` column values). Without `-v`, persisted history survives.
