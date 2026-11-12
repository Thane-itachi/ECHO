"""Durable job queue primitives (fix #4).

There is no in-process scheduler. A reminder creates a `jobs` row at its due time;
workers claim due rows; each notification is written to the `outbox` with a unique
idempotency key before delivery. Two workers, or one worker that crashed and
restarted, cannot double-send.
"""
from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.db.models import Job, Outbox

logger = logging.getLogger("echo.jobs")

SKIP_LOCKED_DIALECTS = {"postgresql", "mysql", "mariadb"}
BACKOFF_BASE_SECONDS = 30
BACKOFF_MAX_SECONDS = 3600


def enqueue_job(
    session: Session,
    *,
    kind: str,
    run_at,
    payload: dict,
    idempotency_key: str | None = None,
    max_attempts: int = 5,
) -> Job | None:
    """Insert a job unless one with the same idempotency key already exists."""
    job = Job(
        kind=kind,
        run_at=run_at,
        payload=payload,
        idempotency_key=idempotency_key,
        max_attempts=max_attempts,
    )
    try:
        with session.begin_nested():
            session.add(job)
    except IntegrityError:
        logger.info("job %s already queued", idempotency_key)
        return None
    return job


def enqueue_outbox(
    session: Session,
    *,
    idempotency_key: str,
    channel: str,
    payload: dict,
    user_id: str | None = None,
) -> Outbox | None:
    """Insert a notification unless the exact same one already exists.

    Wrapped in a savepoint (`begin_nested`) so a duplicate does not roll back the
    caller's surrounding transaction.
    """
    entry = Outbox(
        user_id=user_id,
        channel=channel,
        payload=payload,
        idempotency_key=idempotency_key,
    )
    try:
        with session.begin_nested():
            session.add(entry)
    except IntegrityError:
        logger.info("outbox entry %s already exists, skipping", idempotency_key)
        return None
    return entry


def claim_jobs(session: Session, *, worker_id: str, limit: int = 10, now=None) -> list[Job]:
    """Atomically take a batch of due jobs.

    PostgreSQL uses SELECT ... FOR UPDATE SKIP LOCKED so parallel workers never
    hand each other the same row. SQLite (dev only) relies on its database-level
    write lock plus the `status == 'queued'` guard on the UPDATE.
    """
    moment = now or utcnow()
    dialect = session.get_bind().dialect.name
    stmt = (
        select(Job.id)
        .where(Job.status == "queued", Job.run_at <= moment)
        .order_by(Job.run_at.asc())
        .limit(limit)
    )
    if dialect in SKIP_LOCKED_DIALECTS:
        stmt = stmt.with_for_update(skip_locked=True)

    ids = list(session.scalars(stmt))
    if not ids:
        return []

    session.execute(
        update(Job)
        .where(Job.id.in_(ids), Job.status == "queued")
        .values(
            status="running",
            locked_by=worker_id,
            locked_at=moment,
            attempts=Job.attempts + 1,
        )
    )
    session.commit()
    return list(session.scalars(select(Job).where(Job.id.in_(ids))))


def complete_job(session: Session, job: Job) -> None:
    job.status = "done"
    job.locked_by = None
    job.last_error = None


def fail_job(session: Session, job: Job, error: str) -> None:
    job.last_error = error[:2000]
    job.locked_by = None
    if job.attempts >= job.max_attempts:
        job.status = "failed"
        return
    delay = min(BACKOFF_BASE_SECONDS * (2 ** max(job.attempts - 1, 0)), BACKOFF_MAX_SECONDS)
    job.status = "queued"
    job.run_at = utcnow() + timedelta(seconds=delay)
