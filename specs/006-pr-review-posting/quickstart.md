# Quickstart — PR Review Comment Posting

End-to-end smoke walk-through. Assumes feature 004 (Settings store) has shipped and a working `codesensei-bot` fine-grained PAT exists.

## Pre-requisites

- `docker compose up` is healthy (see `/healthz`).
- A `codesensei-bot` GitHub account exists.
- A fine-grained PAT on that account with:
  - Resource: the target repository (or "All repositories" for the account).
  - Permission: **Pull requests → Read and write**.
  - Permission: **Contents → Read**.
- The PAT has been saved in `/settings` under `GITHUB_TOKEN`.

## 1. Verify the PAT round-trips

Open `/settings`. The `GITHUB_TOKEN` row should display a redacted last-4 of the token. If empty: paste the token, save, and confirm the row now shows `…XXXX`.

## 2. Generate a review against a PR

Open `/review`. Paste a PR URL — for example, a PR on the target repository the bot has access to. Submit. Wait for the result to render. The page should show the verdict, the findings panel, and (if a context-repo was selected) the context-files panel.

The "Post to GitHub" panel appears **only** on PR-URL reviews. If you tested with a raw diff paste, the panel is hidden by design — re-run with a PR URL to see it.

## 3. Pick the event

The radio group pre-selects an event based on the verdict:

- `approve` → `Approve`
- `request_changes` → `Request changes`
- `comment` → `Comment`

Change the selection if you want to override. The choice is yours; the backend honours whatever you pick.

## 4. Post

Click **Post to GitHub**. Watch the spinner. On success (typically ≤ 2 s for a small review) the panel collapses into a `Posted ✓` confirmation with a `View on GitHub` link.

Open that link in a new tab. You should see:

- A new review on the PR.
- The review event matches what you chose.
- Each finding with a `file:line` appears as an inline comment on the right-hand side of the diff, with the markdown body formatted `**severity** (category): message` and an optional `_Suggestion_: …` paragraph.
- The top of the review carries the verdict-summary line and the provider-attribution line.
- Findings without a `file:line` (or beyond the 50-cap) appear as bullets in the review body under `### Findings without inline location` / `### Additional findings (beyond the 50-comment cap)`.

## 5. Verify single-use lock

Back on the `/review` page, attempt to click again. The submit button is gone — only the success badge remains. Refresh the page or run a new review to get a fresh post panel.

## 6. Failure-path smoke tests

For a thesis-grade defense each error path needs to be visible. Recommended manual sequence:

| Path | How to trigger | Expected UI |
|------|----------------|-------------|
| `settings_locked` | Delete `GITHUB_TOKEN` from `/settings`. Re-open the review page, click Post. | Banner says "GitHub token not configured." with a "Go to Settings" button. |
| `github_auth_failed` | Save a PAT scoped to `Pull requests: read` only (no write). | Banner says the missing permission name verbatim. No retry. |
| `github_pr_not_found` | Generate a review against a PR URL the bot cannot reach (private repo without grant, or a `pull/999999` that does not exist). | Banner: "GitHub could not find this PR — check the URL." No retry. |
| `github_review_rejected` (after fallback) | Force-update the PR to remove the file/line that the rendered review pointed at, then post. | Banner with the GitHub raw message visible. |
| `github_api_unavailable` | Block egress to `api.github.com` (firewall, or `/etc/hosts` trick) while clicking Post. | Banner: "GitHub is unreachable." Retry button. |
| `github_rate_limited` | Spam-post 5 000 reviews in an hour (impractical to verify in real life). | Banner with countdown. |

The `github_rate_limited` path is exercised in unit tests with a `respx` route that returns 429 + `Retry-After: 60`; the live smoke test usually skips it.

## 7. Verify no local state was persisted

```bash
docker compose exec db psql -U codesensei -d codesensei \
  -c "SELECT relname FROM pg_stat_user_tables ORDER BY relname;"
```

The set of tables MUST be identical to the set present before this feature shipped. No `posted_reviews` table. No `github_post_audit` table. Nothing.

If `alembic_version` shows a new revision attributed to feature 006 — that is a bug; this feature ships no migration.

## 8. Verify the structured log line

```bash
docker compose logs api | grep github_review_posted
```

Each successful post emits one JSON line carrying `pr_url`, `event`, `comment_count`, `body_chars`, `elapsed_ms`, `review_id`, `outcome`, `attempted_calls`. Each failure emits the same line with `review_id=null` and `outcome=<category>`. The PAT MUST NOT appear in any log line; `docker compose logs api | grep -i ghp_` should return nothing related to this feature.

## Cost / quota notes

- This feature does not call any LLM or embedding provider — zero AI cost per post.
- Each post is one GitHub REST call (two on the 422-fallback path). Against the 5 000 req/h bot-PAT primary rate limit, this is effectively free at thesis-demo traffic levels.
