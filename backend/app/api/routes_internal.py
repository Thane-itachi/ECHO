"""The two endpoints a scheduler calls, instead of a process that never stops.

On a serverless deploy there is no long-running worker: the function is frozen between
requests. So the loop the worker used to own is exposed as one endpoint that does
exactly one pass (`/api/internal/tick`), and the schema is brought up to date by
another (`/api/internal/migrate`). Both require the shared secret a scheduler holds,
and both refuse to run when no secret is configured, so an unset environment variable
is a closed door rather than an open one.
"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import settings
from app.core.errors import Forbidden

logger = logging.getLogger("echo.internal")

router = APIRouter(prefix="/api/internal", tags=["internal"])

# app/api/routes_internal.py -> app/api -> app -> backend. `parents[3]` is one above the
# backend directory, which is the repository root locally and the function root in a
# bundle, so alembic.ini was looked for one directory too high.
BACKEND_ROOT = Path(__file__).resolve().parents[2]


def require_cron_secret(authorization: str | None = Header(default=None)) -> None:
    """`Authorization: Bearer <ECHO_CRON_SECRET>`, which is what Vercel Cron sends."""
    expected = settings.cron_secret
    if not expected:
        raise Forbidden("scheduled endpoints are disabled: ECHO_CRON_SECRET is not set")
    supplied = (authorization or "").removeprefix("Bearer ").strip()
    if supplied != expected:
        raise Forbidden("bad or missing cron secret")


@router.post("/tick", dependencies=[Depends(require_cron_secret)])
def tick(request: Request, db: Session = Depends(get_db)) -> JSONResponse:
    """Claim the jobs that are due, then hand the outbox to the push and mail services.

    Safe to call twice at the same moment: job claiming uses `SKIP LOCKED` and the
    outbox rows carry an idempotency key, so two schedulers overlapping cannot send a
    reminder twice.
    """
    from app.scripts.drain_outbox import drain
    from app.worker import run_once

    factory = request.app.state.session_factory
    stats = run_once(factory, worker_id="cron")
    try:
        # The transports the app already built, not fresh ones: a deployment configures
        # the push service and the mailer once, and tests swap them for captures.
        drained = drain(
            factory,
            limit=50,
            pusher=getattr(request.app.state, "pusher", None),
            mailer=getattr(request.app.state, "mailer", None),
        )
    except Exception:  # noqa: BLE001 - a provider outage must not fail the tick
        logger.exception("outbox drain failed; the next tick retries")
        drained = 0
    logger.info("tick: jobs=%s claimed, outbox=%s delivered", stats.claimed, drained)
    return JSONResponse({"claimed": stats.claimed, "delivered": drained})


@router.post("/migrate", dependencies=[Depends(require_cron_secret)])
def migrate(request: Request) -> JSONResponse:
    """`alembic upgrade head`, run from inside the deployment.

    A managed Postgres is usually reachable only from the deployment itself, so the
    migration has to run here rather than from a laptop.
    """
    from alembic import command
    from alembic.config import Config

    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    try:
        command.upgrade(config, "head")
    except Exception as exc:  # noqa: BLE001 - the operator needs the reason, not a 500
        # Only the holder of the cron secret can reach this, and they are the person who
        # has to fix the database. "internal server error" would send them to the logs of a
        # platform whose logs are not always there; the message is the answer.
        logger.exception("migration failed")
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "migration_failed",
                    "message": f"{type(exc).__name__}: {exc}"[:400],
                }
            },
        )
    logger.info("migrations applied")
    return JSONResponse({"status": "ok"})


@router.get("/outbox", dependencies=[Depends(require_cron_secret)])
def recent_outbox(request: Request, limit: int = 10) -> JSONResponse:
    """What the delivery layer last did, for the operator holding the secret.

    "My reminder never arrived" is answered here rather than by reading platform logs
    that may have rolled over: `suppressed` names the deliberate skip (opted out, no
    provider, no device), `failed` carries the error, and `sent` is what actually left.
    """
    from sqlalchemy import select

    from app.db.models import Outbox

    factory = request.app.state.session_factory
    with factory() as session:
        rows = session.scalars(
            select(Outbox).order_by(Outbox.created_at.desc()).limit(max(1, min(limit, 50)))
        ).all()
        return JSONResponse(
            {
                "items": [
                    {
                        "id": row.id,
                        "channel": row.channel,
                        "status": row.status,
                        "attempts": row.attempts,
                        "last_error": row.last_error,
                        "created_at": row.created_at.isoformat(),
                    }
                    for row in rows
                ]
            }
        )
