"""Admin console API.

Two routers on purpose:
* `public_router` only exposes login and is unauthenticated by design.
* `secure_router` carries `require_admin` as a router-level dependency, so a new
  endpoint cannot be added without the admin token + MFA gate.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.admin import service as admin_service
from app.admin.deps import get_db, require_admin
from app.core.config import settings
from app.core.errors import Forbidden, Unauthorized
from app.core.mfa import verify_totp
from app.core.security import ADMIN_AUDIENCE, DUMMY_HASH, create_access_token, verify_password
from app.db.models import AdminUser
from app.repositories.system import AdminRepository, AuditRepository
from app.schemas import (
    AdminLoginRequest,
    AdminUserList,
    AdminUserRead,
    PlatformStats,
    SetUserActiveRequest,
    TokenResponse,
)

public_router = APIRouter(prefix="/admin/auth", tags=["admin"])
secure_router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


@public_router.post("/token", response_model=TokenResponse)
def admin_login(payload: AdminLoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    admin = AdminRepository(db).by_email(payload.email)
    if admin is None:
        verify_password(payload.password, DUMMY_HASH)
        raise Unauthorized("invalid credentials")
    if not verify_password(payload.password, admin.password_hash):
        raise Unauthorized("invalid credentials")
    if not admin.is_active:
        raise Forbidden("this admin account has been disabled")
    if admin.mfa_required and not verify_totp(admin.mfa_secret, payload.totp_code):
        raise Unauthorized("invalid MFA code")

    AuditRepository(db).record(
        action="admin.login", actor_id=admin.id, actor_type="admin", target_type="admin", target_id=admin.id
    )
    db.commit()
    token = create_access_token(admin.id, audience=ADMIN_AUDIENCE, mfa=True)
    return TokenResponse(access_token=token, expires_in=settings.admin_token_ttl_seconds)


@secure_router.get("/stats", response_model=PlatformStats)
def stats(db: Session = Depends(get_db)) -> PlatformStats:
    return admin_service.platform_stats(db)


@secure_router.get("/users", response_model=AdminUserList)
def users(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> AdminUserList:
    return admin_service.list_users(db, limit=limit, offset=offset)


@secure_router.post("/users/{user_id}/status", response_model=AdminUserRead)
def set_user_status(
    user_id: str,
    payload: SetUserActiveRequest,
    admin: AdminUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdminUserRead:
    return admin_service.set_user_active(db, admin=admin, user_id=user_id, is_active=payload.is_active)


@secure_router.get("/audit")
def audit(limit: int = Query(default=50, ge=1, le=200), db: Session = Depends(get_db)) -> dict:
    entries = AuditRepository(db).recent(limit=limit)
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
