# Research — 009 Review History & Reports

Resolves the open questions surfaced in `plan.md` (R1–R12). Each entry pairs the chosen decision with the rejected alternatives and the reason for rejection.

## R1 — Two tables vs one JSONB blob

- **Decision**: Two tables — `review_runs` (run-level metadata + the normalised diff text) and `review_findings` (one row per emitted finding).
- **Rationale**: Mirrors the existing `repos` + `code_chunks` split. Lets us add a single-column index on `review_findings.severity` or `.file` in a future feature without rewriting the schema or reading a parsed-back blob. Joinable at SQL level — a future "all findings ever flagged as blocker" query is one `JOIN ... WHERE severity='blocker'`, not a row-by-row JSON unmarshal.
- **Alternatives considered**:
  - Single `review_runs` table with a `findings JSONB` column: simpler to insert (one row per review) but harder to evolve; every future per-finding query becomes JSONB-path traversal.
  - Single wide table denormalising every (run, finding) pair: smaller in dev, but writes go N-times-amplified and DELETE on overflow becomes expensive.

## R2 — JSONB for `temporal_context` per finding

- **Decision**: Store `temporal_context` as a JSONB column on `review_findings`.
- **Rationale**: The shape ships verbatim from the LLM-parsed pydantic dataclass + `_attach_temporal_context` routing in `review/service.py`. We never query into the JSON (no "show me findings whose history mentions alice@x"); we read the column as an opaque payload to render. A sub-table for entries would add 4-rows-per-finding on average for zero query benefit.
- **Alternatives considered**:
  - `review_temporal_entries(run_id, finding_position, sha, date, email, subject, lines_changed)` sub-table: relational purity but no future query needs it.
  - Drop the field on persist and re-fetch via `git log -L` on detail open: forfeits the SC-006 guarantee that the detail view shows the same history rows the live view showed (the underlying repo may have shifted).

## R3 — `repos` FK behaviour: `ON DELETE SET NULL` vs `CASCADE`

- **Decision**: `repo_id` is nullable + `ON DELETE SET NULL`.
- **Rationale**: FR-020 — stored runs MUST survive the deletion of their referenced repository. The verdict + findings are far more durable than the `/repos` row that backed retrieval; reviewers expect a deleted repo not to wipe past history.
- **Alternatives considered**:
  - `ON DELETE CASCADE`: nukes history along with the repo, surprising for reviewers who delete a repo intending to clean up.
  - `ON DELETE RESTRICT`: prevents the repo delete, requires manual cleanup of dependent rows. Bad UX.

## R4 — Best-effort persist (try/except) vs transactional bundling

- **Decision**: Persist runs **after** the live response is fully composed; wrap in `try/except` that only logs a structured warning on failure (no re-raise).
- **Rationale**: FR-003 — the live response is the canonical user-visible artefact. A transient DB outage during persistence MUST NOT regress the live latency or fail the user-facing call. The user can always re-run a missed review; they cannot un-fail a failed-because-of-DB review.
- **Alternatives considered**:
  - Wrap the whole `_run_chat` in a single transaction including persist: a DB outage would surface as a 502 even though the LLM call succeeded.
  - Persist via `arq` background task post-response: adds a new dependency on the queue for a P1 feature; the persist call is < 50 ms and inline is simpler and equally fault-tolerant.

## R5 — Prune both on startup AND inline

- **Decision**: Run the prune step at process startup (one-shot, after the migration pass) AND after every successful inline persist.
- **Rationale**: Startup catches any historical excess (e.g. from a prior process crash mid-prune). Inline keeps the cap tight without a separate scheduled job. Both prune ops are bounded — `DELETE WHERE id IN (SELECT id FROM review_runs ORDER BY created_at ASC LIMIT N)` — and the inner SELECT uses the new `(created_at DESC, id)` index.
- **Alternatives considered**:
  - Inline-only: rare crash scenarios leave excess until the next persist (acceptable in v1, but startup is free).
  - Startup-only: cap drifts during long-running processes if reviews come in bursts.
  - Periodic arq job: introduces scheduling complexity; the inline path already keeps the cap.

## R6 — 1000-row cap as a code-internal constant

- **Decision**: `_HISTORY_MAX_ROWS = 1000` lives in `reviews_history/store.py`. No `.env.example` entry; no `app_settings` row.
- **Rationale**: Out-of-Scope item in spec — operator-tunable knobs are deferred. The cap is plenty for a single-user thesis demo; relocating to env later is a one-file change.
- **Alternatives considered**:
  - Expose via `CODESENSEI_HISTORY_MAX_ROWS` env var: more operator surface (docs, .env.example, settings UI) for hypothetical demand.

## R7 — No `created_by` / multi-user column

- **Decision**: `review_runs` has no `user_id` or `created_by` column.
- **Rationale**: Single-user self-hosted v1 (Assumptions in spec.md). Adding a column we cannot meaningfully fill would mislead future readers into thinking the table is multi-tenant-ready when it isn't.
- **Alternatives considered**:
  - `created_by TEXT NULL`: pollutes schema without serving a current need.

## R8 — Listing pagination: 50 default, 200 max

- **Decision**: `GET /api/reviews?limit=N`, default `limit=50`, hard max `limit=200`.
- **Rationale**: Matches typical SPA "first page" semantics; the History page renders top-50 below the fold on a typical desktop viewport. Operators who genuinely want 200 (e.g. backups, audits) can request it; > 200 forces them to query the DB directly (out of scope: real pagination, full-text search).
- **Alternatives considered**:
  - Default 100 / max 1000: forces wide DOM lists in the SPA with no real benefit.
  - Default 20 / max 50: too conservative; a casual reviewer might miss runs.

## R9 — Wiring the stored diff back into PostToGitHubPanel

- **Decision**: `GET /api/reviews/{run_id}` returns the full `ReviewResult` shape PLUS the stored `pr_url` + `diff`. The detail page passes `diff` / `verdict` / `findings` straight to `<PostToGitHubPanel>` props with zero conditional code — the panel already supports this prop set from feature 006.
- **Rationale**: Re-uses the existing posting flow with no new endpoint or panel variant. The panel's existing retry / toast semantics carry over.
- **Alternatives considered**:
  - New `POST /api/review/post/from-history/{run_id}` endpoint: extra surface area for zero benefit.
  - Refetch the diff from GitHub on detail open: requires the PR + PAT to still be valid; defeats the point of persistence.

## R10 — Store the diff verbatim, uncompressed

- **Decision**: `review_runs.diff TEXT NOT NULL`, no compression.
- **Rationale**: Existing 200 KB per-review cap (`review_max_diff_bytes`) bounds the size. PostgreSQL's TOAST mechanism transparently compresses large TEXT columns server-side. Application-level compression adds complexity (codec choice, encoding/decoding) for zero observable benefit at this size.
- **Alternatives considered**:
  - zstd at the application layer: cuts a few KB at the cost of an extra dependency + decode-on-read.
  - Store in a separate `large_objects` table: over-engineering at this scale.

## R11 — Detail endpoint shape: byte-identical to the live response

- **Decision**: `GET /api/reviews/{run_id}` returns a payload whose JSON shape matches `POST /api/review`'s response, PLUS two extra top-level fields needed for the detail view: `created_at` (ISO-8601) and `pr_url` / `diff` for the Re-run / Re-post affordances.
- **Rationale**: The SPA detail view re-uses the existing `FindingsList` rendering branch with zero conditional code (FR-007 / FR-019). Frontend developers don't have to remember a second findings shape.
- **Alternatives considered**:
  - Return only the new fields; expose stored findings via a separate `GET /api/reviews/{run_id}/findings`: doubles the request count for the same data.
  - Reshape findings on the wire (e.g. flatten temporal_context): would force the SPA into a conditional render path.

## R12 — Prune SQL shape

- **Decision**: `DELETE FROM review_runs WHERE id IN (SELECT id FROM review_runs ORDER BY created_at ASC LIMIT :n)` where `n = max(0, count - _HISTORY_MAX_ROWS)`.
- **Rationale**: The inner SELECT scans the `(created_at DESC, id)` composite B-tree index (reverse-scan); the DELETE then fans out via the FK with `ON DELETE CASCADE` to `review_findings`. SQLAlchemy 2.x async + asyncpg handles this in a single round-trip.
- **Alternatives considered**:
  - CTE-based ranked delete (`WITH ranked AS (...) DELETE FROM review_runs USING ranked WHERE ...`): same plan but harder to read.
  - Two-step: SELECT IDs in Python, then DELETE WHERE id = ANY(:ids): one extra round-trip for nothing.

---

## Cross-cutting research notes

### Alembic revision shape

`backend/alembic/versions/004_review_history.py` — `down_revision = "003_repos_chunks"`. Two `op.create_table` calls + one `op.create_index` for `(created_at DESC, id)`. Downgrade reverses in the opposite order. Mirrors the style of `003_repos_chunks.py`.

### ADR-013 to draft

Title: **Persist review history in DB — `review_runs` + `review_findings`**. Hard-trigger record per Principle II. Schema sketch + retention shape (1000-row cap, `ON DELETE SET NULL` on repo FK, JSONB for temporal_context, prune-on-overflow). NFR-3.1 confirmation: no plaintext credentials persisted — only diff + findings. Status: accepted on 2026-05-19, supersedes nothing. Drafted as task T002 BEFORE any production code.

### Frontend route additions

`router.ts` already exists; add two route objects:

```ts
{ path: '/history', component: HistoryPage },
{ path: '/history/:runId', component: HistoryDetailPage, props: true },
```

`AppShell.vue` gets a 5th `<RouterLink>` between "Repos" and "Settings".

### Re-use of in-tree primitives

No new primitive is added. List page uses `Card`, `Badge`, `Button`; detail view uses the existing `FindingsList`, `PostToGitHubPanel`, `Card`, `Button`. Verdict filter chips on the list page reuse `Badge` with `tone="info"` and a click handler.

### What stays unchanged

- `review/parser.py`, `review/prompt.py`, `review/schema.py`, `review/git_temporal.py` — all untouched.
- `review/service.py` — one new call site at the end of `_run_chat` (a single `await` inside `try/except`).
- `posting/` — untouched (the panel re-use happens on the SPA, not the backend).
- All existing tests — pass unchanged (persistence is additive).
