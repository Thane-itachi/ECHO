"""Admin service surface (fix #3).

Hard rule, enforced by tests/test_import_boundaries.py: nothing in this package may
import the memory/people/proposal repositories, the memory service, or the user API
layer. Admin code sees aggregate counts, account metadata and audit rows. It cannot
read memory content even by accident, because it has no way to decrypt it.

Every mutating function here records an audit row, and the role invariants (at least
one active founder) are enforced in the service, not in a router, so a new endpoint
cannot forget them.
"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.admin.permissions import FOUNDER, is_known_role, permissions_for
from app.core.errors import Conflict, InvalidRequest, NotFound
from app.core.mfa import generate_secret, otpauth_url
from app.core.security import hash_password
from app.core.time import utcnow
from app.db.models import (
    ADMIN_ROLES,
    AdminUser,
    AuditLog,
    Job,
    Memory,
    MemoryProposal,
    Outbox,
    User,
)
from app.repositories.system import AuditRepository
from app.schemas import (
    AdminAccountCreated,
    AdminAccountList,
    AdminAccountRead,
    AdminIdentity,
    AdminUserList,
    AdminUserRead,
    AnalyticsPoint,
    AnalyticsResponse,
    HealthResponse,
    PlatformStats,
    SecurityEvent,
    SecurityResponse,
)


def _scalar_int(session: Session, stmt) -> int:
    return int(session.scalar(stmt) or 0)


def _account_read(admin: AdminUser) -> AdminAccountRead:
    return AdminAccountRead(
        id=admin.id,
        email=admin.email,
        role=admin.role,
        is_active=admin.is_active,
        created_at=admin.created_at,
        last_login_at=admin.last_login_at,
    )


# ------------------------------------------------------------------- identity
def identity(admin: AdminUser) -> AdminIdentity:
    return AdminIdentity(
        id=admin.id,
        email=admin.email,
        role=admin.role,
        permissions=sorted(permissions_for(admin.role)),
    )


# ------------------------------------------------------------------ overview
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


def health(session: Session) -> HealthResponse:
    database = "ok"
    try:
        session.execute(select(1))
    except Exception:  # noqa: BLE001 - health must report, never raise
        database = "unavailable"
    stale_cutoff = utcnow() - timedelta(days=30)
    return HealthResponse(
        status="ok" if database == "ok" else "degraded",
        database=database,
        jobs_queued=_scalar_int(session, select(func.count()).select_from(Job).where(Job.status == "queued")),
        jobs_failed=_scalar_int(session, select(func.count()).select_from(Job).where(Job.status == "failed")),
        outbox_pending=_scalar_int(
            session, select(func.count()).select_from(Outbox).where(Outbox.status == "pending")
        ),
        admins_active=_scalar_int(
            session, select(func.count()).select_from(AdminUser).where(AdminUser.is_active.is_(True))
        ),
        admins_without_recent_login=_scalar_int(
            session,
            select(func.count())
            .select_from(AdminUser)
            .where(AdminUser.is_active.is_(True))
            .where((AdminUser.last_login_at.is_(None)) | (AdminUser.last_login_at < stale_cutoff)),
        ),
    )


def analytics(session: Session, *, days: int = 14) -> AnalyticsResponse:
    since = utcnow() - timedelta(days=days)
    buckets: dict[str, AnalyticsPoint] = {}

    def bucket(day: str) -> AnalyticsPoint:
        if day not in buckets:
            buckets[day] = AnalyticsPoint(day=day, users=0, memories=0, proposals=0)
        return buckets[day]

    for created_at in session.scalars(select(User.created_at).where(User.created_at >= since)):
        bucket(created_at.date().isoformat()).users += 1
    for created_at in session.scalars(select(Memory.created_at).where(Memory.created_at >= since)):
        bucket(created_at.date().isoformat()).memories += 1
    for created_at in session.scalars(select(MemoryProposal.created_at).where(MemoryProposal.created_at >= since)):
        bucket(created_at.date().isoformat()).proposals += 1

    approved = _scalar_int(
        session, select(func.count()).select_from(MemoryProposal).where(MemoryProposal.status == "approved")
    )
    rejected = _scalar_int(
        session, select(func.count()).select_from(MemoryProposal).where(MemoryProposal.status == "rejected")
    )
    decided = approved + rejected
    return AnalyticsResponse(
        window_days=days,
        points=[buckets[day] for day in sorted(buckets)],
        proposals_approved=approved,
        proposals_rejected=rejected,
        approval_rate=(approved / decided) if decided else None,
    )


def security(session: Session, *, limit: int = 25) -> SecurityResponse:
    since = utcnow() - timedelta(hours=24)
    failed_admin = _scalar_int(
        session,
        select(func.count())
        .select_from(AuditLog)
        .where(AuditLog.action == "admin.login_failed", AuditLog.created_at >= since),
    )
    failed_user = _scalar_int(
        session,
        select(func.count())
        .select_from(AuditLog)
        .where(AuditLog.action == "user.login_failed", AuditLog.created_at >= since),
    )
    events = AuditRepository(session).recent(limit=limit)
    return SecurityResponse(
        failed_admin_logins_24h=failed_admin,
        failed_user_logins_24h=failed_user,
        disabled_admins=_scalar_int(
            session, select(func.count()).select_from(AdminUser).where(AdminUser.is_active.is_(False))
        ),
        inactive_users=_scalar_int(
            session, select(func.count()).select_from(User).where(User.is_active.is_(False))
        ),
        recent_events=[
            SecurityEvent(
                action=entry.action,
                actor_type=entry.actor_type,
                actor_id=entry.actor_id,
                detail=entry.detail or {},
                created_at=entry.created_at,
            )
            for entry in events
        ],
    )


# ---------------------------------------------------------------- user accounts
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


# ------------------------------------------------------------ admin accounts
def list_admins(session: Session) -> AdminAccountList:
    rows = list(session.scalars(select(AdminUser).order_by(AdminUser.created_at.asc())))
    return AdminAccountList(items=[_account_read(row) for row in rows], total=len(rows))


def count_active_founders(session: Session, *, exclude_id: str | None = None) -> int:
    stmt = (
        select(func.count())
        .select_from(AdminUser)
        .where(AdminUser.role == FOUNDER, AdminUser.is_active.is_(True))
    )
    if exclude_id:
        stmt = stmt.where(AdminUser.id != exclude_id)
    return _scalar_int(session, stmt)


def create_admin(
    session: Session, *, admin: AdminUser, email: str, password: str, role: str
) -> AdminAccountCreated:
    if not is_known_role(role):
        raise InvalidRequest(f"role must be one of {', '.join(ADMIN_ROLES)}")
    if session.scalars(select(AdminUser).where(AdminUser.email == email)).first() is not None:
        raise Conflict("an administrator with that email already exists")
    secret = generate_secret()
    account = AdminUser(
        email=email,
        password_hash=hash_password(password),
        mfa_secret=secret,
        role=role,
        is_active=True,
    )
    session.add(account)
    AuditRepository(session).record(
        action="admin.created",
        actor_id=admin.id,
        actor_type="admin",
        target_type="admin",
        target_id=account.id,
        detail={"role": role},
    )
    session.commit()
    return AdminAccountCreated(
        **_account_read(account).model_dump(),
        totp_secret=secret,
        otpauth_url=otpauth_url(secret, account.email),
    )


def set_admin_role(session: Session, *, admin: AdminUser, admin_id: str, role: str) -> AdminAccountRead:
    if not is_known_role(role):
        raise InvalidRequest(f"role must be one of {', '.join(ADMIN_ROLES)}")
    account = session.get(AdminUser, admin_id)
    if account is None:
        raise NotFound("administrator not found")
    if account.role == FOUNDER and role != FOUNDER and count_active_founders(session, exclude_id=account.id) == 0:
        raise Conflict("the last active founder cannot be demoted")
    account.role = role
    AuditRepository(session).record(
        action="admin.role_changed",
        actor_id=admin.id,
        actor_type="admin",
        target_type="admin",
        target_id=account.id,
        detail={"role": role},
    )
    session.commit()
    return _account_read(account)


def set_admin_active(session: Session, *, admin: AdminUser, admin_id: str, is_active: bool) -> AdminAccountRead:
    account = session.get(AdminUser, admin_id)
    if account is None:
        raise NotFound("administrator not found")
    if not is_active:
        if account.id == admin.id:
            raise Conflict("you cannot disable the account you are signed in with")
        if account.role == FOUNDER and count_active_founders(session, exclude_id=account.id) == 0:
            raise Conflict("the last active founder cannot be disabled")
    account.is_active = is_active
    AuditRepository(session).record(
        action="admin.activated" if is_active else "admin.deactivated",
        actor_id=admin.id,
        actor_type="admin",
        target_type="admin",
        target_id=account.id,
        detail={"is_active": is_active},
    )
    session.commit()
    return _account_read(account)


def rotate_mfa(session: Session, *, admin: AdminUser, admin_id: str) -> AdminAccountCreated:
    account = session.get(AdminUser, admin_id)
    if account is None:
        raise NotFound("administrator not found")
    secret = generate_secret()
    account.mfa_secret = secret
    AuditRepository(session).record(
        action="admin.mfa_rotated",
        actor_id=admin.id,
        actor_type="admin",
        target_type="admin",
        target_id=account.id,
    )
    session.commit()
    return AdminAccountCreated(
        **_account_read(account).model_dump(),
        totp_secret=secret,
        otpauth_url=otpauth_url(secret, account.email),
    )
