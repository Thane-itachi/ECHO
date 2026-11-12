"""Admin service surface (fix #3).

Hard rule, enforced by tests/test_import_boundaries.py: nothing in this package may
import the memory/people/proposal repositories, the memory service, or the user API
layer. Admin code sees aggregate counts, account metadata and audit rows. It cannot
read memory content even by accident, because it has no way to decrypt it.
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import NotFound
from app.db.models import AdminUser, Memory, MemoryProposal, Outbox, User
from app.repositories.system import AuditRepository
from app.schemas import AdminUserList, AdminUserRead, PlatformStats


def _scalar_int(session: Session, stmt) -> int:
    return int(session.scalar(stmt) or 0)


def platform_stats(session: Session) -> PlatformStats:
    return PlatformStats(
        users_total=_scalar_int(session, select(func.count()).select_from(User)),
        users_active=_scalar_int(
            session, select(func.count()).select_from(User).where(User.is_active.is_(True))
        ),
        # Aggregate count only: no content, no per-user breakdown.
        memories_total=_scalar_int(
            session, select(func.count()).select_from(Memory).where(Memory.archived_at.is_(None))
        ),
        proposals_pending=_scalar_int(
            session,
            select(func.count()).select_from(MemoryProposal).where(MemoryProposal.status == "pending"),
        ),
        outbox_pending=_scalar_int(
            session, select(func.count()).select_from(Outbox).where(Outbox.status == "pending")
        ),
    )


def list_users(session: Session, *, limit: int = 50, offset: int = 0) -> AdminUserList:
    rows = list(
        session.scalars(select(User).order_by(User.created_at.desc()).limit(limit).offset(offset))
    )
    total = _scalar_int(session, select(func.count()).select_from(User))
    return AdminUserList(
        items=[
            AdminUserRead(id=row.id, email=row.email, is_active=row.is_active, created_at=row.created_at)
            for row in rows
        ],
        total=total,
    )


def set_user_active(session: Session, *, admin: AdminUser, user_id: str, is_active: bool) -> AdminUserRead:
    user = session.get(User, user_id)
    if user is None:
        raise NotFound("user not found")
    user.is_active = is_active
    AuditRepository(session).record(
        action="admin.user_updated",
        actor_id=admin.id,
        actor_type="admin",
        target_type="user",
        target_id=user.id,
        detail={"is_active": is_active},
    )
    session.commit()
    return AdminUserRead(id=user.id, email=user.email, is_active=user.is_active, created_at=user.created_at)
