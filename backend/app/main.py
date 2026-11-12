"""ECHO API entry point.

Run:  uvicorn app.main:app --reload
Tests build their own app with `create_app(session_factory=..., cipher=...)`.
"""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.admin import routes as admin_routes
from app.api import (
    routes_ask,
    routes_auth,
    routes_captures,
    routes_documents,
    routes_memories,
    routes_proposals,
    routes_reminders,
)
from app.core.config import settings
from app.core.crypto import build_cipher, set_process_cipher
from app.services.llm import build_llm, describe as describe_llm
from app.core.errors import register_exception_handlers
from app.db.session import build_engine, build_session_factory, create_all

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("echo")


def create_app(*, session_factory=None, cipher=None, llm=None) -> FastAPI:
    app = FastAPI(
        title="ECHO API",
        version="0.1.0",
        description="Personal memory engine. Every row is owned by exactly one user.",
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None,
        openapi_url=None if settings.is_production else "/openapi.json",
    )

    engine = None
    if session_factory is None:
        engine = build_engine()
        create_all(engine)  # dev bootstrap; production uses Alembic migrations
        session_factory = build_session_factory(engine)

    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.cipher = cipher or build_cipher()
    # Column types (sealed admin secrets) cannot see a request, so the process keeps
    # the cipher too. One process, one data key.
    set_process_cipher(app.state.cipher)
    app.state.storage_dir = settings.storage_dir
    # Optional model provider. `None` is a supported configuration: extractive
    # answers and rule-based extraction, with no network call anywhere in the path.
    app.state.llm = llm or build_llm()

    register_exception_handlers(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )

    for router in (
        routes_auth.router,
        routes_memories.router,
        routes_memories.people_router,
        routes_proposals.router,
        routes_reminders.router,
        routes_ask.router,
        routes_captures.router,
        routes_documents.router,
        admin_routes.public_router,
        admin_routes.secure_router,
    ):
        app.include_router(router)

    @app.get("/healthz", tags=["ops"])
    def healthz() -> dict:
        return {"status": "ok", "env": settings.env}

    logger.info("ECHO api ready (env=%s)", settings.env)
    logger.info("%s", describe_llm())
    return app


app = create_app()
