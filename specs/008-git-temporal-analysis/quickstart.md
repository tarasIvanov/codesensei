# Manual Smoke — 008 Git Temporal Analysis

Run-through that demonstrates every spec story (US1 / US2 / US3) end-to-end on a fresh `docker compose up` host. Each step has an explicit expected observation.

## Prerequisites

- Stack running: `docker compose up --build -d` (no `--profile ollama` required).
- API up at `http://localhost:8000`, SPA up at `http://localhost:5173`.
- A LLM provider configured in `/settings` (`openai` default, or `anthropic` / `ollama`); a valid API key for that provider.
- A public HTTPS GitHub URL of a small repository whose default branch is known. **Recommendation**: `https://github.com/octokit/octokit.js` (small, fast clones, plenty of history).
- A public PR URL on that same repository that touches at least one file with several recent commits. Any PR on a moderately-active repo will do.

## Walkthrough

### Step 1 — Index the repo

1. Open `http://localhost:5173/repos`.
2. Paste the repo HTTPS URL into the "Source" field, click "Index".
3. Wait for the row's status to show `ready` (a few seconds for a small repo, ≤ 1 min for medium).

**Expected**: row appears in the list, indexed_at timestamp populated.

### Step 2 — First review against the indexed repo

1. Open `http://localhost:5173/review`.
2. Paste the PR URL into the "PR URL" field.
3. From the "Repository (RAG context)" dropdown, pick the repo you indexed in Step 1.
4. Click "Run review".

**Expected**: skeleton placeholder during the in-flight (≤ ~30 s for OpenAI default); findings list renders with at least one finding (any severity).

### Step 3 — Per-finding History disclosure (US1)

1. Pick any finding that has a `line` number (not a file-level remark).
2. Locate the small disclosure below the suggestion / code-context that reads "History (N changes)" — it appears only when temporal context matched.
3. Click to expand.

**Expected**: a 4-column table shows up to 5 rows: short SHA / date (YYYY-MM-DD) / author local-part / subject (≤ 80 chars). If the file you opened has no history matching the diff range, the disclosure is not rendered at all — try another finding.

### Step 4 — Volatility badge (US3)

1. Scan the findings list for any finding whose History row count is ≥ 3.
2. Inspect its severity-pill row.

**Expected**: a small "N changes" badge sits inline next to the severity pill on that finding's header. Findings with ≤ 2 history rows have no badge.

### Step 5 — LLM was conditioned on the history (US2)

1. In the same SPA tab, open the browser DevTools network panel.
2. Find the most recent `POST /api/review/run` request and its corresponding API container log line: `docker compose logs -f api | grep temporal_fetch`.

**Expected** in the API logs: exactly one `temporal_fetch` info entry with non-zero `files_count` and `entries_total`. The LLM prompt itself isn't visible to the user (security/privacy), but the log entry confirms collection occurred.

### Step 6 — Cache amortisation (SC-005)

1. Re-run the review from Step 2 (same PR URL, same indexed repo).
2. Watch the time-to-findings.

**Expected**: second review's perceived "temporal phase" (the gap between request submit and findings-rendered) is at least slightly faster than the first; `docker compose exec api ls /var/tmp/codesensei-temporal/` shows the cache directory survives between runs.

### Step 7 — Diff-only path is unaffected (FR-010)

1. Open `/review`.
2. Paste a different PR URL but **leave the "Repository (RAG context)" dropdown empty**.
3. Click "Run review".

**Expected**: findings render as before; **no** History disclosures appear on any finding; **no** "N changes" badges appear; API logs show **no** `temporal_fetch` entry for that request.

### Step 8 — Failure absorption (FR-019)

1. `docker compose exec api rm -rf /var/tmp/codesensei-temporal/`.
2. Disable outbound network from the api container (or stop the host's network briefly).
3. Re-run Step 2 (review with `repo_id`).

**Expected**: review completes with well-formed findings; History disclosures / badges are absent on all findings; one or more `temporal_fetch_failed` warning log lines appear; the user sees no error banner or toast — the page renders identically to the diff-only case.

Re-enable the network when done.

## Cleanup

- The runtime cache lives only inside the api container; recreating the stack (`docker compose down && docker compose up -d`) wipes it. The indexed-repo row in the DB persists.
