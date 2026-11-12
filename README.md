# ECHO

**Never forget what matters.**

ECHO is a personal memory engine: you record the things worth keeping (who borrowed
what, what a client promised, when the boiler gets fixed) and later ask for them in
plain language. It is a **web app**: a FastAPI backend and a React/TypeScript
frontend, plus an admin console with its own authentication.

Status: the features in `docs/`-level scope are implemented, encrypted, tested and
running. `158` backend tests pass. What remains is genuinely generative intelligence
(an LLM over retrieved memories) and a few production polish items, listed honestly
under [What is not done](#what-is-not-done).

---

## What works today

| Area | Detail |
|---|---|
| Accounts | Email + password (PBKDF2-SHA256), JWT access tokens. Identical failure response for unknown email and wrong password. |
| Email codes | Six digit codes by email for one of three jobs: confirm a new address, finish a sign-in (optional per account), reset a password. Only a keyed digest is stored. See [Signing in, verifying, and resetting](#signing-in-verifying-and-resetting). |
| Memory Vault | Create, read, update, archive/restore, delete, filter by category, search, `include_archived`. |
| Content encryption | Titles **and** bodies are encrypted at rest with a per-user key (HKDF from the master key). Nothing readable is stored for a memory. |
| Private search | Search runs on a keyed blind index (HMAC word tokens plus 3- and 4-character prefixes). Word and prefix matching work; no plaintext word list exists to steal. |
| People | Add and remove the people your memories are about. Notes are encrypted too. |
| Captures | A pasted note goes into a durable queue; the extraction worker turns it into **proposals** (`pending → approved/rejected`). Rule-based by default, model-backed when a provider is configured, and in both cases a proposal is discarded unless its source sentence is word-for-word in your note. Approval is an audited state transition that creates exactly one memory. |
| Ask ECHO | Answers with citations. With no model configured it quotes your stored memories, marks them `[1]`, `[2]`, and lists the sources. With OpenAI configured the model writes the sentence over those same notes, and an answer that cites nothing is discarded in favour of the quotation. `mode` says which one answered. |
| Reminders | Durable `jobs` + outbox queue with `SKIP LOCKED` and one idempotency key per occurrence, so a restart never double-sends. Due reminders are delivered as notifications to the user's own devices. |
| Notifications | Web Push: a phone or laptop subscribes from the sidebar, and a due reminder arrives as a notification with ECHO closed. Payloads are encrypted per device, a retired device is deleted rather than retried, and a test button proves the setup. See [Notifications on your phone](#notifications-on-your-phone). |
| Documents | Encrypted attachments: the bytes are encrypted before they reach the disk, filenames are generated server-side, size-capped, owner-scoped, optionally attached to a memory. |
| Links | Memory-to-memory connections, owner-checked on both ends, idempotent, self-links refused. |
| Isolation | Every private row carries a `NOT NULL user_id`, and `OwnedRepository` cannot be constructed without an owner scope, so a cross-user read is a 404, not an IDOR. |
| Admin console | Founder / platform_admin / support_admin roles over a reviewable permission matrix, TOTP **required** for every administrator, last-founder protection, MFA rotation, audited failed logins, founder-only break-glass access that records its reason. Administrators are created through single-use enrolment links, so the password and authenticator secret are chosen by the account holder. React screens for overview, users, administrators, audit log and security. |
| Migrations | Alembic baseline with a test that fails if `models.py` and the migrations ever drift. |

## What is not done

Stated plainly, because a roadmap that hides this is a sales document:

- **The model provider is optional, and off unless you configure it.** With no key,
  nothing in ECHO makes a network call: answers quote your memories, extraction uses
  rules. With `ECHO_OPENAI_API_KEY` set, both can use a model (see
  [Optional model provider](#optional-model-provider-openai)). What is not done is
  multi-provider support: only the OpenAI wire protocol is implemented, which covers
  OpenAI, Azure-style gateways, vLLM, LM Studio and Ollama.
- **Reminders go out as push notifications, not as email.** Web Push is wired end to
  end (encrypted payload, VAPID signature, a device that is retired is removed). The
  email channel for reminders is still a stub: the outbox row is written and marked
  `failed` with "not wired yet", because a reminder email needs a template and an
  opt-out that do not exist. Nothing pretends to have sent it.
- **A push notification is only as good as the browser.** iOS Safari requires the site
  to be added to the Home Screen; a browser with notifications blocked cannot be fixed
  from inside the app, so the toggle says so instead of failing silently.
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
    services/       memories, proposals, reminders, ask, captures, extraction, documents,
                    jobs, email_codes, mailer
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
115 passed
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
- `tests/test_admin_secrets.py` — administrators' TOTP seeds are ciphertext in the raw
  row, a user's content key cannot open one, and a legacy plaintext row still signs in.
- `tests/test_key_rotation.py` — a retired key reads but never writes; after rotation a
  process holding only the new key still finds memories by search, opens documents,
  decrypts queued captures and signs an administrator in; running rotation without the
  old key reports what it could not read instead of overwriting it.
- `tests/test_jobs.py` — one job claimed once, one notification per reminder, unknown
  job kinds fail instead of looping forever.
- `tests/test_migrations.py` — Alembic `head` must equal `Base.metadata`.

## Rotating the data key

A key you can never change is a key that leaks forever, so rotation is a first-class
operation. It is a window, not a cut-over, and no row is lost if any step is interrupted:

```bash
# 1. start everything with both keys: new one encrypts, old one only decrypts
ECHO_DATA_KEY=<new> ECHO_DATA_KEY_PREVIOUS=<old> scripts/dev.sh

# 2. see what is still on the old key, then rewrite it
cd backend
python -m app.scripts.rotate_data_key --check
python -m app.scripts.rotate_data_key --apply

# 3. drop ECHO_DATA_KEY_PREVIOUS, restart, confirm --check reports zero
```

`--apply` rewrites memory titles and bodies, person notes, proposals and their source
sentences, encrypted documents on disk, queued capture payloads, every blind index
(tokens are keyed, so search breaks silently if they are not rekeyed) and
administrators' sealed TOTP seeds. It is safe to re-run: each value is decrypted to
plaintext and re-encrypted under the current key, never encrypted twice. If a value
cannot be read with the configured keys, the run names the row and stops instead of
overwriting it.

## Signing in, verifying, and resetting

Regular accounts use a password plus a six digit code by email. Administrators are
separate people in a separate table and keep their authenticator app: no email code
can ever stand in for an administrator's TOTP.

| | Regular user | Founder / platform / support admin |
|---|---|---|
| Sign up | email + password + emailed code | enrolment link, then authenticator app |
| Sign in | email + password | email + password + TOTP |
| Optional second step | emailed code at every sign-in | not applicable (TOTP is mandatory) |
| Password reset | emailed code | re-issue an enrolment link |

The rules the code service enforces, all covered by tests:

- six digits, cryptographically random (`secrets`), five minute life, single use;
- five wrong guesses and the code is dead, even if the sixth guess is right;
- only a keyed digest is stored: `HMAC-SHA256(pepper, email | purpose | code)`, so the
  table cannot be turned back into codes, and the same guess hashes differently per
  address;
- a new code retires the previous one for that address and purpose;
- sixty seconds between sends, five codes per address per hour, twenty per IP per hour;
- asking for a code answers identically for known and unknown addresses (except in
  local development, where the code is handed back because there is no mailbox);
- signing in is refused until the address is confirmed, and a reset changes the
  password, marks the address verified, and ends sessions issued before it.

That last one is exact rather than approximate: every user token carries a fingerprint
of the current password hash, so a reset invalidates older tokens immediately, even one
minted in the same second.

```bash
# development: no provider needed, codes appear in the API log (and in the UI)
bash scripts/dev.sh

# production: set the provider, then ECHO refuses to start without it
ECHO_ENV=production
ECHO_RESEND_API_KEY=re_...
ECHO_EMAIL_FROM='ECHO <codes@yourdomain.com>'
```

## Optional model provider (OpenAI)

ECHO answers and extracts without any model. A provider is an upgrade, never a
dependency: if the key is missing, the request never waits on a network call, and if
the provider fails the deterministic path answers instead. Nothing here needs a
provider to run the tests.

```bash
cd backend
# .env
ECHO_LLM_PROVIDER=openai
ECHO_OPENAI_API_KEY=sk-...            # never committed; .env is git-ignored
ECHO_LLM_MODEL=gpt-4o-mini            # default
ECHO_LLM_EXTRACTION=true              # model-backed captures; false keeps rules only
# ECHO_OPENAI_BASE_URL=http://localhost:11434/v1   # local Ollama, same protocol
```

Restart the API (for answers) and the worker (for extraction). The startup log prints
which path is live, without the key:
`model provider: openai/gpt-4o-mini at https://api.openai.com/v1`.

**What is guaranteed, in code rather than in a prompt:**

- Every generated answer must carry `[n]` markers that resolve to notes retrieved for
  *that question*. Markers pointing at a note that was not retrieved are deleted. An
  answer left with no usable citation is thrown away, and the extractive answer is
  returned with `mode: "extractive"`.
- Every model-extracted proposal must carry a `source_text` that appears word-for-word
  in the note (case and whitespace ignored). A proposal that fails this is not queued,
  so a model cannot put a fact into your approval list that you never wrote.
- Citations are assigned by retrieval, never by the model: the `citations` array is
  built from memory rows, and the markers are renumbered to index it.
- A provider error, timeout or unparseable reply is a fallback, not a 500.

**What it costs you, stated plainly:** with the provider enabled, the text of the
memories retrieved for a question, and the text of a captured note, are sent to OpenAI
(or whatever `ECHO_OPENAI_BASE_URL` points at). That is a deliberate, per-deployment
decision: leave the key unset and no content ever leaves the machine. Requests are
bounded (20s timeout, ~400 output tokens for an answer, ~900 for extraction) so a
stuck provider costs a request a second, not a hung worker.

## Notifications on your phone

A reminder is only useful if it reaches you with the tab closed. That is Web Push: the
browser hands ECHO a subscription for that device, ECHO stores it against your account,
and a due reminder is encrypted to that device and handed to the push service (Google's
or Mozilla's), which relays ciphertext it cannot read.

```bash
cd backend
python -m app.scripts.vapid_keys        # prints two lines, paste them into .env
# ECHO_VAPID_PUBLIC_KEY=BC...          # reaches browsers, that is expected
# ECHO_VAPID_PRIVATE_KEY=MIGHAgEA...   # base64 DER on one line; stays here
# ECHO_VAPID_SUBJECT=mailto:you@yourdomain.com
```

Restart the API and the worker. The startup log says
`notifications: web push (VAPID configured)`; with no keypair it says they are not
delivered, and the subscribe endpoint answers `503 push_not_configured` rather than
collecting endpoints it could never use.

Then, in the app: sidebar → **Notify me on this device** → allow the browser prompt →
**Send a test notification**. On an iPhone the site has to be added to the Home Screen
first; Apple allows web push only for installed web apps, and the sidebar says exactly
that rather than showing a button that does nothing.

**What is guaranteed, and why each one is there:**

- **One subscription per browser, owned by one account.** The endpoint is a capability:
  signing in as a different user on the same browser moves it, so the previous account
  cannot keep notifying that device. Endpoints are never logged and never returned by
  the API.
- **A retired device is deleted, not retried.** A `404`/`410` from the push service means
  the device is gone (cleared data, uninstalled, expired). Retrying that forever is how a
  notification system becomes a source of noise. Other failures increment a counter, and
  a device that never succeeds is dropped after five tries.
- **One broken device cannot mute the rest.** Delivery is per device; a failure on one is
  recorded and the loop continues.
- **A bad keypair fails at startup, not at send time.** The public key is derived from
  the private key and compared with `ECHO_VAPID_PUBLIC_KEY`. A mismatch is a
  `RuntimeError` when the process starts, because the alternative is browsers
  subscribing with a key the server cannot sign for and every push coming back as an
  opaque `403`.
- **The service worker navigates, it does not trust.** The payload is type-checked and
  the click target must be a same-origin relative path, so a malformed or hostile push
  cannot send the user to another site. There is no caching layer: a memory vault
  should never serve yesterday's vault from a stale cache.
- **The reminder is queued once.** The push outbox row carries the reminder's own
  idempotency key (`outbox:push:<notification_key>`), so a worker restart, or a second
  worker, cannot send it twice.

---

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
6. **Secrets have their own derivations.** Content uses
   `HKDF(master, info=user_id)`; administrators' TOTP seeds use
   `HKDF(master, salt=echo/system-secret/v1)`. Reading one cannot produce the other, so
   a bug in user content cannot be replayed against an admin's second factor. The seed
   is sealed by a column type, not by remembering to call a helper.
7. **Dev mode is loud.** Without `ECHO_DATA_KEY`, `NullCipher` stores plaintext and the
   API says so at startup. In production the same path raises instead of storing.

## Roadmap

- [x] Encryption for titles, bodies and notes, with a blind index for search
- [x] Admin MFA that cannot be disabled, roles and a permission matrix
- [x] Admin console (overview, users, administrators, audit, security)
- [x] Ask ECHO with citations
- [x] Capture queue + extraction worker writing proposals
- [x] Encrypted documents, memory links, memory-approval history
- [x] Alembic baseline + drift test
- [x] Sealed admin TOTP seeds, and a rotation path that rekeys content, documents,
      indexes and seeds
- [ ] Generative answers (LLM over retrieved memories, citations preserved)
- [ ] Model-backed extraction as an alternative to the rule-based extractor
- [ ] Reminder delivery provider behind `drain_outbox.deliver`
- [ ] PostgreSQL `pg_trgm` search, and `pgvector` when embeddings arrive
- [ ] Export and account deletion (data portability, right to erasure)
- [ ] Rate limiting and refresh tokens for the public API

## License

No license file yet: all rights reserved until you add one.
