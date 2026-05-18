# Feature Specification: Git Temporal Analysis

**Feature Branch**: `008-git-temporal-analysis`
**Created**: 2026-05-19
**Status**: Draft
**Input**: User description: "008 git-temporal-analysis — git log -L driven temporal context as 3rd MUST differentiator (per ADR-011). For every PR finding that has (file, line), attach a 'history hint' — the last N commits that touched those specific lines — and surface it both to the LLM (during review) and to the user (collapsible block under each finding)."

## User Scenarios & Testing *(mandatory)*

This feature delivers the third of three MUST differentiators promised in ADR-011 (self-hosted air-gapped LLM, deep AST-RAG retrieval, **git-based temporal analysis**). It changes neither the high-level review flow nor the SPA navigation; it adds a *signal* — line-level history — that flows both into the LLM (so the model knows whether the touched lines are stable or hot) and back to the human reviewer (so they can audit the model's verdict against recent commits to the same range).

### User Story 1 - Per-finding line history is collected and surfaced inline (Priority: P1)

A reviewer pastes a PR URL against an indexed repository on `/review`. After the review completes, each finding that has a concrete `(file, line)` carries a small "History" disclosure underneath it; expanding the disclosure reveals the last few commits that touched exactly the lines the finding refers to — short SHA, date, author, and commit subject. The display is empty (and the disclosure hidden) whenever there is no relevant history, so the reviewer is never shown an empty box.

**Why this priority**: This is the user-visible payoff of the third differentiator. Without it the feature is invisible — even if the LLM uses temporal context internally, the human reviewer cannot audit whether the model's reasoning is consistent with recent commits, which is exactly the audit-trail discipline the thesis project is designed against. P1 because it is also the smallest viable slice: backend collects per-finding history, frontend renders it; nothing else is required for the feature to deliver value.

**Independent Test**: Index a public repository (e.g. a small open-source project) on `/repos`, paste a PR URL from that repository on `/review` with the indexed repo selected, run the review, expand any finding whose `(file, line)` falls inside a tracked file: the History disclosure shows 1–5 rows with non-empty SHA / date / author / subject. Repeat with a PR against a non-indexed repository: no History disclosure appears anywhere, the page behaves exactly as before this feature shipped.

**Acceptance Scenarios**:

1. **Given** a reviewer has just indexed a public HTTPS repository and a PR URL targeting that repository, **When** they submit the review with the indexed repo selected, **Then** every finding whose line falls inside a file that exists in the repository history shows a "History (N changes)" disclosure that expands to a table of N rows (1 ≤ N ≤ 5).
2. **Given** a finding whose line does not appear in the repository history (new file, generated file, line beyond current EOF), **When** the reviewer expands the finding, **Then** no History disclosure is rendered — the finding still shows severity, message, suggestion, and code-context exactly as in the previous release.
3. **Given** a review run **without** a repository selected (diff-only mode), **When** the review completes, **Then** no findings carry temporal context and no extra time is spent fetching history.

---

### User Story 2 - LLM is conditioned on the same line history before producing the verdict (Priority: P2)

When a reviewer selects an indexed repository for the review, the LLM that produces the findings receives, as part of its input, a compact summary of which lines in the PR diff have changed frequently in the recent past and by whom. The model uses this hint to weight whether a suggested change is consistent with recent intent on those lines — for example, recognising that a function rewritten three times in the last two months is a contested area where confident "approve" verdicts are riskier than usual.

**Why this priority**: This is what *separates* the feature from being a passive history viewer; without it, the LLM and the human reviewer see different evidence and the feature degrades to a UI add-on. P2 because it is downstream of P1: the same data is collected once per review and routed in two directions, but the collection has to exist first.

**Independent Test**: Trigger a review against an indexed repository with a known volatile file (≥ 3 commits in the last 90 days touching the diff range). Inspect the captured LLM prompt (via log assertions in tests) — it MUST contain a "Code history hints" section that names the file, the line window, and at least one commit subject. Trigger the same review path against a brand-new file with one commit in history — the section is either omitted or contains a single-line entry only.

**Acceptance Scenarios**:

1. **Given** a PR diff that touches a file with ≥ 2 commits in history within the touched line range, **When** the review pipeline assembles the prompt for the LLM, **Then** the prompt contains a "Code history hints" block listing those commits before the diff body.
2. **Given** a PR review run without an indexed repository, **When** the prompt is assembled, **Then** the prompt contains **no** "Code history hints" block and the prompt body matches the pre-feature shape byte-for-byte for the same diff.
3. **Given** the temporal fetch exhausts its time budget mid-collection, **When** the prompt is assembled, **Then** the prompt includes whatever was already collected up to that point and the review still completes within its normal latency envelope.

---

### User Story 3 - "Volatility" badge marks frequently-touched findings at a glance (Priority: P3)

When a finding's line range has been touched by three or more recent commits, a small "N changes" badge appears next to its severity pill so the reviewer notices high-volatility locations without expanding the History disclosure. The badge uses the existing info palette (no new colours) and is purely additive — never replacing or recolouring the severity itself.

**Why this priority**: This is a comfort-of-use improvement that depends on US1 being in place. It is small enough to ship in the same release but valuable enough to be in scope — it surfaces the most important signal (volatility) without forcing the reviewer to click every finding to learn which areas are hot.

**Independent Test**: Open a review whose findings include at least one with ≥ 3 history rows and at least one with ≤ 2 history rows. The first carries an inline "N changes" badge in the finding header; the second does not. Toggle the History disclosure on both: the disclosure body is consistent with the badge presence/absence.

**Acceptance Scenarios**:

1. **Given** a finding whose history contains 4 commits, **When** the findings list renders, **Then** a small "4 changes" badge sits inline next to the severity pill on that finding's header row.
2. **Given** a finding whose history is empty or contains ≤ 2 commits, **When** the findings list renders, **Then** **no** badge is rendered next to the severity pill on that finding.
3. **Given** a colour-blind reviewer, **When** they read any finding, **Then** the volatility badge is distinguishable by its text (e.g. "4 changes") not just its colour.

---

### Edge Cases

- **No indexed repository selected**: temporal-context collection is fully skipped, the prompt is identical to the pre-feature shape, and findings carry no `temporal_context` field in the response body.
- **Indexed repository whose `source` is a local path (not HTTPS)**: temporal collection is silently skipped — the runtime cache only handles HTTPS sources, and local-path indexing was always treated as an integration-test convenience rather than a user-facing flow.
- **Diff touches a file that has been renamed since its earliest history commit**: rename tracking is best-effort via `git log -L`'s built-in heuristic; rows that cannot be resolved across the rename are dropped, the disclosure stays compact and the reviewer is not shown stale entries.
- **Diff touches an enormous line range (>200 lines)**: the per-call line range is clamped to the first 200 lines so a single huge hunk cannot dominate the time budget.
- **`git fetch` fails on a stale cache entry**: the existing cache directory is used as-is for this review; the failure is logged but does not bubble to the user.
- **The whole temporal subsystem fails (disk full, `git` not on PATH, network out)**: the review completes with empty `temporal_context` on every finding; the page renders exactly as the pre-feature shape, and a single structured warning log line is emitted.
- **A finding's `line` is `null`** (LLM emitted a file-level remark): no temporal lookup is attempted for that finding; the field stays empty.
- **Same review is run twice in a row against the same repository**: the second run reuses the cached clone, observably faster than the first run on the same host; behaviour is otherwise identical.
- **A repository whose history has rewound (force-push to default branch)**: the cache entry's `git fetch --prune` aligns the local copy with the new remote state; the second review reflects the rewound history, not the stale one.
- **Cache directory has been wiped between requests** (container restart, manual rm): the next review re-clones and proceeds normally without a user-visible error.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The review pipeline MUST, when an indexed repository is selected for the review, collect line-level history hints for the set of `(file, line-window)` pairs derived from the PR diff hunks **before** invoking the LLM.
- **FR-002**: The collected history MUST be capped at five (5) most recent commits per `(file, line-window)` pair.
- **FR-003**: Each collected history entry MUST carry the commit's full SHA, a 7-character short SHA, the author email, the author date in ISO-8601 format, the commit subject truncated to 120 characters, and the number of lines the commit changed inside the window.
- **FR-004**: The total wall-clock time spent on temporal collection per review MUST NOT exceed two (2) seconds; if the budget is exhausted, whatever was collected up to that point flows through and the rest is skipped silently.
- **FR-005**: Each individual line-range lookup MUST be capped at 1.5 seconds; on timeout, the lookup returns an empty list and the overall review continues.
- **FR-006**: Each individual line-range lookup MUST be capped at 200 lines; line ranges beyond that are clamped to the first 200 lines.
- **FR-007**: The LLM prompt MUST include a "Code history hints" section listing the collected entries grouped by file when at least one history entry was collected; if zero entries were collected the section MUST be omitted in full.
- **FR-008**: After the LLM returns findings, each finding whose `(file, line)` falls inside one of the collected windows MUST have its `temporal_context` populated from the in-memory pool — no additional history lookups are issued at this stage.
- **FR-009**: Findings whose `(file, line)` does not match any collected window, and findings whose `line` is null, MUST carry `temporal_context = null` (or an empty list) in the response.
- **FR-010**: Reviews run without an indexed repository (diff-only mode) MUST NOT invoke any temporal-collection code path and the response shape MUST be byte-identical to the pre-feature shape for the same input.
- **FR-011**: The frontend MUST render a per-finding History disclosure, default-collapsed, only when the finding's `temporal_context` contains at least one entry; otherwise the disclosure is not rendered at all.
- **FR-012**: When the History disclosure is expanded, it MUST present the entries as a four-column display (short SHA / date / author local-part / subject), with the date in YYYY-MM-DD format and the subject truncated to 80 characters with an ellipsis.
- **FR-013**: When a finding's `temporal_context` contains three (3) or more entries, the finding header MUST display a small "N changes" volatility badge inline with the severity pill; for fewer entries, no badge is rendered.
- **FR-014**: The volatility badge MUST convey its meaning via text ("N changes") rather than colour alone so colour-blind reviewers can read it.
- **FR-015**: Cached repository clones MUST live entirely inside the API container's filesystem and MUST NOT introduce any new compose service, host-side volume, or external persistence requirement.
- **FR-016**: At most five (5) distinct repositories MUST be kept in the runtime cache at any time; on overflow, the least-recently-used entry MUST be evicted before a new clone is materialised.
- **FR-017**: A cache entry whose on-disk age exceeds one (1) hour MUST be refreshed via a fast fetch + prune before the next history lookup against it; the refresh failure path MUST fall back to reusing the existing entry as-is and emit a structured warning log line.
- **FR-018**: All git subprocess calls MUST run via the system async-subprocess API; no blocking synchronous git call is permitted on the API request path.
- **FR-019**: Temporal collection failures (subprocess non-zero exit, file not in history, OS errors, network errors on fetch) MUST be absorbed silently — the review MUST always complete, the response MUST always be well-formed, and exactly one structured warning log line MUST be emitted per failed lookup with a stable event name.
- **FR-020**: Per-review, exactly one structured info log line MUST be emitted summarising the temporal-collection outcome (number of files looked up, total entries collected, total elapsed milliseconds, whether the time budget was exceeded).
- **FR-021**: Repositories whose `source` is not an HTTPS URL (local-path indexing or any other future shape) MUST NOT trigger any clone or fetch; the temporal lookup silently returns an empty list and the review proceeds without history hints.
- **FR-022**: The response wire shape MUST extend the existing `Finding` object with an optional `temporal_context` array; the field MUST be omitted or `null` whenever no entries apply, so existing clients that do not know about it continue to parse the payload unchanged.

### Key Entities

- **Temporal entry**: a single commit that touched a specific window of lines in a specific file, carrying the commit SHA (full + short), author email, author date, commit subject, and the count of lines that commit changed inside the window.
- **Line window**: a contiguous range `(start_line, end_line)` inside one file, derived once per review by collapsing the diff hunks for that file. Up to three windows are kept per file; very long hunks are clamped to a 200-line window.
- **Cached clone**: a per-repository on-disk replica used purely as a query target by the temporal subsystem. Its lifecycle is fully controlled by the running API process — it is created on first lookup, refreshed when stale, evicted when the cache is full, and discarded with the container.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After running a review against an indexed repository where the diff touches a file with non-empty history, the reviewer can — within ten (10) seconds of the findings appearing — open any one finding's History disclosure and read at least one historical commit subject without leaving the page.
- **SC-002**: A review against an indexed repository where every diff hunk touches a file with non-empty history populates `temporal_context` on at least 80% of findings whose `line` is non-null.
- **SC-003**: A review against an indexed repository completes within the same wall-clock latency envelope as the same review before this feature shipped, plus at most an additional two (2) seconds — the upper bound of the temporal-collection time budget.
- **SC-004**: A review against an unindexed PR (diff-only mode) completes within the same wall-clock latency envelope as the same review before this feature shipped, with zero additional time spent on temporal collection.
- **SC-005**: Across ten consecutive reviews against the same indexed repository on the same running container, the median per-review time spent on temporal collection is no greater than half the first run's time (cache amortisation).
- **SC-006**: Across ten consecutive reviews under any inputs, the API server logs exactly one structured info entry per review reporting the temporal-collection summary (or zero, if the review ran without an indexed repository).
- **SC-007**: When the entire git subprocess subsystem is unavailable (binary missing, disk full, network out), reviews against indexed repositories still complete with well-formed findings and the user-facing page renders identically to the pre-feature shape.
- **SC-008**: When a reviewer compares two findings side-by-side — one with a four-row history and one with no history — the visual cue ("4 changes" badge present vs absent) is correctly perceived by colour-blind users without relying on the badge's colour.
- **SC-009**: When ten distinct repositories are indexed and reviewed in sequence on the same running container, the on-disk footprint of the runtime cache stabilises at five entries' worth of storage; no historical entries beyond the five most recently used remain on disk.

## Assumptions

- The reviewer's typical flow involves indexing a small number of repositories (single-digit) per host, well below the cache eviction threshold; reviews against repositories outside that working set pay a one-time clone cost on first use and are amortised thereafter.
- The repositories under review are public HTTPS GitHub repositories whose full history is fetchable without authentication; private-repo support is explicitly deferred to a later feature.
- Reviewers do not require historical context beyond five most recent commits per line window; deeper drill-down (per-author timelines, blame views, full file history) is out of scope and deferred to a separate "history dashboard" feature.
- Reviewers tolerate stale history up to one hour old between explicit re-fetches; force-pushes to the default branch will surface in the next review after the stale-cache refresh window elapses.
- Container restarts (re-deploys, host reboots) acceptably blow away the runtime cache — reviewers accept the first-run clone cost after restart in exchange for not maintaining a host-side persistent volume.
- Findings come back from the LLM with their `(file, line)` keys close enough to the diff's `(file, line-window)` coverage that pure file-name match on the right side is sufficient routing — the LLM is **not** expected to emit findings on lines outside the diff.
- The existing review flow's RAG retrieval, prompt assembly, parsing, and posting paths remain untouched; the only signature change on the wire is the addition of an optional history field on each finding.

## Out of Scope

- Per-author timeline visualisations and "who touched this file most" repo-level dashboards.
- Blame-style line-by-line authorship overlays.
- Private-repository / SSH-source / authenticated-clone temporal lookups.
- LLM-side ranking of "is this historical context relevant?" — the model receives the raw entries and decides for itself; no separate relevance filter is run.
- File-rename tracking deeper than `git log -L`'s built-in heuristic.
- Configurable cache directory, cache size, or budgets exposed in `.env.example` — all defaults are code-internal in v1; user-tunable knobs are deferred until a real operator asks for them.
- Persisting the runtime cache across container restarts.
- Integrating temporal hints into the PR-posting flow (the posted comment body keeps its pre-feature shape; the History display is `/review` UI only).
