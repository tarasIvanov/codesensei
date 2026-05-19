# Feature Specification: Review History & Reports

**Feature Branch**: `009-history-and-reports`
**Created**: 2026-05-19
**Status**: Draft
**Input**: User description: "009 history-and-reports — persist every review run + /history SPA page. Closes MUST scope FR-3.3 (parse → store) + FR-5.1 (report storage) + FR-5.2 (history list, instant open without re-call LLM) from _mvp_scope.md §2.4 / §2.5."

## User Scenarios & Testing *(mandatory)*

This feature closes three FRs from the bachelor MVP scope that are currently the only unshipped slices of `_mvp_scope.md` §2.4 / §2.5: storing every review run, listing them under a dedicated SPA page, and reopening a stored run without spending a fresh LLM call. The feature is purely additive on the existing review pipeline: persistence runs after the LLM returns; the live `POST /api/review` response shape does not change; the new `/history` SPA page sits alongside `/`, `/review`, `/repos`, `/settings` as the fifth nav entry.

### User Story 1 - Every review is auto-saved and shows up in History (Priority: P1)

A reviewer runs a review on `/review` (either from a pasted diff or from a PR URL, with or without an indexed repository). When the review finishes successfully, the outcome is stored automatically (no extra click), and the new `/history` page lists it as the topmost row — verdict, provider, finding count, relative timestamp, optional PR URL. Clicking the row opens a detail view that renders the original findings exactly as they appeared on `/review` (same severity pills, code-context snippets, collapsible groups, History disclosures from feature 008, volatility badges), without invoking the LLM a second time. The detail view also exposes a small "Delete this run" action.

**Why this priority**: This is the user-visible value of the feature on its own. Without it, every review is fire-and-forget — the reviewer cannot revisit yesterday's verdict, cannot share a stable link to a specific review, cannot audit past activity. P1 because the persistence + list + detail + delete is the smallest fully-useful slice; everything else (re-run, re-post, filter chips) is additive.

**Independent Test**: From a fresh DB, run two reviews on `/review` — one diff-only, one with a PR URL + indexed repo. Open `/history`: both rows appear, newest first, with the correct counts and verdicts. Click the older row: the detail view shows the same findings the user saw originally (incl. temporal context if it was an indexed-repo run). Click "Delete this run" on the detail view: the row disappears from `/history` and reopening the deleted detail URL renders a "not found" empty state. The live `/review` page behaviour is unchanged for the same inputs.

**Acceptance Scenarios**:

1. **Given** a successful review just completed on `/review`, **When** the reviewer navigates to `/history`, **Then** the new run is the topmost row with `created_at` displayed as a human-friendly relative timestamp ("just now"), the correct verdict pill, the provider badge, and the finding count.
2. **Given** the reviewer is on `/history` looking at a list of stored runs, **When** they click any row, **Then** the URL becomes `/history/<run_id>` and the page renders the same findings (severity pills, suggestions, code-context, temporal disclosures, volatility badges) as the original live response — with **no** additional outbound LLM call.
3. **Given** an unsuccessful review (provider error, invalid input, settings locked), **When** the reviewer opens `/history` afterwards, **Then** no row for that failed attempt appears — only successful runs are persisted.
4. **Given** the detail view of a stored run, **When** the reviewer clicks "Delete this run", **Then** the row is removed from the DB, a toast confirms deletion, and the reviewer is navigated back to `/history`.
5. **Given** a stored run whose `repo_id` referred to a repository that has since been deleted from `/repos`, **When** the reviewer opens that run's detail view, **Then** the page still renders the original findings unchanged (only the live "repository link" affordance, if any, is greyed out).

---

### User Story 2 - Re-post and re-run a historical run without retyping (Priority: P2)

The detail view of a historical run includes two convenience affordances when the run was produced from a PR URL: a "Post to GitHub" panel that re-uses the existing posting flow against the same PR (without spending a fresh LLM call) and a "Re-run" button that submits the same input (diff or PR URL) back through `/api/review` to produce a brand-new run in the history.

**Why this priority**: Re-posting and re-running are second-order workflows — useful but not the primary value. P2 because they ride on top of US1's persistence and detail view, and depend on storing the original diff verbatim so the posting endpoint can be re-fed without a fresh fetch.

**Independent Test**: Open the detail view of a stored run whose input was a PR URL. Click "Post to GitHub" → toast confirms success and the PR comment appears on GitHub (same outcome as posting from `/review` immediately after the live run). Click "Re-run" → a new row appears at the top of `/history` (with a fresh `created_at` and possibly different findings, since the diff or the LLM may have changed). The original historical run remains in the list.

**Acceptance Scenarios**:

1. **Given** a stored run produced from a PR URL, **When** the reviewer opens the detail view and clicks "Post to GitHub", **Then** the existing posting flow runs (same toast, same retry semantics), publishing the stored verdict + findings to the original PR.
2. **Given** a stored run produced from a pasted diff (no PR URL), **When** the reviewer opens the detail view, **Then** the "Post to GitHub" panel is absent — only "Re-run" and "Delete this run" are available.
3. **Given** any stored run, **When** the reviewer clicks "Re-run", **Then** `/api/review` is invoked with the stored input (diff or PR URL) and the resulting fresh run appears at the top of `/history` (the original historical run stays).

---

### User Story 3 - Retention pruning + verdict filters (Priority: P3)

Older runs auto-prune past a fixed cap so the DB never grows unbounded; the History page also offers client-side filter chips by verdict so the reviewer can quickly narrow the list down to the runs that need attention.

**Why this priority**: This is operational hygiene. Without pruning, the table grows forever; without filter chips, scanning a hundred runs visually is slow. P3 because both features are valuable but neither blocks demo or thesis defence — a clean v1 ships without them.

**Independent Test**: Programmatically insert 1005 stored runs at carefully-chosen timestamps. After the next successful review (which triggers the prune step), only the 1000 most-recent runs remain; the 5 oldest are gone from both `/api/reviews` and any detail-view URL. On `/history`, click the "request_changes" filter chip — only runs whose verdict is `request_changes` remain visible (the list shrinks without a network call); click the chip again — the full list returns.

**Acceptance Scenarios**:

1. **Given** the `review_runs` table holds the cap of 1000 stored runs, **When** a 1001st successful review is stored, **Then** the oldest stored run is silently removed (and its findings cascade-deleted) so the table holds 1000 entries.
2. **Given** the reviewer is on `/history` with the full 50-row list visible, **When** they click the "approve" verdict filter chip, **Then** only runs with verdict `approve` remain visible; the URL reflects the active filter so a refresh preserves the view.

---

### Edge Cases

- **The same PR URL is reviewed twice in a row**: two distinct runs are stored; both appear independently on `/history`. There is no implicit de-duplication — the reviewer is shown both runs and can decide.
- **A stored run's `repo_id` points at a repository that was deleted**: the run survives (FK is `ON DELETE SET NULL`); the detail view renders findings normally; any "open repo" link affordance is hidden.
- **A stored run's `pr_url` no longer resolves on GitHub** (PR was deleted, repository renamed): the detail view still renders findings; the "Post to GitHub" action will fail at HTTP time with the existing posting-flow error envelope, surfaced as a toast.
- **`/api/reviews/<run_id>` is hit for a non-existent run ID**: 404 with the standard error envelope; the SPA detail view shows a friendly "Run not found" empty state with a back-to-history link.
- **`DELETE /api/reviews/<run_id>` is hit for a non-existent run ID**: 404 with the standard error envelope (idempotent: deleting an already-deleted run is a 404 the second time).
- **The retention cap is reached when no review has run since startup**: the startup prune task runs once and trims any historical excess; from then on, every successful new run triggers an inline prune.
- **The reviewer's browser back/forward navigation between `/history` and a detail view**: cached list and detail data survive without re-fetch (standard SPA back/forward semantics).
- **The user navigates directly to `/history/<run_id>` via a shared URL**: works; no special bootstrap needed.
- **A stored run has zero findings**: the detail view shows the same empty state ("No findings — verdict: approve") that `/review` shows.
- **The DB is paused / unreachable when the live review finishes**: the review still returns its result to the user (the live response is the source of truth); persistence is best-effort with a structured warning log line on failure — the live flow does NOT block on a DB write failure.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Every successful run of the existing review entry-points MUST persist a stored run record carrying the original input shape (diff or PR URL), the resolved repository identifier when one was selected, the LLM verdict, the active provider name, the wall-clock elapsed time, and the count of findings the model produced.
- **FR-002**: Every stored run record MUST persist each individual finding (file, line, severity, message, optional suggestion, optional temporal context) in the order the LLM emitted them.
- **FR-003**: Persistence MUST be additive on the existing review pipeline — the live `/api/review` response shape and latency budget MUST NOT be observably affected, and a DB-side failure during persistence MUST NOT cause the live response to fail.
- **FR-004**: Reviews that error out before producing findings (invalid input, provider error, settings locked, retrieval failure) MUST NOT produce a stored run record.
- **FR-005**: A history listing endpoint MUST return the most-recent stored runs in descending order of creation time, returning each row's `id`, `created_at`, `verdict`, `provider`, `finding_count`, `elapsed_ms`, optional `pr_url`, and a boolean indicating whether temporal context was collected on that run.
- **FR-006**: The listing endpoint MUST cap its response at the most-recent 50 rows by default, with an optional `limit` query parameter accepting `1..200`.
- **FR-007**: A per-run detail endpoint MUST return a payload shape byte-identical to the live review response (verdict, findings array with `temporal_context` preserved, provider, elapsed_ms, optional context_files), so the SPA detail view re-uses the live findings renderer without branching.
- **FR-008**: A per-run delete endpoint MUST remove the run and all its findings atomically, returning 204 on success and 404 when the run does not exist.
- **FR-009**: The History SPA page MUST list the most-recent runs (up to 50) ordered newest-first, with each row showing the relative timestamp, verdict pill, provider badge, finding count, optional PR URL, and an affordance to open the run's detail view.
- **FR-010**: The History SPA page MUST be reachable from the top-bar nav as the fifth entry between "Repos" and "Settings", and the corresponding route MUST be `/history` (list) plus `/history/<run_id>` (detail).
- **FR-011**: The detail view MUST render findings using the same in-tree primitives and severity/temporal/context components used by `/review`, with no fresh LLM call against the provider.
- **FR-012**: The detail view MUST offer a "Delete this run" action that on success removes the row, surfaces a confirmation toast, and navigates back to the list.
- **FR-013**: The detail view MUST offer a "Re-run" action that submits the run's stored input (diff or PR URL) back through the existing review entry-point, producing a fresh run at the top of `/history`.
- **FR-014**: The detail view MUST show the existing GitHub-posting affordance only when the original input was a PR URL; for diff-only stored runs the panel MUST be absent.
- **FR-015**: When the posting affordance is shown on a stored detail view, it MUST publish the original stored verdict + findings against the original stored PR URL, using the existing posting flow with no fresh LLM call.
- **FR-016**: The History SPA page MUST offer verdict-filter chips (`approve`, `request_changes`, `comment`); the chips MUST filter the already-loaded list client-side (no extra round-trip) and MUST preserve the active filter across page refresh via the URL.
- **FR-017**: A storage cap of 1000 stored runs per database MUST be enforced; on overflow, the oldest stored runs MUST be removed silently (cascading their findings) before the new run is acknowledged.
- **FR-018**: Pruning MUST run at API process startup once (to handle any prior excess) and after every successful persist (to keep the cap tight); pruning failures MUST NOT block the live review response.
- **FR-019**: The wire shape of the detail endpoint MUST preserve the per-finding `temporal_context` array exactly as it was emitted when the run was live, including empty / absent fields, so the detail-view's History disclosure and volatility badge behave identically to the live `/review` page.
- **FR-020**: Stored runs MUST survive deletion of their referenced repository (the FK relationship to the repository MUST be nullable and resolve to NULL on repository delete).
- **FR-021**: Stored diffs MUST never exceed the existing per-review diff size cap; the persistence step MUST NOT introduce a separate, larger limit that could overflow the database row size.
- **FR-022**: The history listing and detail endpoints MUST share the same authorisation surface as the rest of the API (in v1, single-user self-hosted with no auth layer); they MUST NOT be exposed unauthenticated if a future auth layer is added.

### Key Entities

- **Review Run**: a single, successful invocation of the review pipeline. Identified by an opaque UUID assigned at persist time. Carries the original input (kind, optional PR URL, optional repository handle, full diff string), the LLM verdict, the active provider name, the wall-clock elapsed time, the count of findings, a flag for whether temporal context was collected, and the optional list of repository files that contributed retrieval context.
- **Finding**: an individual issue the LLM flagged inside a Run. Identified by an opaque UUID + a stable position inside its parent Run. Carries file, optional line number, severity, message, optional suggestion text, and optional temporal context (the per-line `git log -L` history shipped by feature 008, preserved verbatim).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After running any successful review on `/review`, the reviewer can — within five (5) seconds of leaving the review page — open `/history` and see the new run as the topmost row.
- **SC-002**: Opening a stored run's detail view completes within two (2) seconds end-to-end on a typical host (DB hit + SPA render), with zero outbound LLM provider calls observed in API logs.
- **SC-003**: A typical bachelor-thesis workload (≤ 50 reviews per host per week) keeps the History page interactive without pagination — the page renders all 50 rows below the fold within the same render budget as the existing `/repos` page.
- **SC-004**: When the storage cap is reached and 100 additional reviews are run in sequence, the database row count for stored runs stabilises at exactly the cap (1000), with no growth, no manual intervention, and no impact on the live review wall-clock latency budget.
- **SC-005**: Across ten consecutive failed reviews (provider error, invalid input, settings locked), zero stored run records are created — only successful reviews appear in the history.
- **SC-006**: The detail view of a stored run that originally carried temporal context (feature 008) shows the same History (N changes) disclosures and "N changes" volatility badges as the live review page did, with the same row counts and the same visual ordering.
- **SC-007**: Deleting a stored run from the detail view removes its row from the History list immediately on return, and the same detail-view URL resolves to a friendly "Run not found" empty state when re-opened.
- **SC-008**: A stored run produced from a PR URL can be re-posted to GitHub from its detail view in the same number of clicks as posting from `/review` immediately after the live run.
- **SC-009**: A reviewer who lands directly on a shared `/history/<run_id>` URL (e.g. from a chat message) reaches the detail view without first visiting `/history`.

## Assumptions

- The single-user self-hosted boundary remains intact in v1 — there is no auth layer; every operator who can reach the API can read and delete every stored run.
- Reviews are run interactively from the SPA only — there is no expectation of webhook-driven background runs in v1, so persistence runs inline with the live request.
- The reviewer accepts that a force-pushed PR or a renamed branch may make a re-post against a stored historical run fail at GitHub-API time; no smart compensation is attempted.
- A stored diff up to the existing 200 KB per-review cap fits comfortably in a single database row without compression or chunking.
- The retention cap (1000 stored runs) covers a typical bachelor-thesis demo and operator's first months of use; tunability of this cap is deferred to a later feature.
- A failed DB persist is a worse outcome than a missing history entry, so the live review response is the source of truth and persistence is best-effort with a structured warning on failure.

## Out of Scope

- Multi-user / role-based access to history.
- Full-text search over stored findings.
- Side-by-side comparison of two stored runs.
- Export of a stored run to JSON, Markdown, or PDF.
- Pagination beyond a fixed 50-row top-of-list view.
- Persistence of the LLM's raw response body alongside the parsed findings.
- Persisting failed-review attempts (their inputs, error envelope, retry trail).
- Automatic re-running of stored runs on a schedule, or auto-posting them to GitHub.
- Webhook-driven background runs and their history.
- De-duplication of stored runs that target the same PR URL.
- A "diff between two stored runs" view.
- Server-side filter / sort beyond the basic `ORDER BY created_at DESC` + `limit`.
- Bulk delete / bulk export of stored runs from the History page.
