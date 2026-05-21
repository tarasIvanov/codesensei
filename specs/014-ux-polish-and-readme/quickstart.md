# Manual Smoke — 014 UX polish + README

End-to-end walkthrough proving every user story works on a fresh `docker compose up` host.

## Prerequisites

- Stack running: `docker compose up --build -d`.
- API up at `http://localhost:8000`, SPA up at `http://localhost:5173`.
- OpenAI key configured in `/settings` (for the historical-run check).
- At least one indexed repository (from any prior feature) — needed for Step 5.
- At least one historical review run (from any prior feature 012+ flow) — needed for Step 3.

## Walkthrough

### Step 1 — No token/cost line on `/review` (US1)

1. Open `http://localhost:5173/review`.
2. Paste any public PR URL → Submit.
3. Wait for findings to render.

**Expected**: under the existing `provider openai · X ms` line, NO `tokens` or `~$` line is shown. The PostToGitHubPanel + FindingsList render as before. Network inspector: the `POST /api/review` response JSON still carries `prompt_tokens`, `completion_tokens`, `cost_usd` — they are just not rendered.

### Step 2 — No "Recent:" chip strip on `/review` (US2)

1. Stay on `/review` (or reload).

**Expected**:
- No element on the page reads "Recent:" and no horizontal chip strip is rendered under the PR URL input.
- Click into the PR URL `<input>` field → browser-native autocomplete dropdown lists previously-submitted PR URLs (parity check).
- Submit one more PR URL → reload → autocomplete now includes that one.

### Step 3 — `/history/<id>` shows single-line total + cost (US1)

1. Open `/history` and click any run with non-null tokens (post-feature 012).

**Expected**: header card carries one muted-mono line `1801 tokens · ~$0.0023` (where `1801 == prompt_tokens + completion_tokens`). No `in / out` split.

### Step 4 — `/history/<id>` legacy + Ollama edge cases (US1, edge)

1. Open a historical run that pre-dates feature 012 (all three token/cost fields are `null`).

**Expected**: line reads `tokens N/A`.

2. (If Ollama profile available.) Open a recent run made against Ollama.

**Expected**: line reads `N tokens` (no cost segment).

### Step 5 — `/repos` shows Embedding tokens row (US1)

1. Open `/repos`.
2. Expand any repo card.

**Expected**: inside the per-repo `<dl>`, between `Chunks` and `Indexed at`, a new row `Embedding tokens: 1,234,567 tokens` (or whatever the sum is, comma-separated thousands). For a repo with zero chunks, shows `0 tokens`.

### Step 6 — Aggregate stays correct after re-index (US1, FR-009)

1. Click `Re-index` on any repo. Wait for completion.
2. Re-open `/repos`.

**Expected**: `Embedding tokens` value reflects the NEW chunk set's sum (likely close to but not necessarily equal to the pre-re-index value, depending on what changed in the source tree).

### Step 7 — DB sanity (optional, US1)

```bash
docker compose exec postgres psql -U codesensei -d codesensei -c \
  "SELECT repo_id, SUM(token_count) AS total FROM code_chunks GROUP BY repo_id ORDER BY total DESC LIMIT 5;"
```

**Expected**: the totals match the values rendered on `/repos`.

### Step 8 — README renders cleanly (US3)

1. Open `README.md` on GitHub (or locally in a Markdown viewer).

**Expected**:
- First 30 lines surface: tagline, thesis context (Ukrainian paragraph), three named differentiators.
- "Quick start" section has ≤ 5 numbered steps.
- "Architecture" section briefs the stack in one paragraph + bullets.
- Pointers to `_decision_log.md`, `_mvp_scope.md`, `specs/`.
- License note is one or two lines.
- No `[NEEDS …]` placeholders, no Lorem Ipsum.

### Step 9 — Quick-start round-trip (US3, SC-004)

1. On a clean Docker host (or after `docker compose down -v`), run the 5 README quick-start steps verbatim.
2. Time the wall-clock from `git clone` to "SPA renders".

**Expected**: under 10 minutes including the first Docker image pulls.

## What to check in logs

```bash
docker compose logs api | grep -i 'token\|aggregate'
```

No new structured warnings should appear from the aggregate path — it is a normal SQL query.

## Cleanup

`docker compose down -v` wipes the DB (chunks → aggregate goes back to zero on next index). Without `-v`, persisted history + indexes survive.
