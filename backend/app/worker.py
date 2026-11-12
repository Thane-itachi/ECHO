"""Worker loop. Runs in its own process (`python -m app.worker`), never inside the API
process, so N uvicorn workers cannot double-send a reminder."""
from __future__ import annotations

import logging
import os
import signal
import time
from dataclasses import dataclass
from typing import Callable

from sqlalchemy.orm import Session

from app.db.models import Reminder
from app.services.jobs import claim_jobs, complete_job, enqueue_outbox, fail_job

logger = logging.getLogger("echo.worker")

Handler = Callable[[Session, object], None]


def handle_reminder_notify(session: Session, job) -> None:
    reminder = session.get(Reminder, job.payload.get("reminder_id"))
    if reminder is None or reminder.status != "scheduled":
        return
    enqueue_outbox(
        session,
        idempotency_key=f"outbox:{reminder.notification_key}",
        channel="email",
        user_id=reminder.user_id,
        payload={
            "reminder_id": reminder.id,
            "title": reminder.title,
            "due_at": reminder.due_at.isoformat() if reminder.due_at else None,
        },
    )
    reminder.status = "notified"


HANDLERS: dict[str, Handler] = {
    "reminder.notify": handle_reminder_notify,
}


@dataclass
class RunStats:
    claimed: int = 0
    done: int = 0
    failed: int = 0


def run_once(session_factory, *, worker_id: str, limit: int = 10) -> RunStats:
    stats = RunStats()
    session = session_factory()
    try:
        jobs = claim_jobs(session, worker_id=worker_id, limit=limit)
        stats.claimed = len(jobs)
        for job in jobs:
            handler = HANDLERS.get(job.kind)
            if handler is None:
                fail_job(session, job, f"no handler registered for kind {job.kind!r}")
                session.commit()
                stats.failed += 1
                continue
            try:
                handler(session, job)
                complete_job(session, job)
                session.commit()
                stats.done += 1
            except Exception as exc:  # noqa: BLE001 - a failing job must not stop the loop
                session.rollback()
                logger.exception("job %s (%s) failed", job.id, job.kind)
                fail_job(session, job, str(exc))
                session.commit()
                stats.failed += 1
    finally:
        session.close()
    return stats


def main(poll_interval: float = 2.0) -> None:  # pragma: no cover - process entry point
    from app.db.session import build_engine, build_session_factory, create_all

    logging.basicConfig(level=logging.INFO)
    engine = build_engine()
    create_all(engine)
    factory = build_session_factory(engine)
    worker_id = f"{os.getpid()}"

    stopping = {"flag": False}

    def _stop(signum, _frame):
        logger.info("signal %s received, finishing current batch", signum)
        stopping["flag"] = True

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    logger.info("echo worker %s started", worker_id)
    while not stopping["flag"]:
        stats = run_once(factory, worker_id=worker_id)
        if stats.claimed == 0:
            time.sleep(poll_interval)
    logger.info("echo worker %s stopped", worker_id)


if __name__ == "__main__":  # pragma: no cover
    main()
