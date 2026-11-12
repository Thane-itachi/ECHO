"""The ownership boundary (fix #1).

`OwnedRepository` physically cannot build a query without an owner scope: the
constructor rejects a missing/blank owner, `scoped_query()` is the only query
builder on the table, and `add()` refuses to persist an entity whose `user_id`
does not match the scope. Every private repository extends this class.
"""
from __future__ import annotations

from typing import Any, ClassVar, Generic, TypeVar

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.core.errors import NotFound

ModelT = TypeVar("ModelT")


class OwnerScopeError(RuntimeError):
    """A repository was constructed with no owner scope. This is a programming error."""


class OwnershipViolation(RuntimeError):
    """An entity from a different owner was pushed through a scoped repository."""


def require_owner_id(owner_id: str | None) -> str:
    if not isinstance(owner_id, str) or not owner_id.strip():
        raise OwnerScopeError("owned repositories require a non-empty owner_id")
    return owner_id


class OwnedRepository(Generic[ModelT]):
    model: ClassVar[Any] = None

    def __init__(self, session: Session, owner_id: str) -> None:
        self.owner_id = require_owner_id(owner_id)
        self.session = session

    # ------------------------------------------------------------------ queries
    def scoped_query(self) -> Select:
        if self.model is None:  # pragma: no cover - subclass contract
            raise NotImplementedError("OwnedRepository subclasses must set `model`")
        return select(self.model).where(self.model.user_id == self.owner_id)

    def get(self, entity_id: str) -> ModelT | None:
        return self.session.scalars(self.scoped_query().where(self.model.id == entity_id)).one_or_none()

    def require(self, entity_id: str) -> ModelT:
        entity = self.get(entity_id)
        if entity is None:
            # Always 404, never 403: the caller must not learn that the row exists.
            raise NotFound("not found")
        return entity

    def count(self) -> int:
        stmt = select(func.count()).select_from(self.model).where(self.model.user_id == self.owner_id)
        return int(self.session.scalar(stmt) or 0)

    def list_page(self, statement: Select, *, limit: int, offset: int) -> tuple[list[ModelT], int]:
        total = int(self.session.scalar(select(func.count()).select_from(statement.subquery())) or 0)
        rows = list(self.session.scalars(statement.limit(limit).offset(offset)))
        return rows, total

    # ------------------------------------------------------------------- writes
    def add(self, entity: ModelT) -> ModelT:
        if getattr(entity, "user_id", None) != self.owner_id:
            raise OwnershipViolation(
                f"refusing to persist an entity owned by {getattr(entity, 'user_id', None)!r} "
                f"through a repository scoped to {self.owner_id!r}"
            )
        self.session.add(entity)
        return entity

    def delete(self, entity: ModelT) -> None:
        if getattr(entity, "user_id", None) != self.owner_id:
            raise OwnershipViolation("refusing to delete an entity belonging to another owner")
        self.session.delete(entity)
