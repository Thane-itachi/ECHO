"""Queue guarantees: one row claimed once, one notification sent once."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.time import utcnow
from app.db.models import Job, Outbox
from app.services.jobs import claim_jobs, enqueue_job, enqueue_outbox
from app.worker import handle_reminder_notify, run_once


def test_outbox_enqueue_is_idempotent(session_factory):
    with session_factory() as session:
        first = enqueue_outbox(session, idempotency_key="k1", channel="email", payload={"a": 1})
        second = enqueue_outbox(session, idempotency_key="k1", channel="email", payload={"a": 1})
        session.commit()
        rows = session.scalars(select(Outbox)).all()
    assert first is not None
    assert second is None
    assert len(rows) == 1


def test_duplicate_job_is_not_queued_twice(session_factory):
    with session_factory() as session:
        when = utcnow()
        assert enqueue_job(session, kind="reminder.notify", run_at=when, payload={}, idempotency_key="j1")
        assert enqueue_job(session, kind="reminder.notify", run_at=when, payload={}, idempotency_key="j1") is None
        session.commit()
        assert len(session.scalars(select(Job)).all()) == 1


def test_claim_is_exclusive(session_factory):
    with session_factory() as session:
        for index in range(3):
            enqueue_job(
                session,
                kind="reminder.notify",
                run_at=utcnow() - timedelta(minutes=1),
                payload={},
                idempotency_key=f"claim-{index}",
            )
        session.commit()

    factory = session_factory
    first = claim_jobs(factory(), worker_id="worker-1", limit=2)
    second = claim_jobs(factory(), worker_id="worker-2", limit=2)
    third = claim_jobs(factory(), worker_id="worker-3", limit=2)

    first_ids = {job.id for job in first}
    second_ids = {job.id for job in second}
    assert len(first_ids) == 2
    assert len(second_ids) == 1
    assert not (first_ids & second_ids)
    assert third == []


def test_worker_sends_one_notification_per_reminder(client, make_user, session_factory):
    user = make_user()
    due = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    reminder = client.post(
        "/api/reminders", json={"title": "return the ladder", "due_at": due}, headers=user["headers"]
    ).json()

    # Make the job due now (the API schedules it for the reminder's due time).
    with session_factory() as session:
        job = session.scalars(select(Job).where(Job.kind == "reminder.notify")).one()
        job.run_at = utcnow() - timedelta(seconds=5)
        reminder_status_before = reminder["status"]
        session.commit()

    stats = run_once(session_factory, worker_id="worker-1")
    assert stats.claimed == 1 and stats.done == 1
    assert reminder_status_before == "scheduled"

    with session_factory() as session:
        assert len(session.scalars(select(Outbox)).all()) == 1
        assert session.scalars(select(Job)).one().status == "done"

    # A retry of the same job must not duplicate the notification.
    with session_factory() as session:
        job = session.scalars(select(Job)).one()
        handle_reminder_notify(session, job)
        session.commit()
        assert len(session.scalars(select(Outbox)).all()) == 1


def test_unknown_job_kind_fails_instead_of_looping(session_factory):
    with session_factory() as session:
        enqueue_job(
            session,
            kind="does.not.exist",
            run_at=utcnow() - timedelta(minutes=1),
            payload={},
            idempotency_key="unknown-1",
            max_attempts=1,
        )
        session.commit()

    stats = run_once(session_factory, worker_id="worker-x")
    assert stats.claimed == 1 and stats.failed == 1

    with session_factory() as session:
        job = session.scalars(select(Job)).one()
        assert job.status == "failed"
        assert "no handler" in (job.last_error or "")


def test_failed_job_requeues_with_backoff_when_attempts_remain(session_factory):
    from app.services.jobs import fail_job

    with session_factory() as session:
        job = enqueue_job(
            session, kind="reminder.notify", run_at=utcnow(), payload={}, idempotency_key="retry-1", max_attempts=3
        )
        session.commit()
        job.attempts = 1
        fail_job(session, job, "boom")
        session.commit()
        assert job.status == "queued"
        assert job.run_at > utcnow()

        job.attempts = 3
        fail_job(session, job, "boom again")
        session.commit()
        assert job.status == "failed"
