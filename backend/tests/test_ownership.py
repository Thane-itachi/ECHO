"""The repository layer refuses to work without an owner scope, at construction."""
from __future__ import annotations

import pytest

from app.core.crypto import NullCipher
from app.db.models import Memory
from app.repositories.base import OwnerScopeError, OwnershipViolation
from app.repositories.memories import MemoryRepository


@pytest.mark.parametrize("bad_owner", [None, "", "   "])
def test_repository_requires_owner_scope(session_factory, bad_owner):
    with session_factory() as session:
        with pytest.raises(OwnerScopeError):
            MemoryRepository(session, bad_owner, cipher=NullCipher())


def test_repository_refuses_cross_owner_insert(session_factory):
    with session_factory() as session:
        repo = MemoryRepository(session, "owner-a", cipher=NullCipher())
        stray = Memory(user_id="owner-b", title="x", content_enc="p1:x", search_text="x")
        with pytest.raises(OwnershipViolation):
            repo.add(stray)


def test_repository_refuses_cross_owner_delete(session_factory):
    with session_factory() as session:
        repo = MemoryRepository(session, "owner-a", cipher=NullCipher())
        stray = Memory(user_id="owner-b", title="x", content_enc="p1:x", search_text="x")
        with pytest.raises(OwnershipViolation):
            repo.delete(stray)


def test_scoped_query_always_filters_by_owner(session_factory):
    with session_factory() as session:
        repo = MemoryRepository(session, "owner-a", cipher=NullCipher())
        sql = str(repo.scoped_query())
        assert "memories.user_id" in sql
