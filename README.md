# ECHO

**Never forget what matters.**

ECHO is a personal memory engine: you record the things worth keeping (who borrowed
what, what a client promised, when the boiler gets fixed) and later ask for them in
plain language. It is a **web app**: a FastAPI backend and a React/TypeScript
frontend, plus an admin console with its own authentication.

Status: the features in `docs/`-level scope are implemented, encrypted, tested and
running. `108` backend tests pass. What remains is genuinely generative intelligence
(an LLM over retrieved memories) and a few production polish items, listed honestly
under [What is not done](#what-is-not-done).

---

## What works today

| Area | Detail |
|---|---|
| Accounts | Email + password (PBKDF2-SHA256), JWT access tokens. Identical failure response for unknown email and wrong password. |
| Memory Vault | Create, read, update, archive/restore, delete, filter by category, search, `include_archived`. |
| Content encryption | Titles **and** bodies are encrypted at rest with a per-user key (HKDF from the master key). Nothing readable is stored for a memory. |
| Private search | Search runs on a keyed blind index (HMAC word tokens plus 3- and 4-character prefixes). Word and prefix matching work; no plaintext word list exists to steal. |
| People | Add and remove the people your memories are about. Notes are encrypted too. |
| Captures | A pasted note goes into a durable queue; the extraction worker turns it into **proposals** (`pending → approved/rejected`). Approval is an audited state transition that creates exactly one memory. |
| Ask ECHO | Answers with citations: the response quotes your stored memories, marks them `[1]`, `[2]`, and lists the sources. Says plainly when nothing matches instead of inventing an answer. |
| Reminders | Durable `jobs` + outbox queue with `SKIP LOCKED` and one idempotency key per occurrence, so a restart never double-sends. |
| Documents | Encrypted attachments: the bytes are encrypted before they reach the disk, filenames are generated server-side, size-capped, owner-scoped, optionally attached to a memory. |
| Links | Memory-to-memory connections, owner-checked on both ends, idempotent, self-links refused. |
| Isolation | Every private row carries a `NOT NULL user_id`, and `OwnedRepository` cannot be constructed without an owner scope, so a cross-user read is a 404, not an IDOR. |
| Admin console | Founder / platform_admin / support_admin roles over a reviewable permission matrix, TOTP **required** for every administrator, last-founder protection, MFA rotation, audited failed logins, founder-only break-glass access that records its reason. Administrators are created through single-use enrolment links, so the password and authenticator secret are chosen by the account holder. React screens for overview, users, administrators, audit log and security. |
| Migrations | Alembic baseline with a test that fails if `models.py` and the migrations ever drift. |

## What is not done

Stated plainly, because a roadmap that hides this is a sales document:

- **Ask ECHO is extractive, not generative.** It retrieves and quotes your memories.
  There is no LLM call in the request path (no provider, no key, no cost). The
  response shape already carries `mode`, so adding `generated` is additive.
- **Extraction is rule-based.** `app/services/extraction.py` scores sentences with
  word cues, promise/date patterns and sentence splitting. It is deterministic,
  testable and free; it is not an LLM reader. Same swap point: it is a pure function.
- **Reminder delivery stops at the outbox.** `app/scripts/drain_outbox.py` logs what
  would be sent. Wiring an email or push provider is one function (`deliver`).
- **Search is blind-index based**, so it supports terms and prefixes, not fuzzy
  matching or embeddings. PostgreSQL `pg_trgm`/`pgvector` is the upgrade path.
- **No export, no import, no sharing.** A vault is private by construction; sharing
  is a design task, not a missing flag.
- Custom role definitions beyond the three built-in roles are not supported.

## Repository layout

```text
backend/            FastAPI + SQLAlchemy 2.0 API
  app/
    core/           config, time, errors, crypto (ContentCipher, NullCipher, BlindIndex), MFA, auth
    db/             models, session
    repositories/   OwnedRepository + memory/person/proposal/reminder/job/relationship repos
    api/            routers: auth, memories (+links), people, proposals, reminders, ask, captures, documents
    services/       memories, proposals, reminders, ask, captures, extraction, documents, jobs
    admin/          separate admin identity, roles, permissions, routes, service
    worker.py       durable job runner (reminder.notify, memory.extract)
  migrations/       Alembic baseline
  scripts/          seed-demo.py
  tests/            108 tests
web/                React 18 + TypeScript + Vite
  src/pages/        Vault, Ask ECHO, People, Captures, Reminders, Documents, Login
  src/admin/        console: login, overview, users, administrators, audit, security
  src/lib/          typed API client, user auth context, admin client (separate token)
scripts/            dev.sh / stop.sh (API + worker + web, pid-managed)
```

## Quickstart

Backend (Python 3.11+):

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -c "from app.core.crypto import new_data_key; print(new_data_key())"   # paste into ECHO_DATA_KEY
alembic upgrade head            # production: migrations, not create_all
uvicorn app.main:app --reload   # http://127.0.0.1:8000/docs
python -m app.worker            # second process: runs the queue
```

Web app (Node 20+):

```bash
cd web
npm install
npm run dev        # http://127.0.0.1:5173, proxies /api and /admin to :8000
npm run build      # tsc -b && vite build — type errors fail the build
```

Or run everything at once:

```bash
./scripts/dev.sh   # API :8000 + worker + web :5173
./scripts/stop.sh
```

Demo data, then an administrator who chooses their own credentials:

```bash
cd backend
python scripts/seed-demo.py                                          # demo@echo.local / echo-demo-2026
python -m app.scripts.create_admin --email you@example.com --invite   # prints a one-time link
```

Open the link at `/admin/enrol?token=…`, set your own password, scan the QR with an
authenticator app, type the six digits back, and the link burns. Nobody — including
whoever ran that command — ever sees the password or the TOTP secret. Then open
`http://127.0.0.1:5173` (vault) and `http://127.0.0.1:5173/admin` (console).

`--invite` is the normal way to create an administrator, and also the way to recover
one: issuing a link for an existing address replaces both its password and its
authenticator secret, so a locked-out admin needs a colleague with `ADMINS_WRITE`
rather than a support ticket. Links live 72 hours (`--expires-hours`), work once, and
are stored only as a SHA-256 digest; re-issuing retires the previous one.
`--revoke-invites` cancels the open ones. The older `--email … --password …` form still
exists for non-interactive setup, and `--rotate` re-seeds a secret from the shell when
the only founder is locked out.

## Tests

```bash
cd backend && python -m pytest
```

```text
108 passed
```

The suite is weighted towards the failure modes that actually hurt:

- `tests/test_isolation.py`, `tests/test_ownership.py` — user B cannot read, list,
  search, update, archive, delete, link to, or re-parent user A's rows.
- `tests/test_search_privacy.py` — search still matches words and prefixes while the
  database contains none of those words, and the same word hashes differently per user.
- `tests/test_encryption.py` — ciphertext at rest, ciphertext bound to its owner, and
  no plaintext in the raw row.
- `tests/test_admin_roles.py` — the permission matrix, last-founder protection, and
  that no admin token is minted without a verified TOTP code.
- `tests/test_admin_enrol.py` — enrolment links: single use, expiry, re-issue retires
  the old link, no session before the TOTP code is proven, resetting a locked-out
  admin rotates the secret, and the raw token never reaches the audit trail.
- `tests/test_import_boundaries.py` — an AST check that fails the build if the admin
  package imports the user data layer.
- `tests/test_jobs.py` — one job claimed once, one notification per reminder, unknown
  job kinds fail instead of looping forever.
- `tests/test_migrations.py` — Alembic `head` must equal `Base.metadata`.

## Design decisions worth knowing

1. **Ownership is a column, not a convention.** `user_id` is `NOT NULL` on every
   private table and `OwnedRepository` refuses to build a query without a scope.
2. **Encryption decided the search design, not the other way round.** Content and
   titles are ciphertext; search uses a keyed blind index of HMAC tokens. That is the
   trade honestly made: term and prefix search, not fuzzy search, in exchange for a
   database that leaks nothing.
3. **Admin is structurally separate.** Own table, own key, own audience, own routers,
   MFA by database constraint, enforced by an import-boundary test.
4. **Work is queued, never inline.** Captures and reminders go through a `jobs` table
   with `SKIP LOCKED` and idempotency keys, so a slow extractor cannot time out a
   request and a restart cannot double-send.
5. **AI output is a proposal.** Extraction can be wrong; the user's approval is an
   audited state transition that keeps the source sentence.
6. **Dev mode is loud.** Without `ECHO_DATA_KEY`, `NullCipher` stores plaintext and the
   API says so at startup. In production the same path raises instead of storing.

## Roadmap

- [x] Encryption for titles, bodies and notes, with a blind index for search
- [x] Admin MFA that cannot be disabled, roles and a permission matrix
- [x] Admin console (overview, users, administrators, audit, security)
- [x] Ask ECHO with citations
- [x] Capture queue + extraction worker writing proposals
- [x] Encrypted documents, memory links, memory-approval history
- [x] Alembic baseline + drift test
- [ ] Generative answers (LLM over retrieved memories, citations preserved)
- [ ] Model-backed extraction as an alternative to the rule-based extractor
- [ ] Reminder delivery provider behind `drain_outbox.deliver`
- [ ] PostgreSQL `pg_trgm` search, and `pgvector` when embeddings arrive
- [ ] Export and account deletion (data portability, right to erasure)
- [ ] Rate limiting and refresh tokens for the public API

## License

No license file yet: all rights reserved until you add one.
