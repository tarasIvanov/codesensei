# Feature Specification: UX polish — drop Recent row, reformat tokens, write README

**Feature Branch**: `014-ux-polish-and-readme`
**Created**: 2026-05-21
**Status**: Draft
**Input**: User description: "drop Recent: row on /review, reformat token display, write proper README"

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Token usage is shown where it matters (Priority: P1)

The operator does not want to see token + cost numbers on the live `/review` view — what matters there is "the review happened, here are the findings". Tokens are operational telemetry, not a per-review concern. On the `/history/<id>` detail view tokens DO matter — that page is the audit trail. The display there should be a single number (total tokens for the call) plus a cost estimate, not a split of `in / out`. On the `/repos` page, the operator wants to see how many embedding tokens a given indexed repository consumed — this is the "what did this index cost me" answer that today is invisible.

**Why this priority**: directly fixes the dissonance between where token information was placed in feature 012 (everywhere) and where it actually matters (history + repos). Without this fix, `/review` carries visual noise during the most-watched moment, while `/repos` (the only place where embedding spend matters in aggregate) shows nothing.

**Independent Test**: run a review on `/review` and confirm the `tokens · ~$cost` line is gone; open the same run from `/history` and confirm a single combined `1801 tokens · ~$0.0023` line; visit `/repos` and confirm each repo card shows an `Embedding tokens` row with a comma-separated count.

**Acceptance Scenarios**:

1. **Given** the operator submits a PR URL on `/review` and the review succeeds, **When** the result card renders, **Then** no line containing `tokens` or `~$` appears under `provider · X ms`. The `prompt_tokens`/`completion_tokens`/`cost_usd` JSON fields are still present in the network response (frontend simply does not render them).
2. **Given** a historical run with `prompt_tokens=1234` and `completion_tokens=567` and `cost_usd=0.0023`, **When** the operator opens `/history/<id>`, **Then** the header card shows the line `1801 tokens · ~$0.0023` (1234 + 567 = 1801).
3. **Given** a historical run with combined token total but `cost_usd=null` (unknown pricing pair), **When** the detail page renders, **Then** the line shows `N tokens` (no cost segment).
4. **Given** a pre-feature historical run with all three token/cost fields `null`, **When** the detail page renders, **Then** the line shows `tokens N/A`.
5. **Given** an indexed repository whose chunks total `1,234,567` embedding tokens, **When** the operator opens `/repos`, **Then** the per-repo card surfaces an `Embedding tokens` row reading `1,234,567 tokens` (comma-separated thousands, no dollar amount).
6. **Given** a repository indexed with zero chunks, **When** the operator opens `/repos`, **Then** the card shows `Embedding tokens: 0 tokens`.

---

### User Story 2 — Drop the redundant "Recent:" chip strip on /review (Priority: P2)

The `/review` page currently shows a "Recent:" row of clickable chips with previously-submitted PR URLs underneath the URL input. The same recency information is already available via the browser's native autocomplete on the input field (a `<datalist>` populated from the same backing list). The chips are redundant visual noise — they take up screen real estate on the most-trafficked page in the app while offering nothing the autocomplete does not.

**Why this priority**: small QoL cleanup. Lower priority than US1 because no information is lost — the underlying persistence (`codesensei.review.recentPrs`) and the autocomplete affordance stay, only the duplicate chip strip is removed.

**Independent Test**: open `/review` after the change, confirm there is no "Recent:" row of chips below the input, confirm the input still suggests recent PRs when the operator starts typing.

**Acceptance Scenarios**:

1. **Given** the operator has submitted three PR URLs in the past, **When** they open `/review`, **Then** no element on the page reads "Recent:" and no chip row is rendered.
2. **Given** the same three-PR history, **When** the operator clicks into the PR URL input, **Then** the browser-native autocomplete dropdown lists those three URLs (functional parity preserved).
3. **Given** the operator submits a fourth PR URL after the change, **When** they reload `/review`, **Then** the autocomplete dropdown now includes that fourth URL (persistence still writes through).

---

### User Story 3 — Defence-grade README (Priority: P2)

Visitors to the repository land on the README first. Today it is a stub. A thesis defence committee, supervisor, or curious reviewer needs to be able to: (a) understand the project's positioning and goal in two paragraphs, (b) get the stack running with five commands, (c) find the architecture documentation. The README needs to deliver these three answers without burying anything past the fold.

**Why this priority**: not blocking any user flow, but materially important for the defence narrative. A polished README is the first signal of "this project is real" to a non-technical evaluator.

**Independent Test**: a reader who has never seen the project before can, using only `README.md`, (a) describe in one sentence what CodeSensei does and why it exists, (b) get a working local instance up via `docker compose up --build -d`, (c) locate the architectural decision log and the per-feature spec artefacts.

**Acceptance Scenarios**:

1. **Given** a fresh clone of the repository, **When** a reader opens `README.md`, **Then** within the first 30 lines they see (a) the project tagline, (b) the thesis context, and (c) the three named differentiators.
2. **Given** the same fresh clone, **When** the reader follows the "Quick start" section verbatim, **Then** a working API + frontend stack runs on `http://localhost:5173` without dropping to source code.
3. **Given** the same fresh clone, **When** the reader wants to know "why is the LLM adapter shaped this way", **Then** the README points them at `_decision_log.md` and at `specs/<feature>/` for per-feature design.

---

### Edge Cases

- **Historical run with tokens but null cost (Ollama or unknown pair)** — `/history/<id>` shows `N tokens` without the `· ~$X` segment; never shows `~$NaN` or `~$0.0000` on null cost.
- **Repo with zero chunks** — `Embedding tokens: 0 tokens` (numeric zero, not "—").
- **`/repos` page loaded mid-indexing** — the aggregate sum reflects whatever chunks are currently committed. If the indexer is mid-pass (no chunks yet), the row reads `0 tokens`; the next refresh after the chunk-store swap shows the real total.
- **localStorage `codesensei.review.recentPrs` corrupted** — the autocomplete simply skips invalid entries; the chip strip removal does not introduce a regression because there is no chip strip anymore.
- **README rendered on GitHub mobile** — sections collapse correctly; the Quick start `<pre>` blocks wrap or scroll, not overflow.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The `/review` page MUST NOT render any visible line, badge, or chip indicating token counts or cost for a completed review. The underlying JSON response continues to carry those fields.
- **FR-002**: The `/history/<id>` page MUST render exactly one line summarising token consumption for a successful historical run. The line MUST use the format `N tokens · ~$X.XXXX` when both totals are known, `N tokens` when only the token total is known, and `tokens N/A` when token data is absent. `N` is the sum of prompt + completion tokens for the call.
- **FR-003**: The `/repos` page MUST surface, for each indexed repository, a row displaying the total number of embedding tokens consumed across all of its persisted chunks, formatted with thousands separators and the unit "tokens" appended.
- **FR-004**: The `/review` page MUST NOT render a separate "Recent" chip strip or list below the PR URL input. The browser-native autocomplete on the URL input remains the sole surface for recent submissions.
- **FR-005**: The recent-PR persistence mechanism MUST continue to capture each newly-submitted PR URL into the same backing store used by the autocomplete, so subsequent reloads still suggest historical entries.
- **FR-006**: The repository MUST contain a `README.md` at its root whose sections cover, in order: tagline, thesis context, three named differentiators, quick-start instructions, brief architecture overview, feature overview, pointers to deeper documentation, and a short license note.
- **FR-007**: The README quick-start MUST list five or fewer numbered steps that, when followed verbatim against a host with Docker installed, bring up the full stack and render the SPA at the documented URL.
- **FR-008**: The README MUST cite the architectural decision log (`_decision_log.md`) and the per-feature spec directory (`specs/`) as the canonical sources for deeper design rationale.
- **FR-009**: The embedding-token aggregate exposed on `/repos` MUST reflect the current set of persisted chunks for each repo (i.e. it tracks re-index swaps without requiring a separate refresh of the aggregate).
- **FR-010**: No new persistent storage column is introduced for the embedding-token aggregate. The number is computed from existing per-chunk data on read.

### Key Entities *(include if feature involves data)*

- **Historical review token line**: a one-line UI string composed from a historical run's three persisted numeric fields (`prompt_tokens`, `completion_tokens`, `cost_usd`). Not persisted as its own field; rendered.
- **Repo embedding-tokens aggregate**: an integer sum derived at read-time from the existing per-chunk token-count column. Surfaces on the repo entity in the list/detail responses. Not persisted independently of the chunk data.
- **README sections**: ordered set of documentation blocks (tagline, context, differentiators, quick start, architecture, features, docs map, license). Plain Markdown at the repository root.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A reviewer can complete a `/review` submission and read the resulting findings without their eye landing on any per-call cost/token visual element on that page.
- **SC-002**: An operator inspecting an existing run on `/history/<id>` reads exactly one line summarising the token + cost figures for that run, with the total token count as a single number rather than a `in / out` split.
- **SC-003**: For every indexed repository on `/repos`, the embedding-token total surfaced in the UI equals the sum of the persisted per-chunk token counts for that repo (integer arithmetic, no rounding).
- **SC-004**: A fresh reader can stand the project up on a Docker host using only the README quick-start in under 10 minutes wall-clock, starting from `git clone`.
- **SC-005**: Removing the "Recent:" chip strip does not measurably reduce the operator's ability to re-submit a previously-used PR URL — the autocomplete satisfies the same use case in one keystroke.
- **SC-006**: A first-time visitor to the repository who reads the README answers the question "what is this project and why does it exist" correctly without needing to open any other file.

## Assumptions

- The historical-run token fields (`prompt_tokens`, `completion_tokens`, `cost_usd`) introduced by feature 012 remain part of the persisted record and the wire shape; this feature reformats their UI rendering only.
- The per-chunk `token_count` column on `code_chunks` (introduced in feature 005 / ADR-007) remains a count of embedding tokens for the chunk content, never a placeholder, never null.
- The thesis project's bilingual conventions hold: the README is written predominantly in English with a brief Ukrainian-language nod to the thesis context.
- Operators continue to use the browser's native autocomplete affordance on the PR URL input (no exotic browser without `<datalist>` support is in scope).
- No new database column is required; the embedding-token total is a read-time aggregate over existing data.
