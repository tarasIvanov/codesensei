# Quickstart — 003-pr-review-mvp

Three end-to-end smoke scenarios that exercise the feature against a running stack. Each one maps 1:1 to a user story in `spec.md` so a thesis defender can demo them in order.

**Prerequisites**:
- Feature 001 stack is up: `docker compose up -d`. `/healthz` reports `status: "ok"`.
- Feature 002 is configured: at least one chat provider is `ok` in the `providers.llm` badge (either set `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` or run a local Ollama with the chat model pulled).
- Recreate the `api` container after editing `.env` to pick up new values: `docker compose up -d --force-recreate api` (a plain `restart` does **not** reload env per the note in `002/quickstart.md`).

---

## Scenario A — Paste a unified diff (User Story 1)

**Setup**: nothing extra; just need an LLM provider configured.

**Steps**:
1. Open `http://localhost/` in a browser. The HUD shows the existing health badges.
2. Click the "Review" nav link or navigate to `http://localhost/review`.
3. In the **Diff** textarea, paste:

   ```diff
   diff --git a/src/auth.py b/src/auth.py
   index 1111111..2222222 100644
   --- a/src/auth.py
   +++ b/src/auth.py
   @@ -1,3 +1,5 @@
    def get_user(req):
   -    return req.user
   +    user = req.user
   +    email = user.email
   +    return email
   ```
4. Click **Review**.

**Expected**:
- Submit button disables and a "Reviewing…" indicator appears.
- Within ~30 s on a remote provider (cloud) or longer on Ollama, the findings list renders.
- At least one finding refers to `src/auth.py` around line 4–5 with severity `major` (likely null-deref / no None check on `req.user`).
- Verdict is `request_changes` or `comment`.
- Console-network: a single `POST /api/review` request, response shape per `contracts/api_review.md`.

---

## Scenario B — Review a public GitHub PR by URL (User Story 2)

**Setup**:
- Either set `GITHUB_TOKEN=<your-PAT>` in `.env` for higher rate limits / private repos, **or** leave it empty for public-only access. Recreate `api`: `docker compose up -d --force-recreate api`.

**Steps**:
1. On `/review`, switch to the **PR URL** input mode.
2. Paste a small public PR URL — e.g. `https://github.com/tarasIvanov/app/pull/5` (the 001 PR; it's small enough to fit comfortably).
3. Click **Review**.

**Expected**:
- The backend fetches the diff from `https://api.github.com/repos/tarasIvanov/app/pulls/5` with header `Accept: application/vnd.github.v3.diff`.
- The findings list references files actually touched by that PR (e.g. `docker-compose.yml`, `backend/...`).
- A second submission with the same URL produces an independent LLM call (no caching).

**Sanity check** — without a token, fetching a **private** PR URL returns:

```json
{"error": {"category": "github_fetch_failed", "message": "GitHub auth failed for this PR — check the configured token.", "retryable": false}}
```

with HTTP 502. The UI shows the human message.

---

## Scenario C — Oversized diff is rejected fast (User Story 3, AS-1)

**Setup**: leave defaults (`REVIEW_MAX_DIFF_BYTES=256000`).

**Steps**:
1. Generate a synthetic oversized diff and POST it directly with curl to bypass the SPA:

   ```bash
   python3 -c "
   header = 'diff --git a/big.txt b/big.txt\n--- a/big.txt\n+++ b/big.txt\n@@ -1 +1 @@\n'
   payload = header + '+' + ('x' * 300_000) + '\n'
   import json; print(json.dumps({'diff': payload}))
   " | curl -sS -X POST http://localhost/api/review \
        -H 'Content-Type: application/json' \
        --data @- -o /tmp/r.json -w '%{http_code}\n'
   cat /tmp/r.json
   ```

**Expected**:
- HTTP status: `413`.
- Body: `{"error": {"category": "payload_too_large", "message": "Diff exceeds the 256 KB limit. Try a smaller change.", "retryable": false}}`.
- Wall-clock from request to response: under 1 s (SC-004).
- Server log line carries `event=review.failed error_category=payload_too_large payload_bytes=300xxxx`, **but never includes the diff content**.

---

## Scenario D — Malformed LLM output (User Story 3, AS-2) — test-only

Not reproducible against a real provider without a contrived setup; covered by `tests/integration/test_review_endpoint.py::test_provider_malformed_output_502`. The test mocks `LLMProvider.chat` to return `"this is not JSON, dawg"` and asserts:

- HTTP `502`.
- Body category `provider_malformed_output`, `retryable: false`.
- A single WARNING log line: `event=review.failed error_category=provider_malformed_output provider=<name>`.

---

## What this does NOT yet do

These are **explicit non-goals** of 003 and will land in later features — do not block the merge on them:

- No repository indexing or RAG (still 004+).
- No async/queue (`arq`) — endpoint is synchronous.
- No posting comments back to GitHub PRs.
- No diff-chunking for monster refactors (just rejects with 413).
- No persistence of past reviews — close the tab, the result is gone.
