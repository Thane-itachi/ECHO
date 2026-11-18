# ECHO design system

Two layers and nothing else: **tokens** own every value, **components** own every control.
A page composes them and writes no colour, no radius and no shadow of its own. This is the
specification the interface is built against, as implemented in `web/src`.

## Layer 1: tokens (`web/src/tokens.css`)

Imported before `styles.css`, which imports it after the fonts. Two tiers:

- **Primitives** — raw values, never used directly by a page: navy `#080d1b` … violet
  `#7957ff`, violet-450 `#6d46f2` for fills, violet-400 `#9b7bff` for brand text on dark,
  cyan `#22d3ee` as the accent.
- **Semantic** — what a page is allowed to name: `--bg`, `--surface`, `--text`,
  `--text-muted`, `--text-secondary`, `--brand`, `--brand-text`, `--brand-line`,
  `--brand-wash`, `--accent`, `--success`, `--warning`, `--danger`, `--border`,
  `--border-strong`, `--fill-weak`.

Also in the same file: `--space-1…16` (4–64px), `--radius-sm/md/lg/full`, `--shadow-card`,
`--shadow-dropdown`, `--shadow-modal`, `--shadow-focus`, `--shadow-brand`, the type scale
and weights, and the two theme sets.

**Themes.** `[data-theme='light']` re-points the semantic layer (paper `#f7f8fc`, brand
`#5f3fe0`, accent `#0e7490`); the rail stays navy in both. `web/src/lib/theme.ts` stores the
choice under `echo-theme`, applies `html[data-theme]` and updates `theme-color`; an inline
script in `index.html` sets the attribute before first paint so there is no flash.

**Legacy aliases.** The older names (`--paper`, `--ink`, `--leather` …) are aliases of the
semantic layer. They exist so the long stylesheet follows the system without a rewrite, and
new code must not use them.

**Type.** Inter everywhere, self-hosted at `web/public/fonts/inter-{latin,latin-ext}.woff2`
and preloaded. No serif faces remain.

## The mark (`web/src/components/Logo.tsx`)

The logo is the owner's own drawing: three concentric arcs opening to the right, four beads
resting just past the ends of the two outer arcs, and a gradient from blue at the top left to
violet at the bottom right. It is geometry, not a bitmap, so it stays crisp from a 30px rail to
the 300px watermark on the sign-in panel.

- **Measured, not invented.** Arc radii are 103, 80 and 53 on a 216 viewBox with the centre at
  108; the mouth is 144 degrees wide and sits on the horizon. Both gradient ends come from the
  owner's artwork (`#4aa0fb` into `#7c24f7` on dark, `#1d7fd6` into `#6a1fd0` on light).
- **Tokens.** The gradient stops are `--mark-arc-from` and `--mark-arc-to` in both themes, so
  the mark re-tints with the theme and a parent can recolour it (the watermark does).
- **Optical stroke.** `stroke = max(6.5, 345 / size)`, so the line thickens as the mark shrinks
  and the drawing survives 24px. Beads follow the stroke at 1.35×.
- **No plate.** The old violet tile, hairline frame and `--mark-tile-*` / `--mark-ink` variables
  are gone; the arcs carry the shape on navy or on paper.
- **Two components.** `EchoMark` is the mark alone (rail, splash, error boundary, admin).
  `EchoLogo` adds the ECHO wordmark at 0.86× the mark size, with an optional
  `Remember. Organize. Thrive.` tagline for places with room (sign-in panel, public header).
- **Tab icon.** `web/public/favicon.svg` is the same arcs and beads on a `#080d1b` rounded square.

## Layer 2: components (`web/src/components/ui`)

One barrel import: `import { Button, Card, Badge } from '../components/ui'`. Styles live in
`web/src/styles/ui.css`, imported after `styles.css` in `main.tsx`.

| Component | What it is for |
| --- | --- |
| `Button`, `ButtonLink` | `primary` (one per view), `secondary`, `danger`; `md` or `sm`; `block`. |
| `IconButton` | A single glyph with an accessible name. |
| `Card` | `plain`, `accent` (top rule, for the number that matters), `quiet` (a filled panel). |
| `Badge` | `neutral`, `brand`, `success`, `warning`, `danger`, `info`, with an optional dot. |
| `Avatar` | Initials on a brand wash. |
| `Divider` | A hairline that matches every other hairline. |
| `TextInput`, `SelectInput` | A real `<label>`, hint and error, `aria-describedby`, `aria-invalid`, stable ids via `useId`. |
| `SearchBar` | Magnifier, debounced input, a clear button that is reachable by keyboard. |
| `EmptyState`, `ErrorState` | The two honest states: nothing here yet, and something went wrong. |
| `Skeleton`, `SkeletonRows` | Loading that does not jump the layout. |
| `Modal` | Focuses the panel, traps Tab, closes on Escape and backdrop, restores focus, locks body scroll, `role="dialog"` + `aria-modal`. |
| `ConfirmationDialog` | The same modal for a destructive act: it names the consequence in plain words and puts the verb on the button. Never "OK". |
| `ToastProvider`, `useToast` | Confirmations, `aria-live="polite"`, five seconds. Wraps the app inside the error boundary. |
| `Tabs` | Roving tabindex, arrow keys. |
| `Tooltip` | Supplementary text only, never the only place a fact lives. |

**Rules that hold everywhere**

- 44px is the floor for any control, including `sm` buttons on a phone (the media rule
  raises them at ≤560px).
- One focus ring: 2px `var(--brand-text)`, 2px offset. No component invents another.
- Destructive actions ask in a `ConfirmationDialog`; nothing calls `window.confirm`.
- A page may not style a button. If a control is missing a variant, the variant is added
  to the library, not patched in the page.
- `.empty` and `.chip` survive as parity rules in `ui.css`, so old markup renders as
  `EmptyState` and `Badge` rather than as a second visual language.

## Layout

`components/Layout.tsx` holds the shell. The rail is grouped the way the product is:

| Group | Destinations |
| --- | --- |
| Overview | Today, Insights |
| Intelligence | Ask ECHO, Search, Things to check |
| Connections | People |
| Productivity | Reminders |
| Library | Files |

A group exists only where a page exists. Briefing, graph, timeline, projects, tasks,
calendar and follow-ups are deliberately absent rather than present as dead links. The
account lives on `/menu`; the rail keeps one card pinned to the bottom.

**Breakpoints.** ≤560px the rail becomes a bar: group labels hide, groups dissolve
(`display: contents`), destinations flow into a 3-column grid so all eight stay visible.
≤520px toasts span the width. Every page is one column on a phone with no sideways scroll.

## How this is verified

- `npx tsc --noEmit` and `npm run build` before every publish.
- A Playwright sweep over 14 signed-in routes at 1440 and 390: no horizontal overflow, no
  console error, no control under 40px on a phone.
- A contrast audit in both themes: 0 violations (measured, not assumed).
- The live bundle hash is compared against the local build after each deploy.
