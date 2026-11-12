"""Structural boundary (fix #3): admin code cannot reach user data or memory content.

This is the test the review said would otherwise erode in month three. It parses the
import graph instead of trusting code review.
"""
from __future__ import annotations

import ast
from pathlib import Path

ADMIN_DIR = Path(__file__).resolve().parents[1] / "app" / "admin"

FORBIDDEN_MODULES = {
    "app.repositories.memories",
    "app.repositories.proposals",
    "app.repositories.base",
    "app.services.memories",
    "app.services.proposals",
    "app.services.reminders",
    "app.services.serializers",
    "app.api.deps",  # admin has its own dependency; it never borrows the user one
    "app.api.routes_auth",
    "app.api.routes_memories",
    "app.api.routes_proposals",
    "app.api.routes_reminders",
}

FORBIDDEN_NAMES = {"ContentCipher", "NullCipher", "MemoryRepository", "MemoryService"}


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                found.add(node.module)
            for alias in node.names:
                found.add(alias.name)
    return found


def test_admin_package_exports_exist():
    assert (ADMIN_DIR / "routes.py").exists()
    assert (ADMIN_DIR / "service.py").exists()


def test_admin_never_imports_user_data_layer():
    offenders = {}
    for path in ADMIN_DIR.rglob("*.py"):
        imported = _imports(path)
        bad = imported & (FORBIDDEN_MODULES | FORBIDDEN_NAMES)
        if bad:
            offenders[path.name] = sorted(bad)
    assert offenders == {}, f"admin package reaches into user data: {offenders}"


def test_admin_has_its_own_dependency_module():
    from app.admin import deps

    assert hasattr(deps, "require_admin")
    assert not hasattr(deps, "current_user"), "admin must not be able to borrow the user gate"


def test_admin_routes_are_gated_by_require_admin():
    from app.admin.deps import require_admin
    from app.admin.routes import secure_router

    assert secure_router.dependencies, "secure_router must carry a router-level dependency"
    gate_callables = {dep.dependency for dep in secure_router.dependencies}
    assert require_admin in gate_callables

    for route in secure_router.routes:
        assert route.path.startswith("/admin")


def test_public_admin_router_only_exposes_login_and_enrolment():
    """No unauthenticated admin endpoint may be added without thinking about it.

    The allowlist is the login plus the three enrolment-link routes, and those three
    carry a 32-byte single-use token in the path: the token *is* the credential. Every
    other admin route sits behind `require_admin` and is still checked above.
    """
    from app.admin.routes import public_router

    paths = {route.path for route in public_router.routes}
    assert paths == {
        "/admin/auth/token",
        "/admin/auth/enrol/{token}",
        "/admin/auth/enrol/{token}/confirm",
    }
