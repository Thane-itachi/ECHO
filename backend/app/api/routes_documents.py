"""Documents: encrypted upload, encrypted download, owner-scoped throughout."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import current_user, get_cipher, get_db, get_document_store
from app.core.crypto import AnyCipher
from app.core.errors import NotFound
from app.db.models import User
from app.schemas import DocumentList, DocumentRead
from app.services.document_storage import DocumentStore
from app.services.documents import DocumentService

router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.get("", response_model=DocumentList)
def list_documents(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    cipher: AnyCipher = Depends(get_cipher),
    store: DocumentStore = Depends(get_document_store),
) -> DocumentList:
    return DocumentService(db, user.id, cipher=cipher, store=store).list(limit=limit, offset=offset)


@router.post("", response_model=DocumentRead, status_code=201)
async def upload_document(
    file: UploadFile = File(...),
    memory_id: str | None = Form(default=None),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    cipher: AnyCipher = Depends(get_cipher),
    store: DocumentStore = Depends(get_document_store),
) -> DocumentRead:
    service = DocumentService(db, user.id, cipher=cipher, store=store)
    # Read one byte past the limit so oversize uploads are rejected without buffering
    # arbitrary amounts of memory.
    data = await file.read(service.max_bytes + 1)
    return service.store(
        filename=file.filename or "document",
        data=data,
        content_type=file.content_type,
        memory_id=memory_id or None,
    )


@router.get("/{document_id}/download")
def download_document(
    document_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    cipher: AnyCipher = Depends(get_cipher),
    store: DocumentStore = Depends(get_document_store),
) -> Response:
    service = DocumentService(db, user.id, cipher=cipher, store=store)
    try:
        attachment, data = service.open(document_id)
    except FileNotFoundError as exc:
        raise NotFound("document file is missing from storage") from exc
    safe_name = attachment.filename.replace('"', "").replace("\n", "")
    return Response(
        content=data,
        media_type=attachment.content_type or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}"'},
    )


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    cipher: AnyCipher = Depends(get_cipher),
    store: DocumentStore = Depends(get_document_store),
) -> Response:
    DocumentService(db, user.id, cipher=cipher, store=store).delete(document_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
