# Deploying ECHO on Vercel

ECHO is a FastAPI application with a background worker, a Postgres database with
`SKIP LOCKED` job claiming, and encrypted document bytes. Vercel is a serverless host, so
three of those need an explicit answer rather than a shrug:

| What ECHO needs | How a Vercel deploy gets it |
| --- | --- |
| The API itself | `api/index.py` hands the same FastAPI app to Vercel's Python runtime |
| A database | Postgres from the Vercel Marketplace (Neon), over TCP from the function |
| The worker loop | `POST /api/internal/tick`, called every five minutes by GitHub Actions |
| Schema migrations | `POST /api/internal/migrate` (a managed database is not reachable from a laptop) |
| Encrypted document bytes | Vercel Blob, because the function filesystem is scratch space |
| Sending mail | Resend, or `ECHO_MAILER=log` to run without a provider and say so |

Everything else (accounts, the vault, blind-index search, captures, ask, reminders, web
push) is the same code the tests run against.

## 1. Create the project

```bash
vercel link --project echo          # or: vercel project create echo
vercel storage create echo-documents --type blob --access private
vercel storage connect echo-documents --yes
vercel storage update echo-documents --auth token --add-rw-token --yes
```

The last line matters: the default connection uses OIDC, which only the JavaScript
SDK knows how to exchange. ECHO speaks the Blob REST API from Python, so it needs the
static read-write token (`BLOB_READ_WRITE_TOKEN`).

The database is a Marketplace product, which means accepting Neon's terms in a browser
once. That cannot be done from a token, by design:

```bash
vercel integration add neon --name echo-db        # prints a terms link on first run
vercel integration installations                   # confirms it connected
```

## 2. Environment

```bash
# required
ECHO_ENV=production
ECHO_DATABASE_URL=postgresql://...                 # from the Neon connection, ?sslmode=require
ECHO_DATA_KEY=<32 random bytes, url-safe base64>   # python -m app.scripts.rotate_data_key --new
ECHO_USER_JWT_SECRET=<40+ random characters>
ECHO_ADMIN_JWT_SECRET=<different 40+ characters>
ECHO_PUBLIC_APP_URL=https://<project>.vercel.app
ECHO_PUBLIC_API_URL=https://<project>.vercel.app
ECHO_CORS_ORIGINS=https://<project>.vercel.app
ECHO_CRON_SECRET=<32 random characters>

# documents
ECHO_STORAGE_BACKEND=vercel-blob                    # BLOB_READ_WRITE_TOKEN comes from step 1
ECHO_STORAGE_DIR=/tmp/echo-storage                  # scratch only; never the real store
ECHO_MAX_UPLOAD_BYTES=4000000                       # Vercel caps a function request at 4.5 MB

# notifications
python -m app.scripts.vapid_keys                    # prints the three ECHO_VAPID_* lines

# mail: either a provider, or the explicit no-provider mode
ECHO_RESEND_API_KEY=re_...
ECHO_EMAIL_FROM="ECHO <reminders@yourdomain.com>"   # quotes: < > are shell syntax
# or
ECHO_MAILER=log                                     # refused while verification is on
ECHO_EMAIL_VERIFICATION_REQUIRED=false
```

`load_settings()` refuses to boot in production without a data key, distinct signing
keys, a durable document store, and a mail decision. It is strict because the
alternatives are a vault that stores plaintext or a deploy that silently cannot sign
anyone in.

## 3. Deploy, then migrate

```bash
vercel deploy --prod
curl -X POST https://<project>.vercel.app/api/internal/migrate \
  -H "Authorization: Bearer $ECHO_CRON_SECRET"
curl https://<project>.vercel.app/healthz
```

`create_all` deliberately does not run in production: a cold start must not race another
cold start into changing the schema. Migrations are an explicit call.

## 4. Schedule the worker

`.github/workflows/echo-tick.yml` calls `POST /api/internal/tick` every five minutes.
Add two repository secrets:

| Secret | Value |
| --- | --- |
| `ECHO_APP_URL` | `https://<project>.vercel.app` |
| `ECHO_CRON_SECRET` | the same string as the Vercel environment variable |

Vercel's own cron is configured too, but on the Hobby plan it runs at most once a day,
which is not a reminder service. Both schedulers can run at once: job claiming uses
`SELECT ... FOR UPDATE SKIP LOCKED` and every outbox row carries an idempotency key, so
an overlapping pair cannot deliver a reminder twice.

**Latency, stated plainly:** a reminder is delivered on the next tick, so up to five
minutes after it comes due. The alternative on this plan is a paid always-on process.

## 5. What is different from a Docker deploy

- **Documents** go to Blob instead of a directory. The store interface is the only
  change in `DocumentService`; the bytes are encrypted before they leave the process,
  so the bucket holds ciphertext.
- **Uploads** are capped at 4 MB by `ECHO_MAX_UPLOAD_BYTES`, because a Vercel function
  request body maxes out at 4.5 MB. Larger files would need client-side uploads with a
  signed token, which is not built.
- **No connection pool.** `ECHO_DB_POOL=null` on Vercel: a frozen function that holds a
  pooled connection holds it against the database's connection limit.
- **`rotate_data_key.py`** walks the filesystem, so it only works where documents are
  local. On Blob, key rotation covers the database only, unless the whole store is
  rewritten.

## 6. Checking that it really works

```bash
curl https://<project>.vercel.app/healthz
curl -X POST https://<project>.vercel.app/api/auth/register \
  -H 'Content-Type: application/json' -d '{"email":"you@example.com","password":"..."}'
curl -X POST https://<project>.vercel.app/api/internal/tick \
  -H "Authorization: Bearer $ECHO_CRON_SECRET"
```

The tick answer is `{"claimed": n, "delivered": n}`. A `403` means the secret is missing
or wrong; a `500` with "scheduled endpoints are disabled" means `ECHO_CRON_SECRET` is not
set in the deployment at all.
