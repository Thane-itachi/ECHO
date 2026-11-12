"""System-scoped repositories.

These deliberately are NOT owner-scoped and are named so it is obvious at the call
site. They are used by authentication, the job queue, the outbox and the audit
trail. Only `app/admin`'s own service touches `User` rows, and never memory content.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.models import AdminUser, AuditLog, Job, Outbox, User


class UserRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def by_email(self, email: str) -> User | None:
        return self.session.scalars(select(User).where(User.email == email.strip().lower())).one_or_none()

    def by_id(self, user_id: str) -> User | None:
        return self.session.get(User, user_id)

    def create(self, *, email: str, password: str) -> User:
        user = User(
            email=email.strip().lower(),
            password_hash=hash_password(password),
            is_active=True,
        )
        self.session.add(user)
        return user


class AdminRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def by_email(self, email: str) -> AdminUser | None:
        return self.session.scalars(
            select(AdminUser).where(AdminUser.email == email.strip().lower())
        ).one_or_none()

    def by_id(self, admin_id: str) -> AdminUser | None:
        return self.session.get(AdminUser, admin_id)


class AuditRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def record(
        self,
        *,
        action: str,
        actor_id: str | None,
        actor_type: str,
        target_type: str | None = None,
        target_id: str | None = None,
        detail: dict | None = None,
    ) -> AuditLog:
        entry = AuditLog(
            action=action,
            actor_id=actor_id,
            actor_type=actor_type,
            target_type=target_type,
            target_id=target_id,
            detail=detail or {},
        )
        self.session.add(entry)
        return entry

    def recent(self, *, limit: int = 50) -> list[AuditLog]:
        return list(self.session.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)))


class OutboxRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def by_key(self, idempotency_key: str) -> Outbox | None:
        return self.session.scalars(
            select(Outbox).where(Outbox.idempotency_key == idempotency_key)
        ).one_or_none()

    def pending(self, *, limit: int = 50, now=None) -> list[Outbox]:
        """Rows that are due for a delivery attempt.

        `available_at` is the retry delay after a failed attempt; NULL means now.
        Ordering is oldest first, so a retrying row cannot starve newer ones.
        """
        from sqlalchemy import or_

        from app.core.time import utcnow

        moment = now or utcnow()
        return list(
            self.session.scalars(
                select(Outbox)
                .where(
                    Outbox.status == "pending",
                    or_(Outbox.available_at.is_(None), Outbox.available_at <= moment),
                )
                .order_by(Outbox.created_at.asc())
                .limit(limit)
            )
        )


class JobRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def by_key(self, idempotency_key: str) -> Job | None:
        return self.session.scalars(select(Job).where(Job.idempotency_key == idempotency_key)).one_or_none()

    def all(self, *, limit: int = 100) -> list[Job]:
        return list(self.session.scalars(select(Job).order_by(Job.created_at.desc()).limit(limit)))
