# ECHO · navy

A visual reference set for the navy direction: ten rendered screens, the tokens behind
them, and the prototype that produced them.

Open `prototype.html` in a browser and use the hash to jump to a screen
(`#chat`, `#dashboard`, `#system`, …). Every screenshot in `screens/` was rendered from
that one file with headless Chromium, so the pictures and the prototype cannot drift.

**This is a design reference, not the product.** The content is sample data (Ngozi, the
contract draft, the flat viewing), nothing in it calls the API, and the shipped app in
`web/` still wears the warm-paper archive identity. No screen here is wired to ECHO's
backend.

## Tokens

| Token | Value | Use |
|---|---|---|
| `--bg` | `#0B1120` | canvas |
| `--surface` | `#111A2E` | cards, panels, bubbles |
| `--elevated` | `#1A2540` | modals, popovers, hovered controls |
| `--border` | `#232E4A` | hairlines, dividers |
| `--accent` | `#7C6CFF` | primary actions, active nav, chart line |
| `--accent-soft` | `#A79BFF` | hover, citations, highlights |
| `--mint` | `#4ADE80` | recall, "remembered" pills, relevance |
| `--amber` | `#FBBF24` | pinned memories, warnings |
| `--text` | `#E6EAF4` | primary text |
| `--muted` | `#8B95AD` | secondary text |
| `--dim` | `#5E6880` | metadata, timestamps |
| `--radius` | `14px` | cards, buttons |

Type: Inter for everything, JetBrains Mono for scores, hex values, timestamps and
keyboard hints. Scale 10 / 12 / 14 / 16 / 20 / 28 / 36, line height 1.55, display sizes
tracked to -0.03em.

## The set

| # | Screen | Ratio | What it shows |
|---|---|---|---|
| 01 | Login | 16:10 | Split hero, echo rings behind a glass sign-in card |
| 02 | Chat | 16:10 | The three columns: sidebar, conversation, memory rail |
| 03 | Recall expanded | 4:3 | A detail shot of the answer and the three memories under it |
| 04 | Memory rail | 9:16 | The rail on its own: recall, pinned, recent |
| 05 | Dashboard | 16:10 | Memory growth, top tags, activity, suggested pins |
| 06 | Memory library | 16:10 | Filter chips, card grid, hover actions, bulk bar |
| 07 | Command palette | 16:9 | Cmd-K over a blurred conversation |
| 08 | Mobile chat | 9:19.5 | 393 x 852, recall chip, sticky composer |
| 09 | Onboarding | 16:10 | Echo orb empty state |
| 10 | Design system | 16:9 | Colour, type scale, components |

## Re-rendering

```bash
pip install playwright && python -m playwright install chromium
python design/navy/render.py      # writes screens/*.png at 2x device pixels
```

`render.py` reports viewport overflow per screen, so a layout regression cannot slip out
as a nice-looking picture.
