# Manual Smoke — 012 Token usage + cost estimate

End-to-end walkthrough proving every user story works on a fresh `docker compose up` host.

## Prerequisites

- Stack running: `docker compose up --build -d`.
- API up at `http://localhost:8000`, SPA up at `http://localhost:5173`.
- An OpenAI key configured in `/settings` (the cheapest path: `gpt-4o-mini`).
- (Optional) An Anthropic key + Ollama profile (`docker compose --profile ollama up`) for the multi-provider checks.
- Alembic revision `005_review_run_tokens` has run on container startup. Verify with:
  ```bash
  docker compose exec api alembic current
  # → 005_review_run_tokens (head)
  ```

## Walkthrough

### Step 1 — OpenAI review surfaces tokens + cost (US1)

1. Open `http://localhost:5173/review`.
2. Paste a small PR URL (any public PR). Submit.
3. Wait for findings to render.

**Expected**: under the existing `provider openai · X ms` line, a second muted-mono line appears:
```
1234 in / 567 out tokens · ~$0.0023
```
The token counts MUST match what `https://platform.openai.com/usage` would record for the same call (exact, not estimate). The cost figure equals `(prompt_tokens / 1_000_000) * 0.15 + (completion_tokens / 1_000_000) * 0.60` (the `gpt-4o-mini` rate).

### Step 2 — Anthropic review surfaces same shape (US1, multi-provider)

1. Switch `LLM provider` to `anthropic` in `/settings`. Save.
2. Re-run a review on `/review`.

**Expected**: same line, with token counts from Anthropic's `input_tokens` / `output_tokens` fields and cost from the `claude-3-5-sonnet-latest` rate ($3 / $15 per 1M).

### Step 3 — Ollama review surfaces tokens N/A (US1, edge case)

1. Switch `LLM provider` to `ollama` in `/settings`. Set `LLM model` to a model you've pulled (e.g. `llama3.1:8b`).
2. Re-run a review.

**Expected**: the new line reads `tokens N/A` (no token counts, no cost). The review itself completes normally with findings.

### Step 4 — Historical run replays the same line (US2)

1. Open `/history`.
2. Click any row from Step 1 / Step 2 (the OpenAI / Anthropic runs).

**Expected**: the detail page's header card carries the same token-and-cost line as the live `/review` view did. No new LLM call is made (verify with `docker compose logs api --tail 20` — only a `GET /api/reviews/<id>` 200 line, no provider chatter).

### Step 5 — Pre-feature rows degrade gracefully (US2, FR-010)

1. Locate a historical run created BEFORE feature 012 (any row from `/history` whose `created_at` predates the migration).
2. Open it.

**Expected**: detail page shows `tokens N/A` for the new line. Verdict, findings, post-to-GitHub panel all work normally — only the token line is null.

### Step 6 — Unknown pricing pair → tokens visible, cost hidden (US3 prep)

1. In `/settings`, set `LLM model` to a model that is NOT in `PRICING_PER_1M` (e.g. `gpt-4o-2024-08-06` — the dated suffix). Save.
2. Re-run a review.

**Expected**: the line reads `1234 in / 567 out tokens` (no cost segment). Backend logs show the call completed normally.

### Step 7 — Pricing-table update flow (US3)

1. `docker compose exec api cat /app/src/codesensei/review/pricing.py | grep "gpt-4o-mini"` — note the current price.
2. Edit `backend/src/codesensei/review/pricing.py` locally — bump the input price for `("openai", "gpt-4o-mini")` from `0.15` to `0.30`.
3. `docker compose up -d --build api worker` — rebuild + recreate.
4. Re-run a review.

**Expected**: the cost figure is now double what Step 1 reported for the same token counts.

### Step 8 — Database persistence sanity check

```bash
docker compose exec db psql -U codesensei -d codesensei \
  -c "SELECT id, created_at, prompt_tokens, completion_tokens, cost_usd FROM review_runs ORDER BY created_at DESC LIMIT 5;"
```

**Expected**: the most recent rows show non-null tokens + cost for OpenAI/Anthropic runs, null for Ollama runs, null for pre-feature rows. `cost_usd` values are rounded to 6 dp (e.g. `0.002340`).

## What to check in logs

```bash
docker compose logs api | grep review_persisted | tail -5
```

Each line includes `prompt_tokens`, `completion_tokens`, `cost_usd` in its structured-log fields. Failed reviews (`review_persist_failed`) do not include these fields.

```bash
docker compose logs api | grep -i 'usage\|cost'
```

Should be empty — usage is part of the SDK response, not a separate log line; cost is computed at insert time without emitting its own log entry.

## Cleanup

`docker compose down -v` wipes the DB. Without `-v`, persisted history (including token/cost) survives a restart.
