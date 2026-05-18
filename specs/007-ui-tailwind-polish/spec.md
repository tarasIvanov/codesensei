# Feature Specification: UI Tailwind Polish & Findings UX

**Feature Branch**: `007-ui-tailwind-polish`
**Created**: 2026-05-18
**Status**: Draft
**Input**: User description: "007 UI polish — Tailwind design system + findings UX across all 4 SPA pages (/, /review, /repos, /settings). Lifts the SPA from minimalist hand-rolled CSS to a cohesive design system: dark mode, severity-coloured badges, collapsible findings groups, inline code-context preview, toast notifications, skeleton loaders, repos row-expand, settings test-connection."

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Cohesive design-system shell across all pages (Priority: P1)

As any user of CodeSensei (reviewer, repo-indexer, operator), I land on a SPA that looks and behaves as a single product on every page, with a sticky top bar, a card-based layout, a system-controlled light/dark theme, and predictable focus and keyboard behaviour, so the tool feels production-quality instead of a developer scaffold.

**Why this priority**: The SPA today is minimalist hand-rolled CSS with inconsistent spacing, no theming, and no shared visual vocabulary. Without a unified shell the rest of the polish work (Stories 2 and 3) has nothing to attach to. This story is the foundation; Stories 2 and 3 only add value once the shell exists.

**Independent Test**: Open each of the four pages (`/`, `/review`, `/repos`, `/settings`) in light and in dark mode. Verify that every page shares the same top bar (logo + nav links + theme toggle), uses the same card container, uses the same typography scale, uses the same spacing, and that all interactive elements (links, buttons, inputs, radios) show a visible focus outline on keyboard navigation. Verify that toggling the theme persists across reloads and respects the OS preference on first visit.

**Acceptance Scenarios**:

1. **Given** the SPA is open on any of the four pages, **When** the user looks at the page, **Then** a sticky top bar is visible carrying the product name, four navigation links labelled Status / Review / Repos / Settings, and a theme toggle; the active link is visually highlighted.
2. **Given** the user has never visited CodeSensei before, **When** the SPA first loads, **Then** the theme is selected from the operating system's `prefers-color-scheme`; selecting the alternate theme via the toggle MUST persist across page reloads and route navigation.
3. **Given** the user is on any page, **When** they navigate with `Tab` only, **Then** every interactive element (every link, every button, every input, every radio, every collapsible header) shows a visible focus outline that meets a minimum 3:1 contrast ratio against the page background.
4. **Given** the user is on any page, **When** they look at the page content, **Then** the page is laid out inside card containers with consistent padding, a consistent border-radius, and a consistent shadow, and the page header shows a title + optional subtitle in the same layout on every page.
5. **Given** the user looks at any heading, body text, secondary text or badge on any page, **When** comparing two pages, **Then** the same role of text uses the same size, weight and colour across both pages (typography scale is shared).

---

### User Story 2 — Readable, scannable findings on /review (Priority: P2)

As a reviewer reading a generated review, I can quickly understand the severity distribution, group findings by file, see the code context near each finding without leaving the page, and get clear feedback while the review is loading or when there are no findings.

**Why this priority**: The current /review page renders findings as flat text, with no severity colour cue, no grouping, and no surrounding code. This is the page the reviewer actually spends time on; making it scannable is the highest-impact UX win after the shell. Independent of Story 3 — even without `/repos` and `/settings` polish, this story delivers value on its own.

**Independent Test**: Generate a review against a real PR with findings of mixed severities. Verify that each finding shows a severity pill in the correct colour, that findings are grouped by file with an expandable header showing the file path + finding count + worst severity, that clicking the header collapses or expands the group, that each finding shows a small code snippet around its line when the diff carries the context, that during the in-flight review a skeleton placeholder is shown (not a plain "Loading…" string), and that when a review returns zero findings the page shows a friendly empty-state instead of a blank list.

**Acceptance Scenarios**:

1. **Given** a review result is displayed, **When** the user looks at any finding, **Then** the finding's severity is shown as a coloured pill with a fixed colour mapping (critical = red, major = orange, minor = yellow, info = blue) and the same colour mapping is used wherever else severity appears on the page.
2. **Given** a review result with findings spread across multiple files, **When** the findings render, **Then** they are grouped under a per-file header, each header shows the file path, the count of findings in that file, and a pill carrying the worst severity in that group; groups are expanded by default.
3. **Given** the user clicks a file group header, **When** the click resolves, **Then** the group collapses (or expands again if already collapsed) with a smooth transition and keyboard focus remains on the header.
4. **Given** a finding has a file path and line number AND the originating diff carries the surrounding code, **When** the finding renders, **Then** a small code snippet of the file at that line ±3 lines is rendered immediately below the finding's body, with the target line visually highlighted.
5. **Given** a review has been submitted and the request is still in flight, **When** the user looks at the page, **Then** a skeleton placeholder is shown in the shape of the eventual findings list (file-group headers + finding rows), not a plain text spinner.
6. **Given** a review completes with zero findings, **When** the result renders, **Then** an empty-state block is shown carrying the verdict, an icon, and a short "No findings" message; the empty-state does NOT look like an error.
7. **Given** the reviewer takes any action that resolves asynchronously (submit a review, post to GitHub, retry a failed post), **When** the action resolves, **Then** the resolution is communicated via a toast notification, not via an inline alert mid-page; success and informational toasts auto-dismiss after 5 seconds, error toasts persist until the user dismisses them.

---

### User Story 3 — Polish on /, /repos and /settings (Priority: P3)

As an operator I want the supporting pages (status dashboard, repo manager, settings) to expose more information at a glance and let me sanity-check my credentials without leaving the page.

**Why this priority**: These pages are visited less often than /review but they are where the operator configures the system. The improvements here are operational quality-of-life, not core flow; if the shell (Story 1) and the findings UX (Story 2) are done, the product is already shippable. This story polishes the supporting surfaces.

**Independent Test**: Open `/` while one provider is configured and another is missing — verify the status dots are colour-coded with a tooltip carrying the last-error string for any non-green component. Open `/repos`, click on a row — verify the row expands in place showing the indexing status, the chunk count, and the timestamp of the last error if any. Open `/settings`, fill in the OpenAI key and the GitHub PAT, click the per-field "Test connection" button — verify a non-blocking inline result appears next to each field (a green tick + remote identity, or a red cross + diagnosis) within a few seconds; failure does not prevent saving.

**Acceptance Scenarios**:

1. **Given** the user opens `/`, **When** the healthz components render, **Then** each component is shown with a coloured status dot (green = ok, yellow = degraded, red = error) and on hover or focus the dot reveals a tooltip carrying the component name, the status, and the last error string if any.
2. **Given** the user opens `/repos` with at least one indexed repository, **When** they click on a repository row, **Then** the row expands in place to reveal: the indexing status as a coloured badge (idle / indexing / ready / error), the total chunk count for that repository, and the timestamp + message of the most recent indexing error if one is recorded.
3. **Given** the user opens `/settings` and has filled in an OpenAI key, **When** they click "Test connection" next to the OpenAI key field, **Then** within a few seconds an inline result appears next to that field — a green confirmation carrying the resolved model identity on success, a red diagnosis carrying the underlying error message on failure. The result must NOT block the user from saving settings.
4. **Given** the user opens `/settings` and has filled in a GitHub PAT, **When** they click "Test connection" next to the GitHub PAT field, **Then** within a few seconds an inline result appears carrying either the GitHub login the PAT belongs to (success) or the reason the call failed (failure); the test must NOT post anything, MUST NOT make a write call, and MUST NOT mutate settings state.

---

### Edge Cases

- A user switches between light and dark mode while findings are rendered — colour transitions must be smooth and severity pills must remain legible in both modes (contrast ≥ 4.5:1 for pill text against pill background).
- A finding has a file path but no line number — the code-context preview is omitted, but the finding still renders with its severity pill and message, grouped under its file.
- A finding has a file path that does not appear in the originating diff — the file group still renders, but the code-context preview is omitted gracefully (no "patch not found" error surfaced).
- A toast notification queue grows large — toasts stack vertically with a sensible cap; once the cap is reached the oldest toasts drop off so new toasts always render.
- The `/settings` test-connection button is clicked twice in quick succession — the second click is ignored while the first call is in flight (the button is disabled with an inline spinner).
- The user is on a viewport narrower than the design target (< 1024 px) — the SPA does not promise a polished layout; the layout may degrade gracefully but `<1024 px` is explicitly out of scope for this feature.
- An older browser without `prefers-color-scheme` support — the SPA falls back to the light theme by default.
- The user has disabled JavaScript or has a brand-new visit with no `localStorage` entry — the SPA picks the OS preference on first paint without flashing the wrong theme.
- A finding's body contains very long unbroken strings (URL or stack trace) — the layout MUST wrap or scroll inside the card, never overflow the page.
- A repository row in `/repos` is expanded and the indexer status changes in the background — the row's expanded panel reflects the new status without requiring a manual collapse/expand cycle.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The SPA MUST share a single top-bar component across all four routes, carrying the product name, four navigation links (Status / Review / Repos / Settings), a theme toggle, and visual indication of the active route. The top bar MUST remain visible while the page scrolls.
- **FR-002**: The SPA MUST support two themes, light and dark. On first visit the theme MUST be derived from the operating-system colour-scheme preference. The user MUST be able to override the theme via a toggle in the top bar, and the override MUST persist across page reloads and across route navigations.
- **FR-003**: The SPA MUST use a single shared typography scale, spacing scale, palette and border-radius scale across all four pages. Adding a new page MUST be possible without redefining these design tokens.
- **FR-004**: Every interactive element (links, buttons, inputs, radios, checkboxes, collapsible-group headers, toast dismiss controls, theme toggle) MUST show a visible focus outline that is keyboard-reachable and meets WCAG 2.1 contrast AA (3:1) against the page background in both themes.
- **FR-005**: The SPA MUST render the page body inside card containers with consistent padding, border-radius, and shadow across all four pages. Adjacent cards MUST follow the same vertical spacing rhythm.
- **FR-006**: The /review page MUST render each finding's severity as a coloured pill, using a fixed mapping: critical = red, major = orange, minor = yellow, info = blue. The same mapping MUST be used anywhere else severity is shown.
- **FR-007**: The /review page MUST group findings by file path. Each group MUST show a clickable header carrying the file path, the count of findings in that file, and a pill carrying the worst severity in that group. Groups MUST be expanded by default and collapsible by clicking the header.
- **FR-008**: Where a finding has a file path AND a line number AND the originating diff carries the file's patch content, the /review page MUST render a small code-context snippet of ±3 lines around the line under the finding's body, with the target line visually highlighted. Where any of these are missing, the snippet MUST be omitted silently — no placeholder, no error.
- **FR-009**: The /review page MUST show a skeleton-shaped placeholder while a review is in flight, shaped like the eventual findings list (file-group headers and finding rows). Plain text spinners and bare "Loading…" strings MUST NOT appear on /review.
- **FR-010**: The /review page MUST show an empty-state block with the verdict, an icon, and a short "No findings" message when a completed review carries zero findings. The empty-state MUST be visually distinct from error states.
- **FR-011**: Asynchronous-action feedback (review submission, post-to-GitHub, retry, settings save) MUST be delivered as toast notifications, not inline alerts. Success and informational toasts MUST auto-dismiss after 5 seconds. Error toasts MUST persist until the user dismisses them. Toasts MUST stack vertically with a maximum visible count; older toasts MUST be dropped when the cap is exceeded.
- **FR-012**: The `/` page MUST render each healthz component with a coloured status dot — green for ok, yellow for degraded, red for error — and a hover/focus tooltip carrying the component name, current status, and the last error string when present.
- **FR-013**: The `/repos` page MUST allow the user to expand a repository row in place, revealing the indexing status as a coloured badge, the total chunk count for the repository, and the timestamp + message of the most recent indexing error if any is recorded. The expanded panel MUST update without requiring manual collapse/expand if the underlying status changes.
- **FR-014**: The `/settings` page MUST offer a "Test connection" control next to the OpenAI key field and next to the GitHub PAT field. The control MUST make a read-only probe against the corresponding upstream and show the result inline next to the field. The result MUST NOT prevent the user from saving settings, regardless of outcome.
- **FR-015**: The settings GitHub-PAT test MUST NOT make any write call to GitHub; it MUST NOT post a comment, create a review, create a branch, or mutate any GitHub resource. Only a read endpoint identifying the PAT's owner is allowed.
- **FR-016**: The settings test-connection controls MUST be idempotent and self-throttling: clicking the same button twice while a probe is in flight MUST result in only one upstream call.
- **FR-017**: The SPA MUST work as a pure single-page client. Theme selection, route navigation, and all polish features added by this feature MUST function with the existing API surface; no new persisted user-visible state MUST be introduced beyond the theme preference in `localStorage`.
- **FR-018**: The SPA MUST be functional and readable for the desktop viewport range (≥ 1024 px width). Smaller viewports MUST degrade gracefully (no broken layout, no off-screen content) but are not required to look polished.
- **FR-019**: The SPA MUST NOT introduce any new external runtime dependency beyond a CSS framework. No UI-component library, no icon library, no animation library, no state-management library MUST be added.
- **FR-020**: All Markdown rendered inside findings, toasts, and other dynamic surfaces MUST continue to be rendered with the same safety guarantees the SPA already enforces; this feature MUST NOT widen the set of allowed HTML tags or attributes.

### Key Entities

- **Theme preference**: a user-controlled choice between `light`, `dark`, or "follow OS"; persisted in the browser's local storage under a single key; does not exist server-side.
- **Severity pill**: a visual rendering of a finding's severity with a fixed colour and label, reused wherever a severity appears.
- **File group**: a logical grouping of findings sharing the same file path, materialised as a collapsible card with a header (file path + finding count + worst severity).
- **Code-context snippet**: a small render of the file's patch content around a finding's line, with the target line highlighted; only present when the underlying diff carries the patch.
- **Toast notification**: an ephemeral feedback element delivered out of the page flow, with a category (success / info / error), a body string, an optional action (e.g. retry), and auto-dismiss behaviour determined by category.
- **Settings test result**: an inline, ephemeral state next to a settings field, summarising the outcome of a "Test connection" probe (status, remote identity on success, diagnostic message on failure); never persisted.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A first-time visitor lands on a page whose theme matches their OS preference. Switching the theme via the toggle persists across a full-page reload and across navigation to all other routes — verified by smoke on each of the four pages.
- **SC-002**: On /review with at least one finding of each severity, a reviewer can identify the severity of every finding without reading the body — verified by visual inspection that the colour pill alone is sufficient to identify severity.
- **SC-003**: On /review with findings spread across at least three files, a reviewer can collapse all groups except one and then re-expand the target group with a single click each — keyboard navigation between group headers works with `Tab` and toggling works with `Enter` / `Space`.
- **SC-004**: A review request that takes longer than 1 second to resolve never shows a blank page nor a plain text "Loading…" — the skeleton placeholder is visible throughout.
- **SC-005**: For a review with zero findings the empty-state is visually unambiguous: it is rendered in a neutral colour (NOT red, NOT amber) and carries the verdict explicitly.
- **SC-006**: The `/repos` page reveals chunk-count and last-error details in-place without requiring the user to navigate away from the page — verified by clicking on a row of an existing repository.
- **SC-007**: Both settings test-connection buttons return a result within 10 seconds for the happy path and within 30 seconds for the error path (e.g. invalid token). Neither call mutates any state.
- **SC-008**: After this feature, the product offers exactly one toast queue, one theme model, one severity colour palette, and one set of card / button / pill / collapsible primitives — i.e. the codebase does not carry two competing implementations of any of these primitives.
- **SC-009**: The SPA renders correctly in both Chrome and Firefox at viewport widths ≥ 1024 px (manual smoke). Below 1024 px the layout does not break (no horizontal scrollbars on the page body, no off-canvas controls) but is not required to be visually polished.
- **SC-010**: The feature introduces no new persisted server-side state (no migration, no new table, no new column), and at most one new local-storage key (the theme preference).

## Assumptions

- The feature targets desktop viewports (≥ 1024 px). A small portion of mobile-shaped traffic is acceptable as "best-effort, ungaranteed".
- The thesis evaluator and any future demo will be performed in a modern Chromium-family or Firefox browser with `prefers-color-scheme` and `localStorage` available.
- The existing API endpoints (`/healthz`, `/review`, `/repos`, `/settings`) continue to return the same shapes; this feature does not redesign the data model. The single backend addition this feature requires is a read-only "test GitHub PAT" endpoint (calling a GitHub read endpoint with the configured PAT and returning the resolved login or an error) — and only if it is not already provided by the existing healthz/providers surface.
- The user already has the means to configure their credentials via `/settings` (feature 004). This feature does not change credential storage, encryption, or any persistence guarantees around credentials.
- All severity values currently emitted by the review pipeline are one of `critical`, `major`, `minor`, `info`. If the pipeline ever introduces a new severity, the design system documents the colour mapping in one place so adding a new entry is a single-file change.
- Accessibility scope is bounded to keyboard reachability + visible focus rings + WCAG AA contrast. Full screen-reader optimisation and ARIA landmark audit is out of scope.

## Out of Scope

- Mobile-first layout, responsive breakpoints below 1024 px.
- Internationalisation (i18n) or any non-English UI string.
- A Storybook / component documentation site.
- Animation framework (e.g. Framer-Motion-style transitions); only the CSS framework's native `transition-*` utilities are used.
- An icon library; any icons are inline SVG embedded in the relevant component.
- End-to-end browser tests (Playwright / Cypress); manual smoke is sufficient for this iteration.
- Server-driven personalisation (per-user theme persistence, per-user UI flags) — theme lives only in browser local storage.
- A redesign of any backend response shape; this feature is presentation-only with one optional read-only endpoint addition for the GitHub-PAT test.
- Any change to how secrets are stored, encrypted, or transmitted.
- A switch to a UI-component library (PrimeVue, Headless UI, Radix, Reka UI, etc.) — the feature explicitly chooses to keep primitives in-tree.
