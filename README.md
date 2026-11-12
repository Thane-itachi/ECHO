# ECHO

**Never forget what matters.**

ECHO is a personal memory engine: you record the things worth keeping (who borrowed
what, what a client promised, when the boiler gets fixed) and later ask for them by
plain language. It is a web app: a FastAPI backend and a React/TypeScript frontend.

Status: **Milestones 1–2 done** (auth, ownership, memory engine, people, AI-capture
proposals, reminders) and the **web app** on top of it. Admin console, the extraction
worker and conversational answers are next. See [Roadmap](#roadmap).

---

## What works today

| Area | Detail |
|---|---|
| Accounts | Email + password (PBKDF2-SHA256), JWT access tokens. Identical failure response for unknown email and wrong password. |
| Memory Vault | Create, read, update, archive/restore, delete, filter by category, full-text search, `include_archived`. |
| Content encryption | Memory bodies are encrypted at rest with a per-user key (HKDF from the master key). Search runs over a separate derived index column, so plaintext never touches the database. |
| People | Add and remove the people your memories are about. |
| Captures | AI extraction writes **proposals** (`pending → approved/rejected`), not memories. Approval is an audited state transition, not a modal. |
| Reminders | Durable `jobs` + outbox queue with `SELECT … FOR UPDATE SKIP LOCKED` and one idempotency key per occurrence, so a restart never double-sends. |
| Isolation | Every private row carries a `NOT NULL user_id`, and `OwnedRepository` cannot be constructed without an owner scope, so a cross-user read is a 404, not an IDOR. |
| Admin | Separate table, separate signing key, separate JWT audience, TOTP required, and an AST test that fails the build if the admin layer ever imports the memory layer. |

## Repository layout

```text
backend/            FastAPI + SQLAlchemy 2.0 API
  app/
    core/           config, time, errors, crypto, auth primitives
    models/         SQLAlchemy models (memories, people, proposals, reminders, jobs, admin)
    repositories/   OwnedRepository, memory/person/proposal/reminder/job repositories
    api/            routers: auth, memories, people, proposals, reminders
    workers/        reminder worker (jobs + outbox)
  tests/            49 tests, including cross-tenant isolation
  scripts/          seed-demo.py
web/                React 18 + TypeScript + Vite web app
  src/pages/        Vault, Ask ECHO, People, Captures, Reminders, Login
  src/lib/          typed API client, auth context
scripts/            dev.sh / stop.sh for running both locally
```

## Quickstart

Backend (Python 3.11+):

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                     # set ECHO_DATA_KEY before anything real
uvicorn app.main:app --reload            # http://127.0.0.1:8000/docs
```

Generate a master key:

```bash
python -c "from app.core.crypto import new_data_key; print(new_data_key())"
```

Web app (Node 20+):

```bash
cd web
npm install
npm run dev        # http://127.0.0.1:5173, proxies /api to :8000
npm run build      # tsc -b && vite build — type errors fail the build
```

Or run both at once:

```bash
./scripts/dev.sh   # API :8000 + web :5173
./scripts/stop.sh
```

Optional demo data (a handful of memories, people, a pending capture and reminders):

```bash
cd backend && python scripts/seed-demo.py   # demo@echo.local / echo-demo-2026
```

## Tests

```bash
cd backend && python -m pytest
```

```text
49 passed
```

The suite is deliberately weighted towards the failure mode that matters most:
`tests/test_isolation.py` proves user B cannot read, list, search, update, archive,
delete, or re-parent user A's rows, and `tests/test_architecture.py` fails if the
admin package ever imports the memory layer.

## Design decisions worth knowing

1. **Ownership is a column, not a convention.** `user_id` is `NOT NULL` on every
   private table and `OwnedRepository` refuses to build a query without a scope.
2. **Encryption was decided before search, not after.** The body is ciphertext; the
   searchable text lives in a derived column. Moving to PostgreSQL means `pg_trgm`
   (or `pgvector` for embeddings later) over that derived column, not a rewrite.
3. **Admin is structurally separate.** Own table, own key, own audience, own routers,
   MFA required, enforced by an import-boundary test.
4. **Reminders are durable, not in-process.** No scheduler inside the web workers:
   a `jobs` table with `SKIP LOCKED` plus an outbox, so scaling out never double-sends.
5. **AI capture produces proposals.** Extraction can be wrong; the user's approval is
   a state transition that keeps the original source text for audit.

## Web app notes

- Ask ECHO is currently **retrieval**, not conversation: it returns the memories that
  match your words. The answer-shaped assistant endpoint is Milestone 3.
- "Draft one by hand" on Captures exists because the extraction worker is not built
  yet; it creates a proposal so the approval flow is testable end to end.

## Roadmap

- [ ] Milestone 3: Alembic baseline, extraction worker writing proposals from a
      pasted note, `pg_trgm` search for PostgreSQL.
- [ ] Answer-shaped Ask ECHO (LLM over retrieved memories, with citations).
- [ ] Admin console (users, audit log, system health).
- [ ] Documents and attachments, relationships between memories, export.

## License

No license file yet: all rights reserved until you add one.
