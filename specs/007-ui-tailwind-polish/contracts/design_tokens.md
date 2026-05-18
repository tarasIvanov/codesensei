# Contract: Design Tokens (`src/styles/tokens.css`)

**Feature**: 007-ui-tailwind-polish
**Status**: Draft
**Date**: 2026-05-18

Single source of truth for every colour, font size, spacing unit, radius, and shadow used by the SPA. Defined as CSS custom properties inside Tailwind v4's `@theme` directive. Imported once from `main.ts`.

---

## File layout

```text
src/styles/
├── tokens.css       ← @theme block with the design tokens defined below
└── globals.css      ← @import "tailwindcss"; + base resets + data-theme switch
```

`main.ts`:

```ts
import './styles/globals.css';
import './styles/tokens.css';
```

---

## Token shape

### Light mode (root)

```css
@theme {
  /* Neutral scale */
  --color-neutral-0:   #ffffff;
  --color-neutral-50:  #f8fafc;
  --color-neutral-100: #f1f5f9;
  --color-neutral-200: #e2e8f0;
  --color-neutral-300: #cbd5e1;
  --color-neutral-400: #94a3b8;
  --color-neutral-500: #64748b;
  --color-neutral-600: #475569;
  --color-neutral-700: #334155;
  --color-neutral-800: #1e293b;
  --color-neutral-900: #0f172a;
  --color-neutral-950: #020617;

  /* Brand */
  --color-brand-50:  #eff6ff;
  --color-brand-100: #dbeafe;
  --color-brand-500: #3b82f6;
  --color-brand-600: #2563eb;
  --color-brand-700: #1d4ed8;
  --color-brand-900: #1e3a8a;

  /* Semantic */
  --color-success-bg: var(--color-green-100, #dcfce7);
  --color-success-fg: var(--color-green-800, #166534);
  --color-warning-bg: #fef3c7;
  --color-warning-fg: #92400e;
  --color-danger-bg:  #fee2e2;
  --color-danger-fg:  #991b1b;
  --color-info-bg:    #e0f2fe;
  --color-info-fg:    #075985;

  /* Severity pills (single source for FR-006) */
  --color-severity-critical-bg: #fee2e2;
  --color-severity-critical-fg: #991b1b;
  --color-severity-major-bg:    #ffedd5;
  --color-severity-major-fg:    #9a3412;
  --color-severity-minor-bg:    #fef3c7;
  --color-severity-minor-fg:    #92400e;
  --color-severity-info-bg:     #e0f2fe;
  --color-severity-info-fg:     #075985;

  /* Backgrounds */
  --color-bg-page:     var(--color-neutral-50);
  --color-bg-card:     #ffffff;
  --color-bg-elevated: #ffffff;
  --color-border:      var(--color-neutral-200);
  --color-text:        var(--color-neutral-900);
  --color-text-muted:  var(--color-neutral-500);

  /* Typography */
  --font-sans: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont,
               "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  --font-mono: ui-monospace, SFMono-Regular, "SF Mono", Menlo,
               "Roboto Mono", monospace;

  --font-size-xs:  0.75rem;
  --font-size-sm:  0.875rem;
  --font-size-md:  1rem;
  --font-size-lg:  1.125rem;
  --font-size-xl:  1.25rem;
  --font-size-2xl: 1.5rem;

  /* Radii */
  --radius-sm: 0.25rem;
  --radius-md: 0.5rem;
  --radius-lg: 0.75rem;

  /* Shadows */
  --shadow-sm: 0 1px 2px 0 rgb(0 0 0 / 0.05);
  --shadow-md: 0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1);
}
```

### Dark mode override

```css
:root[data-theme="dark"] {
  --color-bg-page:     var(--color-neutral-950);
  --color-bg-card:     var(--color-neutral-900);
  --color-bg-elevated: var(--color-neutral-800);
  --color-border:      var(--color-neutral-700);
  --color-text:        var(--color-neutral-50);
  --color-text-muted:  var(--color-neutral-400);

  --color-severity-critical-bg: rgb(127 29 29 / 0.4);   /* red-900/40 */
  --color-severity-critical-fg: #fecaca;                /* red-200 */
  --color-severity-major-bg:    rgb(124 45 18 / 0.4);   /* orange-900/40 */
  --color-severity-major-fg:    #fed7aa;                /* orange-200 */
  --color-severity-minor-bg:    rgb(120 53 15 / 0.4);   /* amber-900/40 */
  --color-severity-minor-fg:    #fef3c7;                /* amber-100 */
  --color-severity-info-bg:     rgb(12 74 110 / 0.4);   /* sky-900/40 */
  --color-severity-info-fg:     #bae6fd;                /* sky-200 */

  --color-success-bg: rgb(20 83 45 / 0.4);
  --color-success-fg: #bbf7d0;
  --color-warning-bg: rgb(120 53 15 / 0.4);
  --color-warning-fg: #fde68a;
  --color-danger-bg:  rgb(127 29 29 / 0.4);
  --color-danger-fg:  #fecaca;
  --color-info-bg:    rgb(12 74 110 / 0.4);
  --color-info-fg:    #bae6fd;
}
```

---

## FOUC-prevention inline script (in `index.html`)

```html
<script>
  (function () {
    try {
      var stored = localStorage.getItem('codesensei.theme');
      var prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
      var resolved = stored || (prefersDark ? 'dark' : 'light');
      document.documentElement.dataset.theme = resolved;
    } catch (e) {
      // localStorage unavailable; fall back to light
      document.documentElement.dataset.theme = 'light';
    }
  })();
</script>
```

The block runs before `main.ts` evaluates, eliminating the wrong-theme flash.

---

## Tailwind utility surface

Tokens automatically generate the corresponding Tailwind utilities under v4's CSS-first model. Example:
- `bg-brand-600` → `background-color: var(--color-brand-600);`
- `text-text-muted` is **not** generated automatically — instead, expose semantic aliases through the `@theme` shape where utility names matter (`--color-text-muted` is consumed via `color: var(--color-text-muted)` directly in component styles or as a `theme()`-helper).

Where a semantic alias is required as a utility, components consume it through inline `style="color: var(--color-text-muted)"` or a small set of helper utilities defined in `globals.css` (e.g. `.text-muted { color: var(--color-text-muted); }`). Helper utilities MUST be limited to no more than five names; anything beyond that is a sign the design system is being smuggled in as a sublanguage.

---

## Contrast requirements

| Foreground / Background pair                                           | Minimum ratio |
| ---------------------------------------------------------------------- | ------------- |
| `--color-text` on `--color-bg-page` (both modes)                       | 4.5:1         |
| `--color-text-muted` on `--color-bg-card` (both modes)                 | 4.5:1         |
| Each `--color-severity-*-fg` on its matching `*-bg` (both modes)       | 4.5:1         |
| Focus ring (`--color-brand-600` light / `--color-brand-100` dark) vs `--color-bg-page` | 3:1   |

Manual verification step in `quickstart.md` validates these.

---

## Forbidden patterns

- Inline hex colours inside `.vue` files outside of `tokens.css`. Anything that needs a colour MUST consume a token.
- Per-page CSS files with bespoke palettes — all colour goes through the variables above.
- `dark:` class-prefixed utilities. The dark mode swap is handled at the token level via `:root[data-theme="dark"]`, so utilities themselves are theme-agnostic.
