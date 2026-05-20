# Feature Specification: MVP closure — custom-ignore + live index progress

**Feature Branch**: `013-mvp-closure`
**Created**: 2026-05-21
**Status**: Draft
**Input**: User description: "013 mvp-closure — `.codesensei-ignore` + WebSocket index progress (closes FR-4.3 + FR-6.1 from `_mvp_scope.md` §2.3)."

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Custom ignore file respected during indexing (Priority: P1)

The operator places a `.codesensei-ignore` file at the root of the repository being indexed and lists project-specific paths or globs that should not be walked. When CodeSensei (re-)indexes the repository, the contents of that file are honoured in addition to the built-in skip rules (the hardcoded `skip_dirs` like `.git`, `node_modules`, `__pycache__` and the supported-extension whitelist). Nothing from a directory or matching glob makes it into the indexed chunk store.

**Why this priority**: closes one of the last MUST checkboxes from the MVP scope (`_mvp_scope.md §2.3 FR-4.3`). Without it, operators with non-conventional repo layouts — generated code under `gen/`, vendored sources under `third_party/`, fixture snapshots like `**/*.snap` — silently index garbage that pollutes RAG retrieval and inflates embedding cost. The escape hatch is small to ship and high-impact on review quality.

**Independent Test**: place a `.codesensei-ignore` file at a repo root with one line `vendor/`, trigger a re-index, then list indexed chunks for that repo and confirm no chunk's file path starts with `vendor/`. Quickstart Step 1.

**Acceptance Scenarios**:

1. **Given** a repository whose root contains a `.codesensei-ignore` file with the single line `vendor/`, **When** the operator triggers indexing, **Then** the resulting chunk set contains zero chunks under `vendor/`, while non-`vendor/` files are indexed as before.
2. **Given** a `.codesensei-ignore` file with lines `# vendored\n*.generated.ts\ndist/`, **When** indexing runs, **Then** lines starting with `#` are treated as comments, the `*.generated.ts` glob excludes any file whose name ends with `.generated.ts` regardless of directory, and `dist/` excludes the `dist` directory at any depth.
3. **Given** no `.codesensei-ignore` file exists at the repo root, **When** indexing runs, **Then** behaviour is identical to today (only the built-in skip set applies) and no errors are surfaced.
4. **Given** a `.codesensei-ignore` file containing 350 lines (300 of which are usable patterns), **When** indexing runs, **Then** the first 200 patterns are applied, a warning event is logged, and indexing completes successfully.
5. **Given** a `.codesensei-ignore` file larger than 4 KB, **When** indexing runs, **Then** the file is treated as if absent (no patterns applied), a warning event is logged, and indexing completes successfully.
6. **Given** a previously-indexed repository whose `.codesensei-ignore` file is changed between two index runs, **When** the operator re-indexes, **Then** the new pattern list is used for the new run; the previous run's outcome is not retroactively modified.

---

### User Story 2 — Live indexing progress without polling (Priority: P1)

The operator starts an asynchronous index run on a medium-sized repository (say, 200+ source files). The `/repos` page shows a progress card with `N of M files`, `K chunks`, and the current file being processed. Updates arrive in real time as the worker advances through the tree — there is no perceptible delay between "the worker finished a file" and "the UI shows the new count". If anything in the network path between the browser and the API breaks, the progress card transparently falls back to the previous polling experience without the operator seeing a stall or an error toast.

**Why this priority**: closes the second MUST-scope gap (`_mvp_scope.md §2.3 FR-6.1` real-time progress over WebSocket). The current 2-second polling is correct but feels laggy on long index runs (visible "frozen" intervals); a defence demo where the bar moves smoothly is materially better. Polling stays as the graceful fallback, so the change is purely additive — nothing breaks if the WebSocket can't connect.

**Independent Test**: open `/repos`, kick off an index on a fixture repo with ≥ 50 files, observe the progress card update at roughly the worker's natural file-completion rate; verify in browser DevTools that there are no recurring `GET /api/jobs/<id>` requests while the WebSocket is open. Quickstart Steps 3–4.

**Acceptance Scenarios**:

1. **Given** an active index job, **When** the SPA's progress card mounts, **Then** the first progress event arrives within 1 s, and subsequent events arrive at the worker's natural pace (up to ~2 per second, coalesced).
2. **Given** the progress card is streaming, **When** the network path between SPA and API is interrupted (e.g. the reverse-proxy drops the connection), **Then** the SPA automatically falls back to the existing polling at the existing 2 s interval, with no visible error toast.
3. **Given** an index job that completes successfully, **When** the worker emits its final event, **Then** the SPA receives a `complete` event with `state: "success"`, the card transitions to its "ready" state, and the stream is closed.
4. **Given** an index job that fails, **When** the worker terminates with an error category, **Then** the SPA receives a `complete` event with that category and message, and the card surfaces the error.
5. **Given** the operator opens the progress card for a job ID that does not exist (e.g. a stale URL), **When** the WebSocket attempts to connect, **Then** the server politely refuses with a not-found close code and the SPA falls back to polling, which returns the same not-found response from the existing endpoint.

---

### User Story 3 — `.codesensei-ignore` transparency in the UI (Priority: P2)

When the operator opens `/repos`, each repo card with a `.codesensei-ignore` file shows a small badge — for example, `🚫 5 custom ignores` — and a tooltip (or click-to-expand panel) listing the parsed patterns so the operator can audit at a glance what got skipped. The Settings page gains a static help section that explains the file format (one glob per line, `#` comments, trailing `/` for directories, hard cap at 200 patterns / 4 KB).

**Why this priority**: pure transparency / discoverability layer on top of US1. Operators benefit from being able to confirm "yes, my ignore file is being read" without dropping to logs, and the Settings help removes a documentation black hole.

**Independent Test**: index a repo with a `.codesensei-ignore` file containing 3 patterns; open `/repos` and confirm the badge reads `3 custom ignores`; click/hover to confirm the tooltip lists the three patterns verbatim. Quickstart Step 2.

**Acceptance Scenarios**:

1. **Given** a successfully-indexed repo whose source contained a `.codesensei-ignore` with three patterns, **When** the operator opens `/repos`, **Then** the card for that repo shows a badge whose count equals 3.
2. **Given** a successfully-indexed repo whose source had no `.codesensei-ignore`, **When** the operator opens `/repos`, **Then** no ignore badge is rendered.
3. **Given** a `.codesensei-ignore` with 35 patterns, **When** the operator inspects the badge tooltip, **Then** the first 20 patterns are listed and the remainder is summarised as `+15 more`.

---

### Edge Cases

- **Empty `.codesensei-ignore`** (0 bytes or only blank/comment lines) — treated identically to "file absent": no extra exclusions, no warning.
- **`.codesensei-ignore` with only invalid lines** (e.g. a line containing only whitespace after the comment-strip step) — those lines are silently dropped; if zero usable patterns remain, treated as empty.
- **Single-file repo whose only file is `.codesensei-ignore`** — indexing proceeds and reports zero source files, same as today's empty-repo behaviour; the ignore file is read but no patterns affect anything (the file itself is not a source file by extension whitelist).
- **`.codesensei-ignore` pattern that matches everything (`*`)** — indexing produces zero source-file chunks; the operator sees `0 chunks` in the success summary. No special-case override (the operator can simply delete the offending line).
- **WebSocket connection succeeds but the worker has already finished by the time the client subscribes** — the stream sends an immediate `init` frame reflecting terminal state (`state: "success"` / `"failed"`) plus a `complete` frame, then closes cleanly.
- **Multiple concurrent SPA tabs open on the same job ID** — both receive independent streams of the same events (the underlying transport is a fan-out, no contention).
- **Worker crashes mid-job** — the stream goes idle (no further events). The client's existing fallback timer kicks in: when no event arrives for > 5 s and no `complete` was seen, the client opens a polling connection to recover state. This behaviour is symmetric to the network-drop fallback.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST read a file named `.codesensei-ignore` from the root of the repository being indexed, when present, before walking the tree for source files.
- **FR-002**: The `.codesensei-ignore` format MUST treat each non-blank, non-`#`-prefixed line as a single glob pattern, trimming trailing whitespace; a trailing `/` MUST mark the pattern as a directory glob; blank lines and lines whose first non-whitespace character is `#` MUST be ignored.
- **FR-003**: A file path being walked MUST be skipped during indexing if it matches any built-in skip rule (existing `skip_dirs` set, file-size cap, supported-extension whitelist) OR any pattern parsed from the `.codesensei-ignore` file; the new file is purely additive (no negation/overrides).
- **FR-004**: The system MUST enforce a hard cap of 200 patterns per `.codesensei-ignore` file; if the file contains more, the system MUST apply the first 200 in source-line order and emit a structured warning event identifying the truncation.
- **FR-005**: The system MUST reject as malformed any `.codesensei-ignore` file larger than 4 KB (apply no patterns, emit a structured warning event) so a runaway file cannot DoS the indexer.
- **FR-006**: The response payload of the indexing API MUST surface the actual list of patterns that were applied to the index run as a new optional field on the repo entity (null when no file existed; a string list otherwise).
- **FR-007**: The system MUST emit progress events for an active asynchronous indexing job over a real-time channel that the SPA can subscribe to, distinct from the existing on-demand polling endpoint.
- **FR-008**: When a client subscribes to the progress channel for an active job, the system MUST send within 1 s an initial event describing the current job state (`files_total`, `files_done`, `chunks_done`, `started_at`, optional `eta_seconds`).
- **FR-009**: While the job runs, the system MUST emit progress events at the natural pace of worker file-completion, coalesced to a maximum of two events per second to bound bandwidth.
- **FR-010**: When the job reaches a terminal state (success, failure, or cancellation), the system MUST emit a final event carrying that terminal state plus, on failure, the error category and message; the channel MUST then close cleanly.
- **FR-011**: When a client subscribes to the progress channel for an unknown or non-existent job ID, the system MUST close the connection with a distinct, machine-readable refusal code, NOT silently appear to succeed.
- **FR-012**: If the real-time channel cannot be established or drops mid-job, the SPA MUST transparently fall back to the existing polling endpoint without surfacing a user-facing error, so the visible progress experience never regresses below today's polling baseline.
- **FR-013**: When the SPA streams progress over the real-time channel, it MUST suspend its polling timer for the same job to avoid duplicated work; when fallback to polling occurs, the timer MUST resume at its existing interval.
- **FR-014**: The `/repos` page MUST render a visible indicator on each repo card whose last index run applied at least one `.codesensei-ignore` pattern, and MUST allow the operator to inspect the parsed pattern list from that page.
- **FR-015**: The Settings page MUST include a static help section documenting the `.codesensei-ignore` file format (location, supported syntax, hard caps).
- **FR-016**: The system MUST NOT persist `.codesensei-ignore` content beyond the lifetime of a single index run; subsequent re-indexes MUST re-read the file from disk, so changes to the file take effect on the next run without any cache to invalidate.

### Key Entities *(include if feature involves data)*

- **`.codesensei-ignore` file**: a plain-text artefact living at the repository root in the source tree. Read once per index run. Its parsed contents are an ordered list of glob patterns plus a flag per pattern indicating whether it is a directory glob (trailing `/`). Not persisted in CodeSensei storage.
- **Ignore pattern list**: the in-memory list of normalised patterns derived from the file. Forwarded into the file-walker and surfaced on the indexing response payload as `codesensei_ignore_patterns`.
- **Progress event**: a real-time message describing a transition in an indexing job. Three kinds: `init` (first frame on subscribe), `progress` (incremental update), `complete` (terminal). Carries integers for file/chunk counts, the current file name, and, on `complete`, optional error metadata. Not persisted.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An operator who adds a single new exclusion line to `.codesensei-ignore` and triggers re-indexing observes the affected files disappear from the indexed chunk count in the next run, with no manual cache clears or container restarts.
- **SC-002**: For an index run on a repository of ≥ 200 source files, the SPA progress card reflects the current `files_done` value within 1 second of the worker emitting it, measured by comparing the SPA-displayed timestamp against the worker's structured-log timestamp.
- **SC-003**: For the same repository, while the live channel is open, the browser issues zero recurring polling requests against the job's status endpoint — verified by reading the network panel for the duration of the index run.
- **SC-004**: If the live channel is forcibly interrupted mid-run (proxy restart, container restart), the SPA recovers its progress display within 5 seconds via fallback to polling, with no visible error toast and no required user action.
- **SC-005**: 100% of `.codesensei-ignore` files that exceed the hard caps (more than 200 patterns OR more than 4 KB) result in a graceful, deterministic degradation (truncate or skip) plus a structured warning event — never an indexing crash or partial schema mismatch.
- **SC-006**: An operator new to the project can correctly author a `.codesensei-ignore` file (1 directory + 1 glob exclusion) using only the in-app Settings help text, without consulting source code or external documentation.

## Assumptions

- The repository being indexed is a local clone produced by the existing indexing pipeline (`POST /api/index`); CodeSensei has filesystem read access to the repo root at index time. The `.codesensei-ignore` file is read from that local clone, not fetched separately.
- The single-user self-hosted threat model from earlier ADRs continues to apply: the real-time progress channel does not need its own auth/CORS surface; same boundary as the rest of the existing API.
- The existing polling endpoint for job status is retained unchanged; new behaviour is additive.
- The reverse-proxy in front of the API (compose's frontend nginx) supports WebSocket upgrade for the API path. No additional infra change is needed.
- The `_mvp_scope.md` priorities for these gaps (FR-4.3 and FR-6.1 marked MUST) remain in force as of 2026-05-21.
