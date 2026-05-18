# Implementation Plan: UI Tailwind Polish & Findings UX

**Branch**: `007-ui-tailwind-polish` | **Date**: 2026-05-18 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/007-ui-tailwind-polish/spec.md`

## Summary

Lift the SPA from minimalist hand-rolled CSS to a cohesive design system: shared sticky top bar, card-based layout, light/dark theme with OS-preference seeding + localStorage override, severity-coloured findings pills, collapsible per-file groups on /review, inline ±3-line code-context snippets when the diff carries them, skeleton loaders during in-flight reviews, toast notifications for async actions, status dots + tooltips on `/`, in-place row expansion on `/repos`, and per-field "Test connection" probes on `/settings`. Adopt Tailwind v4 with the CSS-first `@theme` directive as the single styling layer. Keep all primitives (`Card`, `Button`, `Badge`, `Toast`, `Tooltip`, `Skeleton`, `Collapsible`, `StatusDot`) in-tree — no external UI / icon / animation / state-management library. Add exactly one new backend endpoint (`GET /api/settings/test/github`) for the GitHub-PAT probe.

## Technical Context

**Language/Version**: Frontend — TypeScript 5.x / Vue 3.5; Backend — Python 3.12.
**Primary Dependencies**:
- Frontend (existing): Vue 3.5, Vite 6, vue-router 4, `marked` (markdown), `dompurify` (sanitisation).
- Frontend (new): `tailwindcss@^4` + `@tailwindcss/vite` (Vite plugin) + `@tailwindcss/postcss` only if Vite plugin path is unavailable. No `tailwind.config.js` — configuration via CSS `@theme` directive.
- Backend (existing): FastAPI, httpx, structlog. Reuses `posting/client.py`-style `httpx.AsyncClient(timeout=15.0)` pattern for the new GitHub probe.
- Backend (new): nothing — the probe is a single async function + one route handler.
**Storage**: No DB change. No migration. The only persisted state added is one `localStorage` key (`codesensei.theme`) on the client.
**Testing**:
- Backend: `pytest` + `respx` for the new GitHub probe endpoint (mirror `tests/integration/test_review_post_endpoint.py` shape).
- Frontend: manual smoke + `vue-tsc` type check + `npm run build` clean.
**Target Platform**: Self-hosted via `docker compose up`; SPA served by nginx; backend FastAPI on uvicorn — all unchanged.
**Project Type**: Web app (existing `backend/` + `frontend/` split).
**Performance Goals**: First contentful paint unaffected (Tailwind compiles to a single static CSS bundle, tree-shaken by usage); skeleton placeholder must appear within one render tick on /review submit.
**Constraints**:
- No new compose service.
- No new persisted server-side state (no table, no column, no migration).
- No new external runtime dependency beyond Tailwind v4.
- PAT MUST NOT appear in any response body or log line (Constitution IV).
**Scale/Scope**: Single-user developer workstation; all four SPA pages touched; one new backend endpoint.

## Constitution Check

*GATE evaluated against v1.0.1 (ratified 2026-05-11).*

| Principle                                  | Status | Notes                                                                                                                                                                                                                                                                                                                                                                                                  |
| ------------------------------------------ | ------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| I. Spec-Driven Development (NON-NEGOTIABLE) | PASS   | spec.md + plan.md (this file) + tasks.md (next phase) before any production code.                                                                                                                                                                                                                                                                                                                       |
| II. ADR-Driven Architectural Decisions     | PASS   | Adopting Tailwind v4 touches the frontend tooling baseline (`docker-compose.yml` not affected; `frontend/Dockerfile` and `package.json` are). To keep the audit trail consistent with prior ADRs, this feature ships **ADR-012 — Frontend design system on Tailwind v4 + in-tree primitives** as part of the plan. The constitution lists "the web framework" as an ADR trigger; ADR-012 is a soft-trigger record rather than a strict requirement, but is included for discipline. |
| III. Pluggable AI Provider Boundaries      | N/A    | Feature does not touch LLM or embedding adapters.                                                                                                                                                                                                                                                                                                                                                       |
| IV. Privacy & Credentials Discipline       | PASS   | New endpoint `GET /api/settings/test/github` reads the encrypted PAT from the Settings store, calls `GET https://api.github.com/user` (read-only), and returns only `{ok: bool, login: str?, error: str?}`. The PAT MUST NOT be echoed in the response body. The probe MUST NOT make a write call. structlog event omits the PAT. Spec FR-015 + FR-020 reinforce this.                                  |
| V. Single-Command Deployment                | PASS   | Tailwind is a build-time dep declared in `frontend/package.json` and consumed inside `frontend/Dockerfile`. No new compose service; no host-side install step.                                                                                                                                                                                                                                          |

**Verdict**: GATE PASS. Proceed to Phase 0.

## Project Structure

### Documentation (this feature)

```text
specs/007-ui-tailwind-polish/
├── plan.md                       # This file (/speckit-plan command output)
├── spec.md                       # Already in place from /speckit-specify
├── research.md                   # Phase 0 output (this command)
├── data-model.md                 # Phase 1 output (this command)
├── quickstart.md                 # Phase 1 output (this command)
├── contracts/
│   ├── settings_test_github.md   # Backend contract for GET /api/settings/test/github
│   ├── design_tokens.md          # CSS variables and Tailwind theme contract
│   └── ui_primitives.md          # In-tree primitive component contracts
├── checklists/
│   └── requirements.md           # Spec-quality checklist (already PASS)
└── tasks.md                      # Phase 2 output (/speckit-tasks command — not created here)
```

### Source Code (repository root)

```text
backend/
└── src/codesensei/
    └── settings_store/
        ├── api.py                # existing — extend with GET /test/github
        ├── github_probe.py       # NEW: async probe wrapping httpx call to /user
        └── ...
    └── (no schema/model touches)

frontend/
├── package.json                  # add tailwindcss + @tailwindcss/vite dev deps
├── vite.config.ts                # register @tailwindcss/vite
├── postcss.config.js             # DELETE if present and replaced by Vite plugin
├── src/
│   ├── styles/
│   │   ├── tokens.css            # NEW: @theme block — palette, typography, spacing
│   │   └── globals.css           # NEW: Tailwind preflight + base resets + dark-mode toggle
│   ├── main.ts                   # import globals.css; install theme + toast providers
│   ├── components/
│   │   ├── AppShell.vue          # NEW: sticky top bar + nav + theme toggle + <RouterView>
│   │   ├── primitives/
│   │   │   ├── Card.vue          # NEW
│   │   │   ├── Button.vue        # NEW
│   │   │   ├── Badge.vue         # NEW
│   │   │   ├── StatusDot.vue     # NEW
│   │   │   ├── Tooltip.vue       # NEW
│   │   │   ├── Skeleton.vue      # NEW
│   │   │   ├── Collapsible.vue   # NEW
│   │   │   └── ToastHost.vue     # NEW: renders the toast queue
│   │   ├── PostToGitHubPanel.vue # existing — restyle, surface results via toast
│   │   └── findings/
│   │       ├── FindingsList.vue          # NEW: groups by file, uses Collapsible
│   │       ├── FindingRow.vue            # NEW: severity pill + body + suggestion
│   │       ├── SeverityPill.vue          # NEW: single source of severity colour mapping
│   │       └── CodeContextSnippet.vue    # NEW: ±3-line snippet from diff patch
│   ├── composables/
│   │   ├── useTheme.ts           # NEW: provides theme ref + toggle + persistence
│   │   ├── useToast.ts           # NEW: provides toast queue + push/dismiss
│   │   └── usePatchContext.ts    # NEW: extracts ±3 lines around target line from patch
│   ├── pages/
│   │   ├── HomePage.vue          # restyle to use AppShell + Card + StatusDot
│   │   ├── ReviewPage.vue        # restyle + Skeleton + EmptyState + new FindingsList
│   │   ├── ReposPage.vue         # restyle + Collapsible row-expand + Badge
│   │   └── SettingsPage.vue      # restyle + Test-connection controls
│   └── api/
│       ├── settings.ts           # extend with testGithub() typed call
│       └── (existing modules)
└── tests/                        # vue-tsc only; no Vitest/Playwright in scope
```

**Structure Decision**: Web-app split. Backend gets one new module (`settings_store/github_probe.py`) and one new route on the existing `settings_store/api.py`. Frontend gets a new `styles/` folder for Tailwind tokens + base, a new `primitives/` folder for reusable components, a new `findings/` folder for /review-specific rendering, three new composables (theme, toast, patch-context), and replaces the existing page-level CSS with Tailwind utility classes inside each page. No new top-level frontend folder is introduced; the existing `components/` / `composables/` / `pages/` shape is honoured.

## Complexity Tracking

No violations of Constitution Check require justification. The plan stays inside the technology baseline: Vue 3 + Vite + TypeScript on the frontend; FastAPI + httpx on the backend. The single new external dependency is `tailwindcss@^4` (CSS framework), which is the **only** approved category per spec FR-019. ADR-012 is recorded for discipline, not because the change crosses a hard ADR trigger.

| Violation | Why Needed | Simpler Alternative Rejected Because |
| --------- | ---------- | ----------------------------------- |
| _none_    | _n/a_      | _n/a_                                |
