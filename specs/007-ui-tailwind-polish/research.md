# Research: UI Tailwind Polish & Findings UX

**Feature**: 007-ui-tailwind-polish
**Phase**: 0 (Outline & Research)
**Date**: 2026-05-18

All entries follow the contract: **Decision / Rationale / Alternatives considered**. Each entry resolves an unknown that would otherwise have been flagged as `NEEDS CLARIFICATION` in `plan.md` Technical Context.

---

## R1 — Tailwind v4 integration path

**Decision**: Install `tailwindcss@^4` together with `@tailwindcss/vite` and register the plugin in `vite.config.ts`. Do **not** add a `postcss.config.js`. Configure the design system entirely in `src/styles/tokens.css` via Tailwind v4's `@theme` directive.

**Rationale**: Tailwind v4 ships with a first-party Vite plugin that compiles utility classes during dev/build with no PostCSS pipeline wiring required. Since the project already runs Vite 6, the plugin is the path of least integration risk. The CSS-first `@theme` block keeps all design tokens (palette, typography scale, spacing, radii, shadows) in one file readable by a non-Vue audience (thesis evaluator) without learning a JS config DSL.

**Alternatives considered**:
- PostCSS + `@tailwindcss/postcss` plugin: more verbose, requires `postcss.config.js`, equivalent in output. Rejected for ceremony.
- Tailwind v3 + `tailwind.config.ts`: stable, well-documented, but binds the design system to a JS file; v4's CSS-first approach is cleaner for thesis readability and is the current LTS direction.

---

## R2 — CSS-first `@theme` token shape

**Decision**: One `@theme` block in `src/styles/tokens.css` defines:
- Neutral palette `--color-neutral-{0,50,100,200,300,400,500,600,700,800,900,950}` (Tailwind v4 default-friendly scale).
- Brand palette `--color-brand-{50..900}` for primary accents.
- Semantic colours `--color-success-*`, `--color-warning-*`, `--color-danger-*`, `--color-info-*`.
- Severity-pill background + foreground pairs `--color-severity-critical-{bg,fg}`, `--color-severity-major-{bg,fg}`, `--color-severity-minor-{bg,fg}`, `--color-severity-info-{bg,fg}` — single source of truth for FR-006.
- Typography scale `--font-size-xs..--font-size-2xl` aligned with Tailwind defaults; no custom font family — system stack.
- Radius scale `--radius-sm`, `--radius-md`, `--radius-lg`.
- Shadow scale `--shadow-sm`, `--shadow-md`.
- Spacing inherits Tailwind defaults — not redefined.

Dark-mode tokens live in a `:root[data-theme="dark"]` block that overrides the same variable names. Tailwind v4 supports this pattern natively because tokens compile to CSS custom properties.

**Rationale**: One file, one block, every other component reads variables. Adding a new severity is a single-file change (spec Assumption). Dark mode is a single override block instead of class-prefixed `dark:` utilities everywhere.

**Alternatives considered**:
- Per-page tokens: rejected because spec FR-003 requires a shared scale.
- Class-prefixed dark-mode utilities (`dark:bg-*`): rejected because it doubles the markup and requires explicit `dark:` on every utility; the `data-theme` swap is one place to maintain.

---

## R3 — Theme persistence & FOUC prevention

**Decision**:
- `useTheme` composable owns a `theme: 'light' | 'dark' | 'system'` ref.
- On `app.ts` boot, a small inline `<script>` block in `index.html` (NOT inside the Vue tree) runs **before** Vite's main module loads and sets `document.documentElement.dataset.theme` from `localStorage['codesensei.theme']` if present, otherwise from `window.matchMedia('(prefers-color-scheme: dark)').matches`. This avoids the "flash of wrong theme" FOUC on first paint.
- The composable subscribes to `matchMedia` change events when `theme === 'system'` so the SPA updates live if the OS theme changes mid-session.
- Toggle action: cycles `system → light → dark → system`; writes the chosen value (or removes the key when back to `system`) to `localStorage`.

**Rationale**: The pre-Vue inline script is the only way to set the correct theme before the first paint in a Vite-built SPA. The cycle order keeps the toggle a single button.

**Alternatives considered**:
- Server-side cookie: would work but requires a backend round-trip and adds a state surface; spec FR-017 explicitly forbids server-side personalisation.
- Always-system + remove toggle: rejected — UX spec requires explicit override.

---

## R4 — Theme & toast distribution: `provide/inject` vs Pinia

**Decision**: Use Vue's `provide` / `inject` exposing two composables (`useTheme`, `useToast`) plus a `<ToastHost>` mounted once inside `AppShell`. No Pinia, no Vuex.

**Rationale**: The shared state is two refs (current theme, toast queue). Pinia is overkill at this scale and would be a new runtime dependency forbidden by spec FR-019. `provide/inject` is the Vue-idiomatic minimum.

**Alternatives considered**:
- Pinia: rejected (dependency forbidden + overkill).
- Module-scoped reactive globals (`reactive({...})` exported from a module): rejected because they bypass Vue's app boundary and break tree-shaking; provide/inject keeps lifecycle aligned with the app.

---

## R5 — Toast UX: stacking, positioning, auto-dismiss, max-queue

**Decision**:
- Position: bottom-right of the viewport, stacked top-to-bottom (newest on top).
- Auto-dismiss: success + info after 5000 ms; error toasts persist until the user dismisses.
- Max visible: 4 toasts. Beyond that, the oldest auto-dismissable toast is removed to make room (errors are never auto-evicted; if all 4 slots hold errors, new toasts are dropped silently with a console warning during development).
- Each toast carries `id`, `category: 'success' | 'info' | 'error'`, `message: string`, optional `action: { label, handler }`.
- Implementation uses a `<Transition>` group with Tailwind `transition-*` utilities for fade + slide. No animation library.

**Rationale**: Bottom-right is the industry default and stays out of the page's top-anchored content. The cap prevents runaway stacks. Persistent errors are required by spec FR-011.

**Alternatives considered**:
- Top-centre placement: rejected — fights with the sticky top bar.
- Per-toast inline buttons (no toast at all): rejected — spec FR-011 mandates toasts over inline alerts.

---

## R6 — Severity colour palette (fixed)

**Decision**:

| Severity | Light bg / fg                       | Dark bg / fg                          | Tailwind palette anchor |
| -------- | ----------------------------------- | ------------------------------------- | ----------------------- |
| critical | `red-100` / `red-800`               | `red-900/40` / `red-200`              | red                     |
| major    | `orange-100` / `orange-800`         | `orange-900/40` / `orange-200`        | orange                  |
| minor    | `amber-100` / `amber-800`           | `amber-900/40` / `amber-100`          | amber (Tailwind yellow) |
| info     | `sky-100` / `sky-800`               | `sky-900/40` / `sky-200`              | sky                     |

Encoded as CSS variables under R2. Contrast for both modes verified against WCAG 4.5:1 minimum on `text` vs `background` pairs.

**Rationale**: Tailwind's named palettes already meet AA in both shades. Pinning specific shades to severities ensures one place to update.

**Alternatives considered**:
- Hue-only mapping with single-tone backgrounds (`bg-red-500`): rejected — fails AA on small text.

---

## R7 — Code-context snippet extraction from patch

**Decision**: A `usePatchContext` composable accepts:
- `patch: string` — unified-diff patch of one file (already available in the review response when the diff carries it).
- `target_line: number` — the post-review line number the finding refers to.
- `context: number = 3` — half-window size.

It walks the patch hunks, tracks the running RHS (new-side) line counter, collects 3 lines before and 3 lines after the target, and returns either `{lines: Array<{line: number, text: string, side: 'context'|'add'|'remove', is_target: bool}>}` or `null` when the patch does not contain `target_line`. The composable does **not** mutate the patch.

**Rationale**: The patch payload is already in scope (review response carries it for PR-driven reviews). Re-parsing on the client avoids backend changes. The Map-walk algorithm is O(n) over the patch text.

**Alternatives considered**:
- Send the raw file contents from the backend: rejected — would require a new fetch path and is wasteful when the patch already carries the relevant lines.
- Use an off-the-shelf diff parser library: rejected — adds a runtime dep; the algorithm is ~40 lines.

---

## R8 — Backend probe endpoint: `GET /api/settings/test/github`

**Decision**:
- New route: `GET /api/settings/test/github` registered on the existing `settings_store/api.py` router (kept under `/api`).
- Implementation in a new module `backend/src/codesensei/settings_store/github_probe.py`.
- Reads the PAT through `await get_setting("GITHUB_TOKEN")` (same path used by `posting/service.py`).
- Calls `GET https://api.github.com/user` with `httpx.AsyncClient(timeout=15.0)` and headers `Authorization: token <PAT>`, `Accept: application/vnd.github+json`, `X-GitHub-Api-Version: 2022-11-28`.
- Response 200:

  ```json
  {"ok": true, "login": "codesensei-bot", "scopes_hint": "fine-grained"}
  ```

  The `scopes_hint` field surfaces the value of the `X-GitHub-Token-Type` header verbatim when present (allows the operator to tell whether the PAT is fine-grained or classic). On `OAuth` etc. it is passed through unchanged.
- Error envelopes (uniform with `posting/`):
  - 503 / `settings_locked` — no PAT configured.
  - 401 / `github_auth_failed` — GitHub responded 401 or 403.
  - 502 / `github_api_unavailable` — 5xx / timeout / network. `retryable=true`.
  - 429 / `github_rate_limited` — `retryable=true`, top-level `retry_after_seconds`.
- structlog event: `github_probe` with fields `ok, login, elapsed_ms, status_code`. **The PAT MUST NOT appear in the log line or in the response body.**
- Pydantic v2 response model: `extra="ignore"`. Request body: none (no payload).

**Rationale**: One read endpoint, mirrors existing patterns from `posting/`, reuses Settings store reads. No write to GitHub. PAT confidentiality preserved.

**Alternatives considered**:
- POST with PAT in body: rejected — would mean accepting an unencrypted PAT over the wire from the SPA, which violates Constitution IV.
- Reuse `/healthz/providers`: rejected — `healthz` covers LLM + embedding providers, not GitHub auth; mixing them muddies status semantics.

---

## R9 — In-tree primitive set (Card, Button, Badge, etc.)

**Decision**: Seven primitives, all in `src/components/primitives/`, all single-file Vue components, all typed.

| Component       | Public props                                                                  | Slot(s)         | Notes                                                                                                  |
| --------------- | ----------------------------------------------------------------------------- | --------------- | ------------------------------------------------------------------------------------------------------ |
| `Card`          | `padded?: boolean = true`, `flush?: boolean = false`                          | default         | One semantic container with consistent radius + shadow + bg. `flush` removes inner padding.            |
| `Button`        | `variant: 'primary'\|'secondary'\|'ghost'\|'danger' = 'primary'`, `size: 'sm'\|'md' = 'md'`, `loading?: boolean`, `disabled?: boolean`, `as?: 'button'\|'a' = 'button'` | default         | Adds focus-visible ring; `loading` shows inline spinner SVG and disables interaction.                  |
| `Badge`         | `tone: 'neutral'\|'success'\|'warning'\|'danger'\|'info' = 'neutral'`         | default         | Used for repo status (idle / indexing / ready / error), settings test results, etc.                    |
| `StatusDot`     | `state: 'ok'\|'degraded'\|'error'`, `label: string`, `error?: string\|null`   | none            | Renders a colour dot + accessible name; opens `Tooltip` on hover/focus carrying `label` and `error`.   |
| `Tooltip`       | `text: string`, `placement: 'top'\|'bottom' = 'top'`                          | default         | CSS-only tooltip using `:focus-visible` + `:hover`; no popper.js.                                       |
| `Skeleton`      | `lines?: number = 1`, `class?: string`                                         | none            | Renders a shimmer block via Tailwind `animate-pulse`.                                                   |
| `Collapsible`   | `defaultOpen?: boolean = true`                                                | `header`, `body` | Renders a button-shaped header that toggles the body; `aria-expanded` synced; keyboard `Enter`/`Space`. |

**Rationale**: Minimum needed surface, each component fits in <80 LoC, no external dep, fully styleable via Tailwind utilities passed through `class` props on consumers.

**Alternatives considered**:
- Headless UI Vue: ~30 kB gzipped runtime — rejected by spec FR-019.
- PrimeVue / Vuetify: heavy, opinionated themes — rejected.
- Radix Vue / Reka UI: TypeScript-heavy, would dictate prop shapes — rejected; we want full ownership.

---

## R10 — Findings rendering algorithm (group + sort)

**Decision**:
- `FindingsList.vue` accepts `findings: Finding[]` plus optional `patches: Record<string, string>` (file → unified-diff patch).
- Groups by `finding.file` (preserving first-seen order of files). Findings without a `file` go into a sentinel group rendered last titled "Without file location".
- Within a group, findings sort by `(severity_rank, line_number)` where `severity_rank = {critical:0, major:1, minor:2, info:3}`; null line numbers go last.
- Worst severity per group is the minimum `severity_rank` across the group's findings.
- Each `FindingRow` renders: severity pill + body + optional `_Suggestion_:` block + optional `<CodeContextSnippet>` (only when `patches[file]` exists AND `usePatchContext(patches[file], line)` returns non-null).

**Rationale**: Stable, deterministic order; the worst-severity badge on the group header lets a reviewer drill into the riskiest files first.

**Alternatives considered**:
- Server-side grouping: rejected — backend remains presentation-agnostic.
- Tree by directory: rejected — over-engineered for thesis scope; flat per-file list is enough.

---

## R11 — Accessibility scope

**Decision**:
- Visible focus rings on every interactive element via Tailwind `focus-visible:ring-2 focus-visible:ring-brand-500` (and a darker accent in dark mode).
- Severity pill text contrast verified ≥ 4.5:1 against pill background in both modes (R6 already aligned).
- Keyboard support on `Collapsible`: `Enter` and `Space` toggle the header; `Tab` enters/exits the body naturally.
- `Tooltip` is reachable via `Tab` (the parent element is focusable when the tooltip carries information not redundant with surrounding text — i.e. on `StatusDot`).
- Theme toggle and toasts have `aria-label` and `role="status"` / `role="alert"` respectively (`role="alert"` for `error` category only).
- Out of scope: full ARIA landmark audit, screen-reader optimisation, RTL layout, prefers-reduced-motion (we use only short Tailwind transitions; no large motion).

**Rationale**: Scoped to what the spec demanded (FR-004) without ballooning into a full a11y rewrite.

**Alternatives considered**:
- Full WCAG AA conformance audit: rejected for thesis scope.

---

## R12 — ADR-012 acceptance

**Decision**: ADR-012 — *Frontend design system on Tailwind v4 + in-tree primitives* — is recorded in `../_decision_log.md` with **Status: accepted**, **Date: 2026-05-18**, alternatives (UI-component library options) tabulated. Notes line points to this plan + future PR.

**Rationale**: keeps an unbroken ADR audit trail consistent with prior features and gives the thesis defence an artefact for "why Tailwind, why no UI lib".

**Alternatives considered**: skipping the ADR — rejected, see plan §Constitution Check.

---

## Closeout

All `NEEDS CLARIFICATION` markers from `plan.md` Technical Context are resolved. Phase 0 is complete.
