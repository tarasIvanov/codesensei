# Data Model: UI Tailwind Polish & Findings UX

**Feature**: 007-ui-tailwind-polish
**Phase**: 1 (Design & Contracts)
**Date**: 2026-05-18

This feature introduces **no** new database schema, no migration, no persisted column. The entities below are wire-only (one new HTTP endpoint) and client-only (in-memory + a single localStorage key).

---

## Server-side wire entities

### `SettingsTestGithubResponse` (200 success)

```python
class SettingsTestGithubResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    ok: Literal[True]
    login: str                    # GitHub login the PAT belongs to
    scopes_hint: str | None       # passthrough of X-GitHub-Token-Type header if present
    elapsed_ms: int               # server-measured roundtrip
```

### Error envelopes

Reuse the existing `ReviewError`-style envelope shape from feature 006 (`backend/src/codesensei/review/errors.py`). The categories the probe can emit are a strict subset of those already in the union; no new category is introduced:

| Category               | HTTP | retryable | Top-level extra        |
| ---------------------- | ---- | --------- | ---------------------- |
| `settings_locked`      | 503  | false     | —                      |
| `github_auth_failed`   | 401  | false     | —                      |
| `github_api_unavailable` | 502 | true      | —                      |
| `github_rate_limited`  | 429  | true      | `retry_after_seconds`  |

The probe never returns `github_pr_not_found`, `github_review_rejected`, or `invalid_input` — those categories are diff-aware and have no meaning for a `GET /user` probe.

---

## Client-side state entities (in-memory)

### `Theme`

```ts
type ThemeChoice = 'light' | 'dark' | 'system';

interface ThemeState {
  // user's selected choice — persisted in localStorage['codesensei.theme'] when not 'system'
  choice: ThemeChoice;
  // the resolved theme actually applied to document.documentElement
  resolved: 'light' | 'dark';
}
```

State transitions (driven by `useTheme().cycle()`):

```text
system → light → dark → system
```

The `resolved` value is derived: when `choice === 'system'`, follow `matchMedia('(prefers-color-scheme: dark)')`; otherwise `resolved = choice`.

Persistence rules:
- `choice = 'system'`: remove the `codesensei.theme` localStorage key (default behaviour).
- `choice = 'light'` or `'dark'`: write the value to `codesensei.theme`.

The pre-Vue inline boot script (in `index.html`) reads the same key and sets `<html data-theme="light|dark">` synchronously before any Vue code runs (FOUC prevention).

---

### `Toast`

```ts
interface Toast {
  id: number;                                    // monotonic per session
  category: 'success' | 'info' | 'error';
  message: string;                               // plain string, sanitised before render
  action?: { label: string; onClick: () => void };
  createdAt: number;                             // ms epoch
}

interface ToastQueue {
  items: Toast[];                                // newest-first
  push(t: Omit<Toast, 'id' | 'createdAt'>): number; // returns id
  dismiss(id: number): void;
}
```

Invariants:
- `items.length ≤ 4` after every `push`.
- If a push would exceed the cap, the **oldest auto-dismissable** toast (`category !== 'error'`) is dropped to make room.
- If the cap is full of `error` toasts, new toasts are dropped silently (console-warn in dev only).
- Auto-dismiss timers are owned by `ToastHost.vue` — when an item disappears from `items`, its timer is cleared.

---

### `FileGroup` (derived on `FindingsList`)

```ts
interface FileGroup {
  file: string | null;                  // null → sentinel group rendered last
  findings: Finding[];                  // sorted by (severity_rank, line_number)
  worstSeverity: 'critical' | 'major' | 'minor' | 'info';
  patch: string | null;                 // unified-diff patch when available
}
```

Derivation rules:
- Iterate `findings` in spec order; first occurrence of each `file` defines the group order.
- `worstSeverity = min(rank(f.severity) for f in findings)` mapped back to the label.
- `patch` is looked up from `patches: Record<string, string>` carried alongside the review result.

State: `expanded: boolean` lives in the `<Collapsible>` component owning each group; default `true`. Resetting the review (new submit) resets all to `true`.

---

### `CodeContextSnippet`

```ts
interface SnippetLine {
  line: number;          // line number on the RHS (post-change)
  text: string;          // raw line text without diff prefix
  side: 'context' | 'add' | 'remove';
  is_target: boolean;    // exactly one entry has is_target = true
}

interface CodeContextSnippet {
  lines: SnippetLine[];  // up to 7 entries: 3 before + target + 3 after, clipped at hunk ends
}
```

Produced by `usePatchContext(patch: string, target_line: number, context = 3)`. Returns `null` when the patch does not cover `target_line`.

---

### `SettingsTestResult` (per-field)

```ts
type SettingsTestResult =
  | { state: 'idle' }
  | { state: 'in_flight' }
  | { state: 'ok'; identity: string; tookMs: number }     // `identity` = OpenAI model id or GitHub login
  | { state: 'error'; message: string; retryable: boolean };
```

Lives in component-local state on `SettingsPage.vue`. Never persisted. Cleared when the user edits the corresponding field.

---

## Relationships

```text
ThemeState  ──→ <html data-theme>   (DOM side-effect, single source)
ToastQueue  ──→ <ToastHost>         (mounted once inside <AppShell>)
ReviewResult.findings  ──→ FileGroup[]  (via FindingsList derivation)
ReviewResult.diff_patches  ──→ patches: Record<string, string>  (when present)
FileGroup.patch + Finding.line  ──→ CodeContextSnippet  (via usePatchContext)
SettingsTestResult  ──→ <SettingsPage>  (per-field local state)
```

No cross-page data flow added; no global store required.

---

## Migration impact

| Layer            | Change         |
| ---------------- | -------------- |
| Database schema  | **none**       |
| Alembic migration| **none**       |
| Compose services | **none**       |
| Server config    | **none**       |
| Client persisted state | exactly one new `localStorage` key: `codesensei.theme` |

Spec **SC-010** is satisfied: no new server-side persisted state introduced.
