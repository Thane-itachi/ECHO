# ECHO — Web app

The browser app for ECHO: Memory Vault, Ask ECHO, People, Captures (proposal
inbox) and Reminders, against the FastAPI backend in `../backend`.

React 18 + TypeScript + Vite, no UI framework. Plain CSS with one palette, so the
whole shell is ~12 kB of stylesheet instead of a component library.

```bash
npm install
npm run dev        # http://127.0.0.1:5173, proxies /api to :8000
npm run build      # tsc -b && vite build  (type errors fail the build)
npm run preview
```

The API must be running on `http://127.0.0.1:8000`:

```bash
cd ../backend && uvicorn app.main:app --reload
```

## What is real, what is not

| Screen | Status |
|---|---|
| Sign in / Create account | Real: `POST /api/auth/token`, `POST /api/auth/register`, token in localStorage |
| Memory Vault | Real CRUD: list, search, category filter, archived toggle, create, edit, archive/restore, delete |
| Ask ECHO | Real retrieval: runs the same search the vault uses and shows matching memories. **Not** a conversational assistant yet; the page says so instead of pretending. |
| People | Real: list, add, remove |
| Captures | Real approval flow: pending → approved (creates exactly one memory) or rejected, with confidence and the source sentence shown |
| Reminders | Real: create against a `datetime-local`, list upcoming/past, cancel |

`Draft one by hand` on the Captures page exists because the AI extraction worker
is Milestone 3: it is the manual version of the row that worker will write.

## Written-down decisions

- **Token in `localStorage`.** Simple for a same-origin SPA, and it means a page
  refresh keeps you signed in. The upgrade path is httpOnly cookies + CSRF, and
  it only touches `request()` in `src/lib/api.ts`.
- **Relative `/api` paths.** Dev uses a Vite proxy; production should serve the
  built `dist/` behind the same origin as the API. No CORS juggling in the client.
- **Naive-UTC timestamps.** The API stores naive UTC, so `parseUtc()` in
  `src/lib/api.ts` appends `Z` before formatting. Getting this wrong is how a
  reminder "due tomorrow" shows up as yesterday.
- **Errors are always visible.** Every failed call renders the API's own message
  (including field-level validation text) instead of a silent empty state.

## Layout

```
src/
  lib/api.ts        typed client: endpoints, error envelope, date helpers
  lib/auth.tsx      auth context, session restore, 401 → sign out
  components/Layout.tsx
  pages/            Login, Vault, Ask, People, Proposals, Reminders
  styles.css        palette + layout + responsive rules
```

## Verified in the browser

Registered an account, created a memory, drafted a capture and approved it (the
memory lands in the vault marked "Captured, then approved" with its confidence),
added a person, searched "laptop" from Ask ECHO, and confirmed a scheduled
reminder renders with "in 2 days". `npm run build` passes with `strict`,
`noUnusedLocals` and `noUnusedParameters` on.

## Next

1. Extraction worker: a chat turn becomes a `memory_proposals` row.
2. Ask ECHO that answers in sentences, with citations to the memories it used.
3. Relationship view: person → memories → promises, on one timeline.
4. httpOnly cookie auth, then admin console UI.

## The look

ECHO is set like a small private archive rather than a dashboard: warm paper with a
faint grain, ink for text, one leather accent, and hairline rules instead of floating
cards.

**Type.** Three voices, all self-hosted in `public/fonts` (no Google Fonts request, so
it looks identical offline and on every machine):

- *Instrument Serif* sets the voice: page titles, the wordmark, the sign-in headline.
  It ships a single weight, so `body { font-synthesis: none }` stops the browser from
  inventing a fake bold.
- *Newsreader* is what you actually read: memory bodies, answers, proposals, quotes.
- *Karla* is the machinery: labels, controls, buttons, numbers.

**The mark.** An E whose arms shorten and fade like a sound dying away. It is one SVG
(`src/components/Logo.tsx`) tinted through `--mark-tile` / `--mark-ink`, so the same
shape sits on paper, on the ink sidebar, and in the admin console (where the tile turns
forest green so you always know which surface you are on). The favicon is
`public/favicon.svg`, same geometry, hard-coded colours.

A few decisions worth keeping if you extend it:

- Memory rows are an index, not cards: the number sits in the margin, the date sits in
  its own column, and the selected row is marked with a leather rule on its left edge.
- The reading sheet on the right is deliberately paper-like: a 2px leather top edge, a
  dashed rule above the metadata, and a printed running footer.
- Colours live in one `:root` block at the top of `styles.css`; change the accent there
  and the whole app follows.
- Everything is readable at 380px wide: the vault stacks, the sidebar becomes a
  horizontal strip, and the sign-in page drops its editorial panel.
