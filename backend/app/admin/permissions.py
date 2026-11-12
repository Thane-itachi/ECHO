"""Admin roles and the permission matrix.

Three roles, deliberately few:

* `founder`        - the owner of the platform. Everything, including creating and
                     disabling other administrators and break-glass access.
* `platform_admin` - runs the platform day to day: user accounts, audit, analytics,
                     system health. Cannot create or disable administrators.
* `support_admin`  - read-only triage: see accounts and audit, nothing that writes.

The matrix is data, and permission names are checked in one place, so "who can do
what" is reviewable in a diff instead of scattered `if admin.role == ...` branches.
An unknown role has no permissions at all, which is the safe default: adding a role
to the database without teaching it here locks it out instead of granting it
everything.
"""
from __future__ import annotations

from fastapi import Depends

from app.admin.deps import require_admin
from app.core.errors import Forbidden
from app.db.models import ADMIN_ROLES, AdminUser

FOUNDER = "founder"
PLATFORM_ADMIN = "platform_admin"
SUPPORT_ADMIN = "support_admin"

USERS_READ = "users:read"
USERS_WRITE = "users:write"
ADMINS_READ = "admins:read"
ADMINS_WRITE = "admins:write"
AUDIT_READ = "audit:read"
STATS_READ = "stats:read"
SYSTEM_READ = "system:read"
SECURITY_READ = "security:read"
EMERGENCY_ACCESS = "emergency:access"

ALL_PERMISSIONS: frozenset[str] = frozenset(
    {
        USERS_READ,
        USERS_WRITE,
        ADMINS_READ,
        ADMINS_WRITE,
        AUDIT_READ,
        STATS_READ,
        SYSTEM_READ,
        SECURITY_READ,
        EMERGENCY_ACCESS,
    }
)

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    FOUNDER: ALL_PERMISSIONS,
    PLATFORM_ADMIN: frozenset(
        {USERS_READ, USERS_WRITE, ADMINS_READ, AUDIT_READ, STATS_READ, SYSTEM_READ, SECURITY_READ}
    ),
    SUPPORT_ADMIN: frozenset({USERS_READ, AUDIT_READ, STATS_READ}),
}


def permissions_for(role: str) -> frozenset[str]:
    return ROLE_PERMISSIONS.get(role, frozenset())


def has_permission(role: str, permission: str) -> bool:
    return permission in permissions_for(role)


def is_known_role(role: str) -> bool:
    return role in ADMIN_ROLES


def require_permission(permission: str):
    """Dependency factory: authenticated admin **and** the permission it needs.

    Denial is 403 with the permission name, never a silent filter: a support admin
    who tries to disable an account should learn why it failed.
    """

    def dependency(admin: AdminUser = Depends(require_admin)) -> AdminUser:
        if not has_permission(admin.role, permission):
            raise Forbidden(f"role {admin.role!r} is not allowed to {permission}")
        return admin

    return dependency
