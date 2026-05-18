# Quickstart: UI Tailwind Polish & Findings UX

**Feature**: 007-ui-tailwind-polish
**Phase**: 1 (Design & Contracts)
**Date**: 2026-05-18

Manual smoke walkthrough verifying every spec success criterion. Spend ~15 minutes on this.

---

## Preconditions

- `docker compose up --build -d` is running.
- `/healthz` returns `{"status":"ok"}` (or any non-fatal state).
- At least one repository has been indexed (any from `/repos` — a small public repo works).
- `/settings` has either no PAT (to test `settings_locked`) or a valid bot PAT (to test the happy path).
- The browser is Chromium or Firefox at a viewport ≥ 1024 px.

---

## Step 1 — Theme: OS preference seeding

1. Set the OS theme to dark.
2. Open `http://localhost:5173/` in a private window (clean localStorage).
3. Verify: the page lands in dark mode on **first paint** (no flash of light theme).
4. Set the OS theme to light.
5. Hard-refresh.
6. Verify: the page lands in light mode on first paint.

**Pass when**: theme matches OS in both cases without flicker (FR-002, SC-001).

---

## Step 2 — Theme toggle persistence

1. With OS = light, override via the top-bar toggle to dark.
2. Reload.
3. Navigate to `/review`, `/repos`, `/settings`.
4. Verify: dark mode persists everywhere.
5. Toggle back to "system" (the third option in the cycle).
6. Verify: localStorage no longer carries the `codesensei.theme` key (DevTools → Application → Local storage).

**Pass when**: each step matches (FR-002, SC-001).

---

## Step 3 — Top bar + card layout

1. Open each of `/`, `/review`, `/repos`, `/settings`.
2. Verify: same top bar (logo + four nav links + theme toggle) is present and sticky on scroll.
3. Verify: the active nav link is visually highlighted (underline or filled state).
4. Verify: page content lives inside cards with consistent radius, shadow, and padding.

**Pass when**: visual consistency holds across all four pages (FR-001, FR-005, SC-008).

---

## Step 4 — Keyboard navigation + focus rings

1. On any page, press `Tab` repeatedly from the top.
2. Verify: every interactive element shows a visible focus ring with at least 3:1 contrast in **both** themes.
3. Verify: focus order is predictable (top bar → page content → footer if any).
4. On `/review` after running a review, `Tab` lands on each file-group header; `Enter` toggles open/close.

**Pass when**: no element is reachable yet invisibly focused; toggling works via keyboard (FR-004, SC-003).

---

## Step 5 — Findings UX on /review

1. Submit a review against a real PR with findings of mixed severities across at least 3 files.
2. While the request is in flight: verify a skeleton placeholder is visible (file-group headers + finding rows), **not** a plain "Loading…" string.
3. On success: verify each finding shows a severity pill in the correct colour:
   - critical = red.
   - major = orange.
   - minor = yellow.
   - info = blue.
4. Verify findings are grouped by file. Each group header shows: file path + count + a pill carrying the worst severity in the group.
5. Click a file header — the group collapses smoothly. Click again — it re-expands.
6. For findings whose file has a patch in the response: verify a small code snippet (±3 lines) renders below the body with the target line highlighted.
7. For findings without a patch: verify the body renders cleanly, **no** "patch not found" error appears.

**Pass when**: each substep matches (FR-006…FR-009, SC-002, SC-003, SC-004).

---

## Step 6 — Empty state

1. Submit a review against a PR you expect to be clean (or rerun against a small PR until findings are empty).
2. On success: verify the empty-state block renders the verdict, an icon, and a "No findings" message — in a neutral colour, **not** red.

**Pass when**: empty state is visually unambiguous and not error-coloured (FR-010, SC-005).

---

## Step 7 — Toasts on async actions

1. Submit a review with an invalid PR URL ("not a url"). Verify an **error** toast appears in the bottom-right with the error message; it persists until dismissed.
2. Submit a valid review and click "Post to GitHub". Verify a **success** toast announces the posted review with a link; it auto-dismisses after ~5 s.
3. Trigger a rate-limit response (mock or by hitting GitHub frequently). Verify an **info** toast with the retry-after countdown.

**Pass when**: each category renders, errors persist, success/info auto-dismiss (FR-011).

---

## Step 8 — /repos polish

1. On `/repos`, observe the list of indexed repositories.
2. Verify: each row shows a status badge (`idle` / `indexing` / `ready` / `error`).
3. Click any row.
4. Verify: the row expands in place revealing chunk count + last-error timestamp + message (if any). No navigation occurs.
5. While a repository is mid-indexing, refresh: the expanded panel reflects the new status without manually re-expanding.

**Pass when**: each substep matches (FR-013, SC-006).

---

## Step 9 — /settings test-connection buttons

1. On `/settings`, fill in a known-good OpenAI key and click "Test connection" next to it.
2. Verify: within ~10 s an inline result appears next to the field — green tick + the resolved model id.
3. Replace the key with a bogus value, save, click the test button again.
4. Verify: an inline red diagnosis appears explaining the failure. **Saving was not blocked.**
5. Repeat for the GitHub PAT field:
   - Good PAT: inline success with the GitHub `login`.
   - Bad PAT: inline error with the GitHub status code / message.
   - No PAT configured: inline error explaining the PAT is not set (route returns `settings_locked`).
6. Verify (manually inspect network panel): no `POST` / `PUT` / `PATCH` / `DELETE` is sent during the GitHub probe; only one `GET /api/settings/test/github` and one outbound `GET https://api.github.com/user`.

**Pass when**: each substep matches (FR-014, FR-015, FR-016, SC-007).

---

## Step 10 — Status dots on `/`

1. Open `/`.
2. Verify: each healthz component is shown with a coloured dot (green / yellow / red).
3. Hover or `Tab`-focus a non-green dot. Verify: tooltip carries the component name + status + the last error string.

**Pass when**: dots + tooltips match (FR-012).

---

## Step 11 — Smoke for SC-010 (no schema migration)

1. Run `alembic history` inside the backend container.
2. Verify: no new migration revision was added by this feature.
3. Run `docker compose exec db psql -U codesensei -c "\d+"`.
4. Verify: the table list is unchanged from before 007.
5. Open DevTools → Application → Local Storage on the SPA origin.
6. Verify: at most one new key exists — `codesensei.theme`.

**Pass when**: each substep matches (SC-010).

---

## Step 12 — Constitution audit

- ADR-012 is present in `../_decision_log.md` with **Status: accepted**.
- `_decision_log.md` ADR table row pointing to feature 007 is added.
- No new compose service.
- No new persisted server-side state.
- The PAT never appears in DevTools network bodies or in container `docker compose logs api`.

**Pass when**: every bullet holds.

---

## Failure modes

If any step above fails, the implementation phase is not complete. Open a `## Defect` block in the corresponding task's notes and reopen the relevant `tasks.md` item.
