---
description: "Tasks for feature 007 — UI Tailwind polish & findings UX"
---

# Tasks: UI Tailwind Polish & Findings UX

**Input**: Design documents from `/specs/007-ui-tailwind-polish/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Backend gets `pytest` + `respx` coverage for the single new probe endpoint (`GET /api/settings/test/github`) — mirrors the testing shape used by feature 006's posting endpoint. Frontend has **no** Vitest / Playwright in scope; correctness is validated via `vue-tsc` + `npm run build` clean + manual smoke per `quickstart.md`.

**Organization**: Tasks are grouped by user story. US1 (Tailwind baseline + cohesive shell) is the foundation; US2 (findings UX) and US3 (/repos + /settings + / polish) layer on top. US2 and US3 do not depend on each other and can be implemented in either order once US1 is in place.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

Repo is a web-app per `plan.md`: `backend/src/codesensei/`, `frontend/src/`, tests under `backend/tests/{unit,integration}/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Wire Tailwind v4 into the Vite build, create the shared CSS-token file, and add the FOUC-prevention inline script. No primitives or components yet — only the foundations every subsequent page-level task assumes.

- [X] T001 Add `tailwindcss@^4` and `@tailwindcss/vite` to `frontend/package.json` (under `devDependencies`) and run `npm install` so `frontend/package-lock.json` is regenerated. Do **not** add `postcss.config.js`.
- [X] T002 Register the Tailwind v4 Vite plugin in `frontend/vite.config.ts`: `import tailwindcss from '@tailwindcss/vite'` and append `tailwindcss()` to the `plugins` array.
- [X] T003 [P] Create `frontend/src/styles/tokens.css` containing the `@theme { … }` block from `contracts/design_tokens.md` (light-mode tokens) plus the `:root[data-theme="dark"] { … }` override block (dark-mode tokens). Severity-pill colour pairs (`--color-severity-{critical,major,minor,info}-{bg,fg}`) MUST be exactly as in the contract — they are the single source of truth for FR-006.
- [X] T004 [P] Create `frontend/src/styles/globals.css`: `@import "tailwindcss";` followed by minimal base resets (body `bg-[var(--color-bg-page)] text-[var(--color-text)] font-sans antialiased`, anchor reset to inherit color) and a small set of semantic helper utilities allowed by `design_tokens.md` (`.text-muted { color: var(--color-text-muted); }` and similar, max five names).
- [X] T005 Add the FOUC-prevention inline `<script>` block from `contracts/design_tokens.md` to `frontend/index.html` immediately **above** the `<script type="module" src="/src/main.ts"></script>` tag. The block reads `localStorage["codesensei.theme"]` (or `prefers-color-scheme`) and writes `document.documentElement.dataset.theme` synchronously.
- [X] T006 Update `frontend/src/main.ts` to import `./styles/globals.css` and `./styles/tokens.css` **before** mounting the Vue app, so utility classes resolve and tokens are available on first paint.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Build the in-tree primitives, the theme and toast composables, the new backend probe endpoint, and the typed frontend wrapper for it. Every user story below depends on these.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

### Frontend primitives (parallel — each in its own file)

- [X] T007 [P] Create `frontend/src/components/primitives/Card.vue` per `contracts/ui_primitives.md` §1 (props `padded`, `flush`, `title`, `subtitle`; slots `default`, `header`, `footer`).
- [X] T008 [P] Create `frontend/src/components/primitives/Button.vue` per `contracts/ui_primitives.md` §2 (props `variant`, `size`, `loading`, `disabled`, `as`, `href`; emits click; renders `<button>` or `<a>`; focus-visible ring on `--color-brand-500`).
- [X] T009 [P] Create `frontend/src/components/primitives/Badge.vue` per `contracts/ui_primitives.md` §3 (prop `tone` ∈ `neutral|success|warning|danger|info`; reads `--color-*-bg/fg` tokens; inline-block pill shape).
- [X] T010 [P] Create `frontend/src/components/primitives/StatusDot.vue` per `contracts/ui_primitives.md` §4 (props `state` ∈ `ok|degraded|error`, `label`, `error?`; wraps a `<Tooltip>` for the error string).
- [X] T011 [P] Create `frontend/src/components/primitives/Tooltip.vue` per `contracts/ui_primitives.md` §5 (props `text`, `placement`; CSS-only show on `:hover` / `:focus-visible`; no portal).
- [X] T012 [P] Create `frontend/src/components/primitives/Skeleton.vue` per `contracts/ui_primitives.md` §6 (prop `lines`; renders shimmer rows using Tailwind `animate-pulse`).
- [X] T013 [P] Create `frontend/src/components/primitives/Collapsible.vue` per `contracts/ui_primitives.md` §7 (prop `defaultOpen`; emit `toggle`; slots `header`, `body`; `aria-expanded` synced; `Enter`/`Space` toggle; uses `<Transition>` with Tailwind `transition-[max-height]`).

### Frontend composables

- [X] T014 [P] Create `frontend/src/composables/useTheme.ts` per `data-model.md` "Theme" section: exports `provideTheme()` (called once in `main.ts`) and `useTheme()` returning `{choice, resolved, cycle(), set(choice)}`. Subscribes to `matchMedia('(prefers-color-scheme: dark)')` when `choice === 'system'`. Writes `document.documentElement.dataset.theme` and `localStorage["codesensei.theme"]` on `set`. Cycle order: `system → light → dark → system`.
- [X] T015 [P] Create `frontend/src/composables/useToast.ts` per `data-model.md` "Toast" section: exports `provideToastQueue()` and `useToast()` returning `{items, push(t), dismiss(id)}`. Enforces `items.length ≤ 4` invariant; on overflow drops the oldest non-error toast; if all 4 are errors, drops the new toast (console-warn in dev only).
- [X] T016 [P] Create `frontend/src/components/primitives/ToastHost.vue` per `contracts/ui_primitives.md` §8: reads queue from `useToast()`, renders fixed bottom-right stack with `<Transition>` enter/leave, owns the auto-dismiss timers (5 s for `success`/`info`, none for `error`). `role="alert"` for errors, `role="status"` otherwise.

### Shared shell

- [X] T017 Create `frontend/src/components/AppShell.vue`: sticky top bar with the product name, four `<RouterLink>`s (Status / Review / Repos / Settings) with active-link styling, the theme-toggle `<Button variant="ghost" size="sm">` calling `useTheme().cycle()` and showing a sun / moon / monitor inline SVG depending on `choice`, and a `<main>` that renders `<RouterView />` inside `<Card>` containers shaped by individual pages. Mount `<ToastHost />` once at the end of the layout. This component is the single owner of the top bar — pages MUST NOT render their own.
- [X] T018 Update `frontend/src/App.vue` to render `<AppShell />` instead of the previous top-level layout. Update `frontend/src/main.ts` to call `provideTheme()` and `provideToastQueue()` on the app instance before `app.mount('#app')`.

### Backend probe endpoint

- [X] T019 Create `backend/src/codesensei/settings_store/github_probe.py`: async function `async def probe_github(token: str) -> dict` that runs `httpx.AsyncClient(timeout=15.0)`, calls `GET https://api.github.com/user` with headers per `contracts/settings_test_github.md`, returns `{"login": <str>, "scopes_hint": <str|None>}` on 200, raises `ReviewError(GITHUB_AUTH_FAILED, ...)` on 401/403, `ReviewError(GITHUB_API_UNAVAILABLE, retryable=True, ...)` on 5xx / `httpx.TimeoutException` / `httpx.NetworkError`, and `ReviewError(GITHUB_RATE_LIMITED, retryable=True, retry_after_seconds=<parsed>, ...)` on 429. Do NOT echo the PAT in any return value, log line, or exception message.
- [X] T020 Add route `GET /test/github` on the existing settings_store router in `backend/src/codesensei/settings_store/api.py`. Handler: read PAT via `await get_setting("GITHUB_TOKEN")`; if `None` raise `ReviewError(SETTINGS_LOCKED, "GitHub PAT is not configured. Open Settings to add one.")`. Else call `probe_github(token)`, measure `elapsed_ms`, return `SettingsTestGithubResponse(ok=True, login=..., scopes_hint=..., elapsed_ms=...)`. Wrap in `try/finally` that always emits one `structlog.info("github_probe", ok=<bool>, login=<str|None>, status_code=<int|None>, elapsed_ms=<int>, category=<str|None>)`.
- [X] T021 Add `SettingsTestGithubResponse` pydantic model to `backend/src/codesensei/settings_store/api.py` (or a new `settings_store/schema.py` if the file feels crowded): `model_config = ConfigDict(extra="ignore")`, fields `ok: Literal[True]`, `login: str`, `scopes_hint: str | None = None`, `elapsed_ms: int`. Per `contracts/settings_test_github.md`, no request body model is needed.

### Frontend typed wrapper

- [X] T022 [P] Extend `frontend/src/api/settings.ts` with `testGithub(): Promise<TestGithubResult>` and a typed `TestGithubError(category, message, retryable, retryAfterSeconds?)` exception per `contracts/settings_test_github.md` — mirror the parser shape already in `frontend/src/api/posting.ts` so top-level `retry_after_seconds` is honoured.

**Checkpoint**: All primitives, composables, the shared shell, and the backend probe endpoint are in place. User stories can now begin. After this phase the SPA already boots through `<AppShell />` and the theme toggle works — but pages still render their existing content unchanged.

---

## Phase 3: User Story 1 — Cohesive design-system shell across all pages (Priority: P1) 🎯 MVP

**Goal**: Every page on the SPA (`/`, `/review`, `/repos`, `/settings`) renders inside the shared `<AppShell />` with card-based layout, consistent typography and spacing, light/dark theming, and keyboard-reachable focus rings.

**Independent Test**: Run through `quickstart.md` steps 1–4 (theme OS-seeding, toggle persistence, top-bar consistency, keyboard navigation). All four pages display the same top bar, same card containers, same typography rhythm, and visible focus rings in both themes.

### Implementation for User Story 1

- [X] T023 [US1] Refactor `frontend/src/pages/HomePage.vue` to render its content inside `<Card>` containers (one card per healthz section) and remove all `<style scoped>` blocks; styling lives purely on Tailwind utility classes. Replace ad-hoc `<button>`/`<a>` elements with `<Button>`. The dot/badge implementations stay placeholder until US3 — for now just render text status with the right `text-*` semantic token colour.
- [X] T024 [US1] Refactor `frontend/src/pages/ReviewPage.vue` to render inside `<Card>` containers (one card for the input form, one for the result). Remove `<style scoped>` blocks; styling lives on Tailwind utility classes. The findings list still uses the pre-existing rendering (no severity pill yet) — that is replaced in US2.
- [X] T025 [US1] Refactor `frontend/src/pages/ReposPage.vue` to use `<Card>` containers for the add-repo form and the existing repos list. Remove `<style scoped>`. Status text uses semantic token colours; the row-expand and `Badge`-based status come in US3.
- [X] T026 [US1] Refactor `frontend/src/pages/SettingsPage.vue` to use `<Card>` containers for each provider group (LLM provider card, Embedding provider card, GitHub token card). Replace `<input>` borders with semantic-token `border-[var(--color-border)] rounded-[var(--radius-sm)] bg-[var(--color-bg-elevated)]`. Replace `<button>` save controls with `<Button variant="primary">`. The "Test connection" buttons come in US3.
- [X] T027 [US1] Refactor `frontend/src/components/PostToGitHubPanel.vue` to render inside a `<Card>` and use `<Button>` for the primary action. Remove the inline alert banner — its messages will flow through `useToast()` in US2; for now keep its current state machine but wire the success / error states to toasts at the call sites (replace the alert <div> with `useToast().push(...)`).
- [X] T028 [US1] Run `npx vue-tsc --noEmit` from `frontend/` and ensure zero type errors after the refactors above. Fix any prop-type drift introduced by the new primitives. Run `npm run build` and ensure the output bundle builds clean.

**Checkpoint**: Quickstart steps 1–4 pass. Every page wears the same shell + cards; theme works; keyboard reaches every interactive element.

---

## Phase 4: User Story 2 — Readable, scannable findings on /review (Priority: P2)

**Goal**: The /review page becomes scannable — severity pills, per-file grouping with worst-severity badges, ±3-line code-context snippets when the patch is available, skeleton loaders during in-flight requests, an empty-state for zero-findings reviews, and toast notifications for all async actions.

**Independent Test**: Run through `quickstart.md` steps 5–7. With a review carrying mixed severities across multiple files: severity pills colour-coded correctly, groups collapsible per file, code snippets visible where the patch contains the target line, skeleton placeholder during in-flight, empty-state on zero findings, toasts for submit / post-to-GitHub / errors.

### Implementation for User Story 2

- [X] T029 [P] [US2] Create `frontend/src/components/findings/SeverityPill.vue` per `contracts/ui_primitives.md` §9. Reads `--color-severity-<severity>-{bg,fg}` tokens; renders label `severity.toUpperCase()` inside a rounded-full pill. This component is the **only** code path that maps severity to colour; no other component may hard-code severity colours.
- [X] T030 [P] [US2] Create `frontend/src/composables/usePatchContext.ts` implementing `usePatchContext(patch: string, target_line: number, context: number = 3): CodeContextSnippet | null` per `data-model.md` "CodeContextSnippet" section. Walks the unified-diff patch's `@@ -A,B +C,D @@` hunks, tracks the running RHS line counter, returns `{lines: SnippetLine[]}` with `is_target` marker or `null` when the patch does not cover `target_line`.
- [X] T031 [P] [US2] Create `frontend/src/components/findings/CodeContextSnippet.vue` consuming the composable output: renders each `SnippetLine` with `font-mono text-xs`, line-number gutter, target line visually highlighted (`bg-[var(--color-warning-bg)]` or similar). When the composable returns `null` the component renders nothing (no placeholder, no error).
- [X] T032 [P] [US2] Create `frontend/src/components/findings/FindingRow.vue`: props `{finding, patch?: string | null}`. Renders one row with a `<SeverityPill>` + the finding's message + optional `_Suggestion_:` block + an inline `<CodeContextSnippet>` when `patch && finding.line`. No file path here — that lives on the group header (T033).
- [X] T033 [US2] Create `frontend/src/components/findings/FindingsList.vue`: props `{findings: Finding[], patches?: Record<string, string>}`. Derives `FileGroup[]` per `data-model.md` (preserves first-seen file order; sentinel "Without file location" group last; sort within group by `(severity_rank, line)`; computes `worstSeverity` per group). Each group is a `<Collapsible defaultOpen>` whose header shows `<file path> · <count> · <SeverityPill worstSeverity>` and whose body iterates `<FindingRow>` for each finding in the group. Empty `findings` array → renders nothing (the page-level empty-state in T034 owns that case).
- [X] T034 [US2] Update `frontend/src/pages/ReviewPage.vue` to: (1) replace the existing findings rendering with `<FindingsList :findings :patches />` where `patches` is read from the review-response payload when present; (2) render `<Skeleton :lines="6" />` (or a small composed skeleton mirroring the file-group shape) inside the result `<Card>` while the request is in flight; (3) when the result returns `findings.length === 0`, render an empty-state block showing the verdict + a neutral icon + "No findings" message — styled with neutral tokens, NOT red/amber; (4) push toasts via `useToast()` on submit success/error and on retry, mirroring the success/error/info categories.
- [X] T035 [US2] Update `frontend/src/components/PostToGitHubPanel.vue` (already restyled to a `<Card>` in T027) to push a `success` toast linking to the posted review's `html_url` on success, and an `error` toast (with retry action for retryable errors) on failure. Remove any leftover inline banner. The single-use post lock stays in place — toast does not replace the lock.
- [X] T036 [US2] `vue-tsc --noEmit` clean + `npm run build` clean. Visual smoke per quickstart §5–§7 (severity colours, group collapse, code snippets, skeleton, empty-state, toasts).

**Checkpoint**: Quickstart §5–§7 pass. /review is now scannable.

---

## Phase 5: User Story 3 — Polish on /, /repos and /settings (Priority: P3)

**Goal**: `/` shows status dots with tooltips; `/repos` has in-place row-expand revealing chunk count + last error timestamp; `/settings` has per-field "Test connection" buttons that probe upstream without mutating state.

**Independent Test**: Run through `quickstart.md` steps 8–10. Status dots colour-coded with hover tooltips; repos rows expand to show chunk count + last error; settings test buttons probe and surface inline result without blocking save.

### Tests for User Story 3 — backend probe endpoint ⚠️ (write FIRST, must FAIL before T039 wires the route)

- [X] T037 [P] [US3] Create `backend/tests/unit/test_settings_test_github.py` covering `probe_github()` directly: respx-mocked happy path (200 + body `{"login":"codesensei-bot"}` + header `X-GitHub-Token-Type: fine-grained`) → returns `{"login":"codesensei-bot","scopes_hint":"fine-grained"}`; 401 → `ReviewError(GITHUB_AUTH_FAILED)` with message containing `"401"`; 403 → same; 500 → `GITHUB_API_UNAVAILABLE, retryable=True`; timeout → `GITHUB_API_UNAVAILABLE, retryable=True`; 429 with `Retry-After: 75` → `GITHUB_RATE_LIMITED, retryable=True, retry_after_seconds=75`. Assert that no test case includes the PAT in the raised exception message or in any returned dict.
- [X] T038 [P] [US3] Create `backend/tests/integration/test_settings_test_github_endpoint.py`: ASGI TestClient hits `GET /api/settings/test/github`. Cases: (a) happy path — `respx` returns 200, response shape matches `SettingsTestGithubResponse`, `login == "codesensei-bot"`; (b) no PAT — `monkeypatch` `get_setting` to return `None` → HTTP 503 + `error.category == "settings_locked"`; (c) 401 from GitHub → HTTP 401 + `error.category == "github_auth_failed"`; (d) 429 with `Retry-After: 90` → HTTP 429 + top-level `retry_after_seconds == 90`; (e) 5xx → HTTP 502 + `retryable=true`; (f) the response body never contains the PAT value `"fake-token"` (assert substring absence).

### Implementation for User Story 3

- [X] T039 [US3] Verify the route added in T020 is included by `backend/src/codesensei/main.py`'s settings router mount (the settings router is already mounted by feature 004 — adding a route on the same router auto-wires). If a stale `include_router` mount needs reordering, do it here. Run T037 + T038 → all green.
- [X] T040 [US3] Update `frontend/src/pages/HomePage.vue` to render each healthz component using `<StatusDot :state :label :error />`. Map upstream component status string → `ok|degraded|error` (`"ok"` → `ok`, anything error-like → `error`, otherwise `degraded`). The tooltip surfaces the component name + status + any `error` field from the healthz payload.
- [X] T041 [US3] Update `frontend/src/pages/ReposPage.vue`:
   1. Each repo row is wrapped in a `<Collapsible>` whose header is the existing row (repo URL/path + status + actions) and whose body shows: chunk count (read from `repo.chunk_count` if present in the API response, else "—"), `repo.last_error_at` timestamp + `repo.last_error` message inside a `<Badge tone="danger">` if non-null, and the row's existing actions if any.
   2. Replace the existing status text with `<Badge :tone>` where `tone` derives from `repo.status` (`idle` → neutral, `indexing` → info, `ready` → success, `error` → danger).
   3. The expanded panel re-renders reactively when `repo.status` changes (because it reads from the same reactive state — no manual collapse/expand cycle required).
- [X] T042 [US3] Update `frontend/src/pages/SettingsPage.vue` to add a `<Button variant="secondary" size="sm">Test connection</Button>` next to the OpenAI API key field and next to the GitHub PAT field. Each button:
   1. Has component-local state of shape `SettingsTestResult` (`idle | in_flight | ok | error`).
   2. Sets state to `in_flight` on click, calls the corresponding API wrapper (`testOpenai()` already exists, `testGithub()` from T022 is new), then sets state to `ok` (carrying `identity` and `tookMs`) or `error` (carrying `message` and `retryable`).
   3. Renders the result inline next to the field: green chip with the identity on success, red chip with the message on error; the chip uses `<Badge tone="success">` / `<Badge tone="danger">` plus a small inline icon.
   4. Disables the button while `state === 'in_flight'` (use `<Button :loading>`).
   5. Result MUST NOT prevent the user from clicking the existing "Save" button regardless of outcome.
   6. The result chip resets to `idle` whenever the user edits the corresponding input value.
- [X] T043 [US3] `vue-tsc --noEmit` clean + `npm run build` clean. Backend `pytest -q` → all green (245 + new probe tests). Manual smoke per quickstart §8–§10.

**Checkpoint**: Quickstart §8–§10 pass. /, /repos, /settings now wear their polish.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Verification of the whole feature against the spec's Success Criteria and Constitution gates. Updates to `README.md` and `CLAUDE.md` to reflect what landed.

- [X] T044 Run all of `quickstart.md` §1–§12 manually on a fresh `docker compose up`. Each step must pass without notes. Step 11 (no migration / no new table) must be explicitly inspected and recorded in this task's notes.
- [X] T045 Run `npx vue-tsc --noEmit` from `frontend/` and `npm run build` — both must be clean.
- [X] T046 Run backend `pytest -q` from `backend/` — all tests green (the existing 245 + the new ~8 added by T037/T038).
- [X] T047 Run `ruff check backend/` and `ruff format --check backend/` — both must be clean.
- [X] T048 Update `README.md`:
   - Mention dark mode + Tailwind design system on the existing `/` description bullet.
   - Append a one-line pointer to `specs/007-ui-tailwind-polish/quickstart.md` next to the existing 003 / 005 / 006 quickstart links.
   - The "Status: pre-MVP" line stays but can be updated to reflect feature 007's polish if useful.
- [X] T049 Verify `_decision_log.md` already contains ADR-012 (added during `/speckit-plan`) with `Status: accepted` and a Notes line pointing at feature 007. If the Notes line predates implementation completion, append "Shipped 2026-MM-DD" after the commit lands.
- [X] T050 Sanity-check that no inline hex colour was introduced in any `.vue` file outside of `tokens.css`. Run `rg "#[0-9a-fA-F]{3,8}" frontend/src --type vue` and confirm zero matches (a small allowlist of design-system documentation comments is acceptable but unlikely to be needed).

**Checkpoint**: Feature 007 is feature-complete. Ready for commit and PR.

---

## Dependency Graph

```text
T001 ─┬─→ T002 ─→ T006 ─┬─→ T017 ─→ T018 ─┬─→ T023..T028 (US1 pages)
      │                  │                │
      └─→ T003 ───────────┘                ├─→ T029..T036 (US2)
                                           │
T004 ─→ T006                               └─→ T040..T043 (US3 frontend)
T005 ─→ T017
T007..T013 (primitives, parallel) ─→ T017
T014 (useTheme) ─→ T017
T015 (useToast) ─→ T016 (ToastHost) ─→ T017
T019 (probe fn) ─→ T020 (route) ─→ T021 (response schema) ─→ T022 (FE wrapper) ─→ T042
T037..T038 (probe tests) ─→ T039 (wire) → T042
T044..T050 (polish) depend on every preceding phase.
```

## Parallel Execution Examples

- **Phase 1**: T003 and T004 can run in parallel (different CSS files).
- **Phase 2 primitives**: T007..T013 are all `[P]` — each in its own file under `frontend/src/components/primitives/`.
- **Phase 2 composables**: T014 and T015 are independent files.
- **Phase 4 (US2)**: T029, T030, T031, T032 can run in parallel (separate files); T033 depends on T029 + T032; T034 depends on T033; T035 depends on T034 (toast pattern reused).
- **Phase 5 (US3) tests**: T037 and T038 are different files and can run in parallel before T039.

## Implementation Strategy

- **MVP cut** = US1 only (Phases 1 + 2 + 3 + the polish gate of Phase 6). After this cut the SPA already wears the shared shell, light/dark theming, focus rings, and card-based layout — the visible quality jump alone is shippable.
- **Layered increments**: US2 layers findings UX on top of MVP. US3 layers operator polish on top. Either layer can ship first after MVP.
- **Single commit boundary**: per the project's commit-granularity rule (memory), the entire feature commits at the end of Phase 6 as one commit on branch `007-ui-tailwind-polish`, then opens one PR to `main`.
- **Test discipline**: Phase 5 follows the project's TDD-for-critical-paths convention for the new probe endpoint — write the failing tests in T037 + T038 **before** wiring T039.
- **Forbidden during implementation**: no new external runtime dependency beyond `tailwindcss@^4` and `@tailwindcss/vite` (spec FR-019); no UI / icon / animation / state-management library; no inline hex colours outside `tokens.css`; no `dark:`-prefixed Tailwind utilities (dark mode is handled at the token level via `data-theme`).

---

## Format Validation

All 50 tasks above use the strict checklist format `- [ ] [TaskID] [P?] [Story?] Description with file path`. Setup (T001–T006), Foundational (T007–T022), and Polish (T044–T050) phases carry no `[Story]` label. User-story phases (T023–T028 = US1; T029–T036 = US2; T037–T043 = US3) carry the `[USx]` label. File paths are explicit for every task.
