"""Captures: a pasted note goes into the durable queue, the worker does the work.

The API request never runs extraction inline. That matters for three reasons:
a slow or failing extractor cannot time out a user's request; retries are the queue's
job, not the browser's; and the same path is used whether the note arrives from the
web app, a phone share sheet or a future Telegram bridge.

The note itself is encrypted before it is written to `jobs.payload`, so the work queue
is not a second plaintext copy of the user's diary.
"""
from __future__ import annotations

import hashlib

from sqlalchemy.orm import Session

from app.core.crypto import AnyCipher, get_default_cipher
from app.core.time import utcnow
from app.db.models import Job
from app.repositories.system import JobRepository
from app.services.jobs import enqueue_job

EXTRACTION_KIND = "memory.extract"


class CaptureService:
    def __init__(self, session: Session, owner_id: str, *, cipher: AnyCipher | None = None) -> None:
        self.session = session
        self.owner_id = owner_id
        self.cipher = cipher or get_default_cipher()
        self.jobs = JobRepository(session)

    def submit(self, text: str) -> Job:
        digits = hashlib.sha256(f"{self.owner_id}\x00{text}".encode()).hexdigest()[:32]
        idempotency_key = f"extract:{digits}"
        job = enqueue_job(
            self.session,
            kind=EXTRACTION_KIND,
            run_at=utcnow(),
            payload={"user_id": self.owner_id, "text_enc": self.cipher.encrypt(text, self.owner_id)},
            idempotency_key=idempotency_key,
        )
        self.session.commit()
        if job is not None:
            return job
        # Identical note already queued (or already processed): reuse that row instead
        # of extracting twice.
        existing = self.jobs.by_key(idempotency_key)
        if existing is None:  # pragma: no cover - only if the row vanished mid-request
            raise RuntimeError("capture job disappeared")
        return existing
