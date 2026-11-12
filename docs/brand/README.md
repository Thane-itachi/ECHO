# ECHO brand assets

| File | What it is |
| --- | --- |
| `echo-lockup.png` | The primary lock-up: mark, wordmark, tagline on warm paper (1200 × 630). |
| `echo-mark.png` | The mark on its own, leather plate and dark plate, at icon sizes. |

The canonical sources live with the app, not here:

- `web/src/components/Logo.tsx` — the mark as one SVG, tinted through CSS variables
  (`--mark-tile-hi`, `--mark-tile-lo`, `--mark-ink`): leather in the vault, forest in
  the admin console, cream-on-ink as the sign-in watermark.
- `web/public/favicon.svg` — the same geometry with hard-coded colours, for the tab.

Type: Instrument Serif (display and wordmark), Newsreader (reading), Karla (interface),
all self-hosted in `web/public/fonts`. Do not substitute Google Fonts; the app is meant
to render identically offline.

Plate colours: leather `#8c4a2b` → `#743a20`, forest `#2a5145`, ink `#16120d`,
paper `#f2ede3`, cream `#fbf7f0`.
