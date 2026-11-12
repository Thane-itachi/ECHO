from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import current_user, get_cipher, get_db
from app.core.crypto import ContentCipher, NullCipher
from app.db.models import User
from app.schemas import (
    Category,
    LinkCreate,
    LinkList,
    MemoryCreate,
    MemoryList,
    MemoryRead,
    MemoryUpdate,
    PersonCreate,
    PersonList,
    PersonRead,
)
from app.services.memories import MemoryService, PersonService

router = APIRouter(prefix="/api/memories", tags=["memories"])


def _service(user: User, db: Session, cipher) -> MemoryService:
    return MemoryService(db, user.id, cipher=cipher)


@router.get("", response_model=MemoryList)
def list_memories(
    q: str | None = Query(default=None, max_length=200),
    category: Category | None = Query(default=None),
    include_archived: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    cipher: ContentCipher | NullCipher = Depends(get_cipher),
) -> MemoryList:
    return _service(user, db, cipher).list(
        q=q,
        category=category.value if category else None,
        include_archived=include_archived,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=MemoryRead, status_code=201)
def create_memory(
    payload: MemoryCreate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    cipher: ContentCipher | NullCipher = Depends(get_cipher),
) -> MemoryRead:
    return _service(user, db, cipher).create(payload)


@router.get("/{memory_id}", response_model=MemoryRead)
def get_memory(
    memory_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    cipher: ContentCipher | NullCipher = Depends(get_cipher),
) -> MemoryRead:
    return _service(user, db, cipher).get(memory_id)


@router.patch("/{memory_id}", response_model=MemoryRead)
def update_memory(
    memory_id: str,
    payload: MemoryUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    cipher: ContentCipher | NullCipher = Depends(get_cipher),
) -> MemoryRead:
    return _service(user, db, cipher).update(memory_id, payload)


@router.post("/{memory_id}/archive", response_model=MemoryRead)
def archive_memory(
    memory_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    cipher: ContentCipher | NullCipher = Depends(get_cipher),
) -> MemoryRead:
    return _service(user, db, cipher).set_archived(memory_id, archived=True)


@router.post("/{memory_id}/restore", response_model=MemoryRead)
def restore_memory(
    memory_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    cipher: ContentCipher | NullCipher = Depends(get_cipher),
) -> MemoryRead:
    return _service(user, db, cipher).set_archived(memory_id, archived=False)


@router.get("/{memory_id}/links", response_model=LinkList)
def list_links(
    memory_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    cipher: ContentCipher | NullCipher = Depends(get_cipher),
) -> LinkList:
    return _service(user, db, cipher).list_links(memory_id)


@router.post("/{memory_id}/links", response_model=LinkList, status_code=201)
def link_memory(
    memory_id: str,
    payload: LinkCreate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    cipher: ContentCipher | NullCipher = Depends(get_cipher),
) -> LinkList:
    return _service(user, db, cipher).link(memory_id, payload)


@router.delete("/{memory_id}/links/{other_id}", response_model=LinkList)
def unlink_memory(
    memory_id: str,
    other_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    cipher: ContentCipher | NullCipher = Depends(get_cipher),
) -> LinkList:
    return _service(user, db, cipher).unlink(memory_id, other_id)


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_memory(
    memory_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    cipher: ContentCipher | NullCipher = Depends(get_cipher),
) -> Response:
    _service(user, db, cipher).delete(memory_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


people_router = APIRouter(prefix="/api/people", tags=["people"])


@people_router.get("", response_model=PersonList)
def list_people(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    cipher: ContentCipher | NullCipher = Depends(get_cipher),
) -> PersonList:
    return PersonService(db, user.id, cipher=cipher).list(limit=limit, offset=offset)


@people_router.post("", response_model=PersonRead, status_code=201)
def create_person(
    payload: PersonCreate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    cipher: ContentCipher | NullCipher = Depends(get_cipher),
) -> PersonRead:
    return PersonService(db, user.id, cipher=cipher).create(payload)


@people_router.delete("/{person_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_person(
    person_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    cipher: ContentCipher | NullCipher = Depends(get_cipher),
) -> Response:
    PersonService(db, user.id, cipher=cipher).delete(person_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
