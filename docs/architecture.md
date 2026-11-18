# ECHO: where it stands, and what comes next

Read from the running repository at commit `78eb571` on 18 November 2026, with 245 backend
tests passing. Nothing here is a promise of delivery; it is an order of work.

The vision is four verbs: **Remember, Understand, Retrieve, Act**. Eight of its ten areas
have a working foundation in the code and none is finished. This document puts what a
signed-in person can do today beside what is being asked for.

## The line that must not move

ECHO may say "I do not have that saved". It may not guess in the voice of certainty. Every
answer carries a grounding label: **from a saved record** (extractive), **paraphrased from
your notes** (inferred) or **nothing saved answers this** (no citations). An answer that
cannot cite a saved record is discarded, not softened, and a model proposal must quote a
sentence verbatim from the note or it is dropped.

A feature that invents a memory is worse than a feature that is missing.

## Where each area stands

| Area | State | What runs today | The gap |
| --- | --- | --- | --- |
| Memory system | Partial | Pasted text becomes proposals you approve or reject; every note has a category, a person, a source and a confidence figure; notes archive, restore and link to each other. | Every answer now says what it stands on, in plain words, and an extracted note shows its confidence. Still missing: an importance field, a per-note timeline, and suggestions that arrive while you are writing rather than from text you paste in. |
| Personal assistant | Partial | Ask ECHO answers from your own notes with citations, falls back to quoting them word for word with no model key, and drops any answer it cannot source. | No follow-up context, no voice, no period summaries, no recommendations. The grounding label is the whole of its honesty; there is no memory of the last question. |
| People | Partial | A person carries a name, an encrypted note, a relationship label and key dates; promises, lent and borrowed things are counted on them and become reminders in one tap. | Commitments are typed by hand rather than suggested from a note, and there is no per-person history of interactions. |
| Reminders | Partial | One-off reminders with a due time, delivered by push and email, cancellable, optionally attached to the note that caused them, with a signed opt-out that only a confirm press honours. | No recurrence, no overdue handling, no suggestions from a note, no calendar. |
| Search | Partial | Keyword search over encrypted notes through a keyed blind index, plus category and archived filters, debounced as you type. | Notes only; no date, importance or source filters; no natural phrasing; nothing from people, documents or reminders. |
| Documents | Partial | PDF, Word and image upload, text extracted in the background, bytes encrypted, download and delete per file. | No summaries, no search inside a document, no expiry tracking, no links to people or projects. |
| Dashboard | Runs | Greeting, the Ask column, the next reminder, four counts, Coming up, Recently saved, Worth a look, and an owed block that sets a reminder in one tap. | No insights beyond the counts, no quick-capture button on the page itself, no daily briefing. |
| Privacy and security | Runs | A key per person, password change, account deletion, email-code sign-in, push device list, admin console behind a code with an audit trail. | No second factor on the vault itself, no session or login history, no data export, no private-memory mode. |
| Advanced intelligence | Planned | One seed only: the link between two notes, shown as related reading. | Graph, life timeline, memory health, knowledge map, recovery, daily briefing, voice capture, duplicate cleanup. |
| Navigation | Runs | Eight destinations in five named groups (overview, intelligence, connections, productivity, library), a menu page holding the account, and every page drawn from one component library. | Groups exist only where a page exists, so briefing, graph, timeline, projects, tasks, calendar and follow-ups still have no door. Settings is one long page rather than its nine sections. |

## The four verbs, and what each one still owes

- **Remember.** Capture is real and encrypted; nothing captures on its own yet. The missing
  piece is a suggestion that arrives while the thought is still being typed.
- **Understand.** Categories, people and links exist per note. Understanding is currently
  per note, never across a month or a person.
- **Retrieve.** Asking works and cites. Retrieval still begins with a keyword, not with
  "that business idea from last month".
- **Act.** A reminder fires and reaches a phone. What is missing is ECHO noticing a promise
  on its own and offering to hold you to it.

## Six phases

1. **Remember, ask, find.** Memory management, the assistant and search. Nine tenths there:
   the gaps are confidence on screen (now shipped), suggestions while typing, and search
   that reaches past notes.
2. **People and commitments.** Relationship, dates, borrowed and lent, promises; a promise
   one tap from a reminder. Shipped as a data layer, a People page and a dashboard block.
3. **Documents that answer.** Summaries and search inside a file, expiry dates, and a
   document attached to the person or project it belongs to.
4. **The map and the line.** A graph of people, projects and notes, a life timeline, and
   memory health that names what is stale or contradictory.
5. **Calendar and prediction.** Two-way calendar, recurring reminders, and suggestions that
   read the week ahead rather than a single note.
6. **Voice and a phone app.** Spoken capture and spoken answers, then installable mobile
   software with offline notes.

## The navigation the vision asks for

| Group | Today | To come |
| --- | --- | --- |
| Overview | Today, Insights | Daily briefing |
| Intelligence | Ask ECHO, Search, Things to check | Memory graph, memory timeline |
| My memories | My notes, with categories as filters | Category shortcuts in the rail |
| Connections | People | Projects, relationships |
| Productivity | Reminders | Tasks, calendar, follow-ups |
| Library | Files | Images and documents split out |
| Settings | Account, security, reminders, text size | AI permissions, export, appearance sections |

## What to build next, smallest first

1. **A reminder offered, not typed.** The proposal pass already reads a note for meaning.
   When it finds a date or a promise, it asks once whether to hold you to it.
2. **Documents that answer.** A summary per file and search inside it, so the library
   stops being a drawer.
3. **A per-note timeline.** What happened to this note: created, edited, linked, reminded,
   archived. It is the smallest honest version of "the map and the line".
