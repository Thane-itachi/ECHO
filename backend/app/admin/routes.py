"""Admin console API.

Two routers on purpose:
* `public_router` only exposes login and is unauthenticated by design.
* `secure_router` carries `require_admin` as a router-level dependency, so a new
  endpoint cannot be added without the admin token + MFA gate. Every route then
  states the permission it needs, so authorisation is visible in the route table.

MFA is not optional: there is no code path that issues an admin token without a
verified TOTP code, and an admin row cannot exist without an enrolled secret.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.admin import service as admin_service
from app.admin.deps import get_db, require_admin
from app.admin.permissions import (
    ADMINS_READ,
    ADMINS_WRITE,
    AUDIT_READ,
    EMERGENCY_ACCESS,
    SECURITY_READ,
    STATS_READ,
    SYSTEM_READ,
    USERS_READ,
    USERS_WRITE,
    require_permission,
)
from app.core.config import settings
from app.core.errors import Forbidden, Unauthorized
from app.core.mfa import verify_totp
from app.core.security import ADMIN_AUDIENCE, DUMMY_HASH, create_access_token, verify_password
from app.core.time import utcnow
from app.db.models import AdminUser
from app.repositories.system import AdminRepository, AuditRepository
from app.schemas import (
    AdminAccountCreated,
    AdminAccountList,
    AdminAccountRead,
    AdminCreateRequest,
    AdminIdentity,
    AdminLoginRequest,
    AdminRoleUpdate,
    AdminUserList,
    AdminUserRead,
    AnalyticsResponse,
    EmergencyAccessRequest,
    EmergencyAccessResponse,
    HealthResponse,
    PlatformStats,
    SecurityResponse,
    SetUserActiveRequest,
    TokenResponse,
)

public_router = APIRouter(prefix="/admin/auth", tags=["admin"])
secure_router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])

EMERGENCY_TOKEN_TTL_SECONDS = 15 * 60


def _record_failed_login(db: Session, email: str) -> None:
    AuditRepository(db).record(
        action="admin.login_failed",
        actor_id=None,
        actor_type="admin",
        target_type="admin",
        target_id=None,
        detail={"email": email},
    )
    db.commit()


@public_router.post("/token", response_model=TokenResponse)
def admin_login(payload: AdminLoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    admin = AdminRepository(db).by_email(payload.email)
    if admin is None:
        verify_password(payload.password, DUMMY_HASH)
        _record_failed_login(db, payload.email)
        raise Unauthorized("invalid credentials")
    if not verify_password(payload.password, admin.password_hash):
        _record_failed_login(db, payload.email)
        raise Unauthorized("invalid credentials")
    if not admin.is_active:
        raise Forbidden("this admin account has been disabled")
    # No bypass: MFA is required for every administrator, verified before a token exists.
    if not verify_totp(admin.mfa_secret, payload.totp_code):
        _record_failed_login(db, payload.email)
        raise Unauthorized("invalid MFA code")

    admin.last_login_at = utcnow()
    AuditRepository(db).record(
        action="admin.login",
        actor_id=admin.id,
        actor_type="admin",
        target_type="admin",
        target_id=admin.id,
        detail={"role": admin.role},
    )
    db.commit()
    token = create_access_token(admin.id, audience=ADMIN_AUDIENCE, mfa=True)
    return TokenResponse(access_token=token, expires_in=settings.admin_token_ttl_seconds)


# ------------------------------------------------------------------- identity
@secure_router.get("/me", response_model=AdminIdentity)
def me(admin: AdminUser = Depends(require_admin)) -> AdminIdentity:
    return admin_service.identity(admin)


# ------------------------------------------------------------------- overview
@secure_router.get("/stats", response_model=PlatformStats)
def stats(
    admin: AdminUser = Depends(require_permission(STATS_READ)), db: Session = Depends(get_db)
) -> PlatformStats:
    return admin_service.platform_stats(db)


@secure_router.get("/health", response_model=HealthResponse)
def health(
    admin: AdminUser = Depends(require_permission(SYSTEM_READ)), db: Session = Depends(get_db)
) -> HealthResponse:
    return admin_service.health(db)


@secure_router.get("/analytics", response_model=AnalyticsResponse)
def analytics(
    days: int = Query(default=14, ge=1, le=90),
    admin: AdminUser = Depends(require_permission(STATS_READ)),
    db: Session = Depends(get_db),
) -> AnalyticsResponse:
    return admin_service.analytics(db, days=days)


@secure_router.get("/security", response_model=SecurityResponse)
def security(
    limit: int = Query(default=25, ge=1, le=200),
    admin: AdminUser = Depends(require_permission(SECURITY_READ)),
    db: Session = Depends(get_db),
) -> SecurityResponse:
    return admin_service.security(db, limit=limit)


# --------------------------------------------------------------- user accounts
@secure_router.get("/users", response_model=AdminUserList)
def users(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    admin: AdminUser = Depends(require_permission(USERS_READ)),
    db: Session = Depends(get_db),
) -> AdminUserList:
    return admin_service.list_users(db, limit=limit, offset=offset)


@secure_router.post("/users/{user_id}/status", response_model=AdminUserRead)
def set_user_status(
    user_id: str,
    payload: SetUserActiveRequest,
    admin: AdminUser = Depends(require_permission(USERS_WRITE)),
    db: Session = Depends(get_db),
) -> AdminUserRead:
    return admin_service.set_user_active(db, admin=admin, user_id=user_id, is_active=payload.is_active)


# -------------------------------------------------------------- admin accounts
@secure_router.get("/admins", response_model=AdminAccountList)
def list_admins(
    admin: AdminUser = Depends(require_permission(ADMINS_READ)), db: Session = Depends(get_db)
) -> AdminAccountList:
    return admin_service.list_admins(db)


@secure_router.post("/admins", response_model=AdminAccountCreated, status_code=201)
def create_admin(
    payload: AdminCreateRequest,
    admin: AdminUser = Depends(require_permission(ADMINS_WRITE)),
    db: Session = Depends(get_db),
) -> AdminAccountCreated:
    """Founder only. The TOTP secret is returned exactly once, at creation."""
    return admin_service.create_admin(
        db, admin=admin, email=payload.email, password=payload.password, role=payload.role
    )


@secure_router.patch("/admins/{admin_id}/role", response_model=AdminAccountRead)
def set_admin_role(
    admin_id: str,
    payload: AdminRoleUpdate,
    admin: AdminUser = Depends(require_permission(ADMINS_WRITE)),
    db: Session = Depends(get_db),
) -> AdminAccountRead:
    return admin_service.set_admin_role(db, admin=admin, admin_id=admin_id, role=payload.role)


@secure_router.post("/admins/{admin_id}/status", response_model=AdminAccountRead)
def set_admin_status(
    admin_id: str,
    payload: SetUserActiveRequest,
    admin: AdminUser = Depends(require_permission(ADMINS_WRITE)),
    db: Session = Depends(get_db),
) -> AdminAccountRead:
    return admin_service.set_admin_active(db, admin=admin, admin_id=admin_id, is_active=payload.is_active)


@secure_router.post("/admins/{admin_id}/mfa/rotate", response_model=AdminAccountCreated)
def rotate_admin_mfa(
    admin_id: str,
    admin: AdminUser = Depends(require_permission(ADMINS_WRITE)),
    db: Session = Depends(get_db),
) -> AdminAccountCreated:
    return admin_service.rotate_mfa(db, admin=admin, admin_id=admin_id)


# -------------------------------------------------------------------- audit
@secure_router.get("/audit")
def audit(
    limit: int = Query(default=50, ge=1, le=200),
    action: str | None = Query(default=None, max_length=64),
    admin: AdminUser = Depends(require_permission(AUDIT_READ)),
    db: Session = Depends(get_db),
) -> dict:
    repo = AuditRepository(db)
    entries = repo.recent(limit=limit)
    if action:
        entries = [entry for entry in entries if entry.action == action]
    return {
        "items": [
            {
                "id": entry.id,
                "action": entry.action,
                "actor_type": entry.actor_type,
                "actor_id": entry.actor_id,
                "target_type": entry.target_type,
                "target_id": entry.target_id,
                "detail": entry.detail,
                "created_at": entry.created_at.isoformat(),
            }
            for entry in entries
        ],
        "total": len(entries),
    }


# ------------------------------------------------------------- emergencies
@secure_router.post("/emergency/access", response_model=EmergencyAccessResponse)
def emergency_access(
    payload: EmergencyAccessRequest,
    admin: AdminUser = Depends(require_permission(EMERGENCY_ACCESS)),
    db: Session = Depends(get_db),
) -> EmergencyAccessResponse:
    """Break-glass: founder-only, short-lived, reason recorded.

    This is the one deliberately powerful endpoint. It never widens an account's
    role; it issues a 15-minute token marked `elevated` and writes the reason to the
    audit trail, so an incident review can reconstruct who did what and why.
    """
    AuditRepository(db).record(
        action="admin.emergency_access",
        actor_id=admin.id,
        actor_type="admin",
        target_type="admin",
        target_id=admin.id,
        detail={"reason": payload.reason},
    )
    db.commit()
    token = create_access_token(
        admin.id,
        audience=ADMIN_AUDIENCE,
        ttl_seconds=EMERGENCY_TOKEN_TTL_SECONDS,
        mfa=True,
        extra={"elevated": True, "reason": payload.reason},
    )
    return EmergencyAccessResponse(
        access_token=token, expires_in=EMERGENCY_TOKEN_TTL_SECONDS, scope="emergency"
    )
