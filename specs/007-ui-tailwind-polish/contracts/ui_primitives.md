# Contract: In-Tree UI Primitives

**Feature**: 007-ui-tailwind-polish
**Status**: Draft
**Date**: 2026-05-18

The SPA owns its primitives. No external UI library is added (spec FR-019). Every primitive below lives in `src/components/primitives/` as a single-file Vue component (≤ ~120 LoC), reads colours only from the design tokens (R6 + design_tokens.md), and is consumed by pages via `<script setup>` imports.

---

## 1. `Card.vue`

**Purpose**: One semantic container with consistent radius, shadow and background. Replaces every `<div class="panel">`-style ad hoc wrapper today on the four pages.

```ts
defineProps<{
  padded?: boolean;   // default: true
  flush?: boolean;    // default: false — removes inner padding
  title?: string;     // optional inline header
  subtitle?: string;
}>();
```

Slots: `default`, `header` (override), `footer`.

Visual contract:
- `bg-[var(--color-bg-card)]` + `border border-[var(--color-border)]` + `rounded-[var(--radius-md)]` + `shadow-[var(--shadow-sm)]`.
- Padded: `p-6`; flush: `p-0`; header: `px-6 py-4 border-b`.

---

## 2. `Button.vue`

**Purpose**: Single button styled across variants and sizes. Used everywhere actions live (submit, post-to-github, theme toggle, test-connection, etc.).

```ts
defineProps<{
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger';   // default 'primary'
  size?: 'sm' | 'md';                                       // default 'md'
  loading?: boolean;
  disabled?: boolean;
  as?: 'button' | 'a';                                      // default 'button'
  href?: string;                                            // required when as === 'a'
}>();
```

Behavioural contract:
- Renders a `<button>` by default or an `<a>` when `as === 'a'`. Both share the same look.
- `loading` shows an inline spinner SVG, disables clicks, sets `aria-busy="true"`.
- `disabled` greys the button to `opacity-50` and disables clicks (`pointer-events-none` plus `disabled` attribute on `<button>`).
- Focus: `focus-visible:ring-2 focus-visible:ring-[var(--color-brand-500)] focus-visible:ring-offset-2`.

Variant matrix:

| Variant     | Light bg / fg                                  | Hover                                  | Notes                                          |
| ----------- | ---------------------------------------------- | -------------------------------------- | ---------------------------------------------- |
| `primary`   | `bg-brand-600 text-white`                      | `hover:bg-brand-700`                   | Main CTA — "Post to GitHub", "Submit review".  |
| `secondary` | `bg-neutral-100 text-neutral-800`              | `hover:bg-neutral-200`                 | Secondary actions — "Test connection", "Cancel".|
| `ghost`     | transparent + `text-neutral-700` (light)       | `hover:bg-neutral-100`                 | Theme toggle, collapsible headers.             |
| `danger`    | `bg-danger-bg text-danger-fg`                  | matches danger-bg darker variant       | Destructive actions only.                      |

Sizes: `sm` = `px-2.5 py-1 text-sm`; `md` = `px-4 py-2 text-md`.

---

## 3. `Badge.vue`

```ts
defineProps<{
  tone?: 'neutral' | 'success' | 'warning' | 'danger' | 'info';   // default 'neutral'
}>();
```

Visual contract:
- Inline-block, `rounded-[var(--radius-sm)]`, `px-2 py-0.5 text-xs font-medium`.
- Tone determines `bg` + `fg` via the semantic tokens (`--color-success-bg/fg`, etc.).
- `neutral` tone uses `--color-neutral-100` / `--color-neutral-700`.

Used by:
- `/repos` row badges: `idle` → neutral, `indexing` → info, `ready` → success, `error` → danger.
- Settings test-result chips: success / error tone.
- Wherever a one-word status appears.

---

## 4. `StatusDot.vue`

```ts
defineProps<{
  state: 'ok' | 'degraded' | 'error';
  label: string;        // accessible name and tooltip title
  error?: string | null;
}>();
```

Visual contract:
- `inline-flex items-center gap-2`.
- A 8 px circle: `ok` = `--color-success-fg`, `degraded` = `--color-warning-fg`, `error` = `--color-danger-fg`.
- The label is rendered next to the dot in small muted text.
- Hovering or focusing the wrapper opens a `Tooltip` carrying `label` + state name + the `error` string (if any).

Used by:
- `/` healthz components (one `StatusDot` per check).

---

## 5. `Tooltip.vue`

```ts
defineProps<{
  text: string;                          // required
  placement?: 'top' | 'bottom';          // default 'top'
}>();
```

Slot: `default` — the trigger element. The tooltip body is rendered as a sibling `<span>` and shown via CSS on `:hover` and `:focus-visible`. No popper.js, no portal. The trigger MUST be focusable (a `<button>`, `<a>`, or has `tabindex="0"`).

Visual contract:
- Pop-up: `bg-[var(--color-neutral-800)] text-[var(--color-neutral-50)] rounded-[var(--radius-sm)] px-2 py-1 text-xs shadow-[var(--shadow-md)]`.
- Inverted in dark mode (`bg-[var(--color-neutral-100)] text-[var(--color-neutral-900)]`).
- Positioned 6 px above (or below) the trigger via absolute positioning inside the relative-wrapped trigger.

---

## 6. `Skeleton.vue`

```ts
defineProps<{
  lines?: number;     // default 1 — number of stacked skeleton rows
  class?: string;
}>();
```

Visual contract:
- Each row: `h-3 rounded-[var(--radius-sm)] bg-[var(--color-neutral-200)] animate-pulse`.
- Rows separated by `space-y-2` when `lines > 1`.
- Inherits any consumer-supplied class (e.g. width).

Used by:
- `/review` in-flight state — a fake findings list (3 file headers each with 2 finding rows).

---

## 7. `Collapsible.vue`

```ts
defineProps<{
  defaultOpen?: boolean;     // default true
}>();
defineEmits<{ (e: 'toggle', open: boolean): void }>();
```

Slots: `header` (always rendered, clickable), `body` (rendered when open).

Behavioural contract:
- `aria-expanded` synced with state on the header `<button>`.
- Keyboard: `Enter` and `Space` toggle.
- Toggle uses Vue's `<Transition>` with Tailwind `transition-[max-height]` for a smooth open/close.
- Focus remains on the header after a toggle.

Used by:
- `/review` file groups (one `Collapsible` per file).
- `/repos` row-detail expansion.

---

## 8. `ToastHost.vue`

Mounted exactly once inside `<AppShell>`. Reads the queue from `useToast()` via inject. Renders the queue:

- Position: `fixed bottom-6 right-6 z-50 flex flex-col-reverse gap-2 max-w-sm`.
- Each toast: a small `Card`-shaped element with a left border-tinted by category (`success` → `--color-success-fg`, `info` → `--color-info-fg`, `error` → `--color-danger-fg`), a body string, an optional `<Button variant="ghost" size="sm">{action.label}</Button>`, and a dismiss `×` button.
- Auto-dismiss timers live here; cancelled on unmount.
- `role="status"` for success/info, `role="alert"` for error.

The component reads `Toast[]` and renders newest-first using `flex-col-reverse`.

---

## 9. `SeverityPill.vue` *(non-primitive but cross-page; lives in `components/findings/`)*

```ts
defineProps<{
  severity: 'critical' | 'major' | 'minor' | 'info';
}>();
```

Visual contract:
- `inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium uppercase tracking-wide`.
- Background + foreground colours read **only** from `--color-severity-<severity>-{bg,fg}`.
- Label text equals `severity.toUpperCase()`.

Single source of truth for severity colours across `/review` and any future place a severity is rendered. Spec FR-006 anchors here.

---

## Composition rules

- Pages NEVER render bare `<div>` containers — they go through `Card`.
- Pages NEVER render bare `<button>` or `<a>` — they go through `Button`.
- Severity is **always** rendered via `SeverityPill`, never as bare text or with ad hoc colour.
- Toasts are **always** triggered via `useToast().push(...)`, never via inline alert banners on the page.

Any deviation from these rules is a review-blocker for the implementation phase.
