"""The deploy files must describe the code, or the deploy is where you find out.

Vercel builds from the repository root, so two things live there that the backend does
not need: `requirements.txt` (what the function installs) and `vercel.json` (routing).
Both can drift silently, and drift here shows up as a production import error or a 404,
so they are asserted instead.
"""
from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BACKEND_REQUIREMENTS = REPO / "backend" / "requirements.txt"
DEPLOY_REQUIREMENTS = REPO / "requirements.txt"


def _pinned(path: Path) -> list[str]:
    return [
        line.strip()
        for line in path.read_text().splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def test_the_deploy_requirements_match_the_backend():
    """Vercel installs the root file; the backend keeps its own. They are the same list."""
    assert _pinned(DEPLOY_REQUIREMENTS) == _pinned(BACKEND_REQUIREMENTS)


def test_every_backend_dependency_is_pinned_by_a_floor():
    for line in _pinned(BACKEND_REQUIREMENTS):
        assert any(operator in line for operator in (">=", "==", "~=")), line


def test_vercel_routes_the_api_and_the_pages_separately():
    config = json.loads((REPO / "vercel.json").read_text())
    sources = [rule["source"] for rule in config["rewrites"]]

    assert "/api/(.*)" in sources, "the API would fall through to index.html"
    assert sources[-1] == "/(.*)" or sources[-1].startswith("/(.*)"), "the SPA fallback must come last"
    # The admin console has pages at /admin/users and an API at /admin/users; the page
    # must win for a navigation, or deep links render JSON.
    guarded = [
        rule
        for rule in config["rewrites"]
        if rule["source"].startswith("/admin/users") and "has" in rule
    ]
    assert guarded, "a deep link to /admin/users must not be answered by the API"
    assert config["outputDirectory"] == "web/dist"
    assert config["functions"]["api/index.py"]["includeFiles"] == "backend/**"


def test_the_cron_secret_endpoint_is_the_one_scheduled():
    config = json.loads((REPO / "vercel.json").read_text())
    assert [job["path"] for job in config["crons"]] == ["/api/internal/tick"]


def test_the_serverless_entry_point_builds_the_shared_app():
    """`api/index.py` must hand over the same app the tests and uvicorn use."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("vercel_entry", REPO / "api" / "index.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]

    from app.main import app as shared

    assert module.app is shared
