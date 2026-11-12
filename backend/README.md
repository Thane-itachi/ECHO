# ECHO — Backend (Milestone 1–2)

Drop-in scaffold of the consolidated ECHO architecture: FastAPI + SQLAlchemy 2.0,
SQLite for dev, PostgreSQL for production. This milestone merges **auth + ownership
+ validation + tests** into one unit (your original plan had tests twice, in stages
2 and 4).

Verified locally: `49 passed` and a live server smoke test
(register → token → create memory → search → admin route refused with a user token).

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # fill ECHO_DATA_KEY before anything real
uvicorn app.main:app --reload   # http://127.0.0.1:8000/docs
python -m app.worker            # reminder/notification worker (separate process)
python -m app.scripts.create_admin --email you@example.com
```

## What this milestone contains

| Module | Endpoint | Notes |
|---|---|---|
| Auth | `POST /api/auth/register`, `POST /api/auth/token`, `GET /api/auth/me` | PBKDF2-SHA256, identical failure shape for unknown email and wrong password |
| Memories | `GET/POST /api/memories`, `GET/PATCH/DELETE /api/memories/{id}`, `POST …/archive`, `POST …/restore` | body encrypted at rest, search over a derived index |
| People | `GET/POST /api/people`, `DELETE /api/people/{id}` | memories may reference a person *you* own |
| Proposals | `GET/POST /api/proposals`, `POST …/approve`, `POST …/reject` | AI extraction lands here, never straight into memories |
| Reminders | `GET/POST /api/reminders`, `POST …/cancel` | creates one durable job at the due instant |
| Admin | `POST /admin/auth/token`, `GET /admin/stats`, `GET /admin/users`, `POST /admin/users/{id}/status`, `GET /admin/audit` | separate table, separate signing key, TOTP required |

## The six review points, and where they landed

1. **Ownership is a column, not an inference.** Every private table has a NOT NULL
   `user_id` (`app/db/models.py`). `OwnedRepository` (`app/repositories/base.py`)
   refuses to construct without an owner, exposes `scoped_query()` as the only query
   builder, and rejects inserts/deletes whose `user_id` differs from the scope.
   Non-owned ids return **404, never 403**.
2. **Encryption decided before search.** `app/core/crypto.py`: per-user key derived
   from one master key via HKDF, Fernet envelope on the body. Plaintext only lives in
   the derived `search_text` index column. Moving to true E2EE later touches
   `MemoryRepository._index_text` and nothing else. Production refuses to start
   without `ECHO_DATA_KEY`; dev falls back to `NullCipher` (which itself refuses when
   `ECHO_ENV=production`).
3. **Admin separation is structural.** Own table (`admin_users`), own signing key,
   own `aud` claim, MFA claim required at decode time, own dependency module
   (`app/admin/deps.py`) so it cannot borrow the user gate, and an AST test
   (`tests/test_import_boundaries.py`) that fails if admin code ever imports the
   memory/proposal repositories, memory services, or the user API layer.
4. **No in-process scheduler.** `jobs` table with `SELECT … FOR UPDATE SKIP LOCKED` on
   PostgreSQL, attempts/backoff, `idempotency_key` on jobs and outbox rows, and a
   separate outbox drain (`app/scripts/drain_outbox.py`). A crashed worker that
   retries a claimed job produces exactly one notification — covered by
   `tests/test_jobs.py::test_worker_sends_one_notification_per_reminder`.
5. **AI capture is a proposal state machine.** `memory_proposals` with
   pending → approved/rejected, `decided_at`, `decided_by`, audited, and a second
   approval is a 409 instead of a duplicate memory.
6. **Cross-tenant tests exist.** `tests/test_isolation.py` (9 tests) proves user B
   cannot read, list, search, update, archive, delete, or re-parent A's rows, and
   cannot attach A's person to B's memory.

Plus: `extra="forbid"` on every request model, so `user_id` cannot be smuggled into a
create payload (`tests/test_isolation.py::test_cannot_smuggle_user_id_into_create`).

## Deliberate tradeoffs (written down, not hidden)

- **Search index is plaintext.** `search_text` is a lowercased projection of title +
  body, so search never decrypts a row. If/when ECHO goes E2EE, search moves
  client-side and `_index_text` is the only function to change. This is asserted in
  `tests/test_encryption.py`, so it can't drift silently.
- **Naive UTC everywhere** (`app/core/time.py`). SQLite drops tzinfo silently; storing
  naive UTC once means no "same night" comparisons that differ between SQLite and
  PostgreSQL.
- **`create_all` on boot for dev only.** Milestone 3 should add Alembic before the
  first real deployment; nothing in the code prevents it.
- **People notes are not encrypted** (only memory/proposal bodies are). Cheap to
  extend: add `notes_enc` alongside the existing column.

## Suggested Milestone 3

1. Alembic baseline + the `search_text` index → `pg_trgm`/`tsvector` on PostgreSQL.
2. The extraction worker that turns a chat turn into `memory_proposals` rows.
3. Relationship engine + attachment upload with signed URLs.
4. Real transport in `drain_outbox.deliver()`.
5. Frontend: Memory Vault, Ask ECHO, proposal inbox.

## Layout

```
app/
  core/          config, time, errors, security (pbkdf2 + aud tokens), mfa, crypto
  db/            models (ownership columns), session factories
  repositories/  base (owner scope enforced), memories, proposals, system (user/job/outbox/audit)
  services/      memories, proposals, reminders, jobs (queue), serializers
  api/           deps, auth, memories+people, proposals, reminders
  admin/         deps (isolated gate), service (aggregates only), routes
  worker.py      queue loop + handlers
  scripts/       create_admin, drain_outbox
tests/           isolation, ownership, auth, proposals, jobs, encryption, import boundaries
```
