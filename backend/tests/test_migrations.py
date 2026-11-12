"""The migration baseline and the models must describe the same database.

Autogenerate drifts silently: someone adds a column to `models.py`, forgets the
migration, and production fails on a query that works locally. This test upgrades a
fresh database to `head` and compares it to `Base.metadata`, so drift is a red test
rather than a production incident.
"""
from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from app.db.models import Base

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def test_alembic_head_matches_the_models(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{tmp_path}/migrated.db"
    monkeypatch.setenv("ECHO_DATABASE_URL", url)

    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    command.upgrade(config, "head")

    engine = create_engine(url)
    try:
        inspector = inspect(engine)
        migrated = {
            table: {column["name"] for column in inspector.get_columns(table)}
            for table in inspector.get_table_names()
            if table != "alembic_version"
        }
    finally:
        engine.dispose()

    expected = {
        name: {column.name for column in table.columns} for name, table in Base.metadata.tables.items()
    }
    assert migrated == expected
