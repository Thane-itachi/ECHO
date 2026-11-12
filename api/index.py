"""Vercel entry point: the whole ECHO API as one serverless function.

Vercel looks for a module in `api/` that exposes an ASGI `app`, so this file does one
thing: put `backend/` on the import path and hand over the same FastAPI application a
long-running deploy would run (`uvicorn app.main:app`). No second application is
defined here on purpose. A deploy that builds its own app is a deploy that drifts from
the one under test.

The background worker is not started here: a function is frozen between requests, so
the loop it used to own is `POST /api/internal/tick`, called by a schedule.
"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.main import app  # noqa: E402 - after the import path is set

# `app` is the ASGI callable Vercel's Python runtime looks for.
__all__ = ["app"]
