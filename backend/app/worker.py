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

from app.core.config import settings
from app.core.crypto import CipherError, build_cipher
from app.db.models import Reminder
from app.repositories.memories import PersonRepository
from app.repositories.proposals import ProposalRepository
from app.repositories.system import AuditRepository
from app.services.extraction import extract_proposals, extract_proposals_with_model
from app.services.llm import build_llm
from app.services.jobs import claim_jobs, complete_job, enqueue_outbox, fail_job
from app.services.push import Notification, PushService, build_pusher

logger = logging.getLogger("echo.worker")

Handler = Callable[[Session, object], None]


def handle_reminder_notify(session: Session, job) -> None:
    reminder = session.get(Reminder, job.payload.get("reminder_id"))
    if reminder is None or reminder.status != "scheduled":
        return
    payload = {
        "reminder_id": reminder.id,
        "title": reminder.title,
        "due_at": reminder.due_at.isoformat() if reminder.due_at else None,
    }
    enqueue_outbox(
        session,
        idempotency_key=f"outbox:{reminder.notification_key}",
        channel="email",
        user_id=reminder.user_id,
        payload=payload,
    )
    # Same notification, second channel. Queued only when there is a device to reach,
    # so an account that never enabled notifications does not accumulate dead rows.
    push = PushService(session, reminder.user_id, pusher=build_pusher())
    if push.device_count():
        enqueue_outbox(
            session,
            idempotency_key=f"outbox:push:{reminder.notification_key}",
            channel="push",
            user_id=reminder.user_id,
            payload={
                **payload,
                "body": "A promise you asked to be reminded about is due.",
                "url": "/reminders",
            },
        )
    reminder.status = "notified"


def handle_memory_extract(session: Session, job) -> None:
    """Turn a queued capture into pending proposals. Never writes a memory.

    The note arrived encrypted in the payload, so the queue is not a second plaintext
    copy. Re-running a job is safe: proposals whose source sentence is already pending
    for this user are skipped instead of duplicated.
    """
    user_id = job.payload.get("user_id")
    text_enc = job.payload.get("text_enc")
    if not user_id or not text_enc:
        raise ValueError("extraction job payload is incomplete")
    cipher = build_cipher()
    try:
        text = cipher.decrypt(text_enc, user_id)
    except CipherError as exc:
        # Almost always a deployment mistake: the worker process is missing
        # ECHO_DATA_KEY, so it derives a different (or no) key than the API that
        # encrypted the note. Say so instead of a bare "scheme mismatch".
        raise ValueError(
            "cannot decrypt capture: the worker and the API must run with the same ECHO_DATA_KEY"
        ) from exc

    people = PersonRepository(session, user_id, cipher=cipher)
    known_people = tuple(person.name for person in people.search(limit=200)[0])

    # Model first when one is configured, rules otherwise (or when the model gives
    # nothing usable). Either way the output is proposals the user approves, never
    # memories: a wrong extraction costs one click.
    extractor = "rules"
    proposals: list | None = None
    if settings.llm_extraction:
        llm = build_llm()
        if llm is not None:
            proposals = extract_proposals_with_model(text, known_people=known_people, llm=llm)
            extractor = "model"
    if proposals is None:
        proposals = extract_proposals(text, known_people=known_people)
        extractor = "rules"

    repo = ProposalRepository(session, user_id, cipher=cipher)
    pending = repo.list_by_status(status="pending", limit=200)[0]
    already = {repo.read_source_text(proposal) for proposal in pending}

    created = 0
    for extracted in proposals:
        if extracted.source_text in already:
            continue
        repo.create(
            title=extracted.title,
            content=extracted.content,
            source_text=extracted.source_text,
            category=extracted.category,
            confidence=extracted.confidence,
        )
        created += 1

    AuditRepository(session).record(
        action="capture.extracted",
        actor_id=user_id,
        actor_type="system",
        target_type="proposal",
        detail={"proposed": created, "candidates": len(proposals), "extractor": extractor},
    )


HANDLERS: dict[str, Handler] = {
    "reminder.notify": handle_reminder_notify,
    "memory.extract": handle_memory_extract,
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
    from app.scripts.drain_outbox import drain

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
        # A due reminder is only half the job: the outbox row it wrote still has to be
        # handed to the push service or the mailer. Draining here is what makes a
        # reminder actually arrive without a second cron.
        try:
            drain(factory, limit=50)
        except Exception:  # noqa: BLE001 - a provider outage must not stop the worker
            logger.exception("outbox drain failed; will retry on the next pass")
        if stats.claimed == 0:
            time.sleep(poll_interval)
    logger.info("echo worker %s stopped", worker_id)


if __name__ == "__main__":  # pragma: no cover
    main()
