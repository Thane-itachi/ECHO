"""Documents: attachments stored encrypted outside the database, owned by one user.

The database keeps metadata (name, size, type, owner, optional memory link); the
bytes live outside the database, encrypted with the same per-user key as memory
content. A stolen `storage/` directory is therefore as useless as a stolen database:
without the master key there is nothing to read.

`storage_key` is generated server-side (`<owner>/<random>`), never taken from the
uploaded filename, so a filename like `../../etc/passwd` cannot escape a local storage
directory *and* two users with the same filename cannot collide.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.crypto import AnyCipher, get_default_cipher
from app.core.errors import PayloadTooLarge
from app.db.models import Attachment
from app.repositories.memories import AttachmentRepository, MemoryRepository
from app.schemas import DocumentList, DocumentRead
from app.services.document_storage import DocumentStore, LocalStore
from app.services.serializers import to_document_read


class DocumentService:
    def __init__(
        self,
        session: Session,
        owner_id: str,
        *,
        cipher: AnyCipher | None = None,
        storage_dir: str | Path | None = None,
        store: DocumentStore | None = None,
        max_bytes: int | None = None,
    ) -> None:
        self.session = session
        self.owner_id = owner_id
        self.cipher = cipher or get_default_cipher()
        # A store, not a directory: on a serverless deploy the bytes go to object
        # storage and there is no directory to name. Named `blobs` because `store` is
        # already the method that takes an upload.
        self.blobs = store or LocalStore(storage_dir or settings.storage_dir)
        self.max_bytes = max_bytes or settings.max_upload_bytes
        self.documents = AttachmentRepository(session, owner_id)
        self.memories = MemoryRepository(session, owner_id, cipher=self.cipher)

    # ------------------------------------------------------------------ writes
    def store(
        self,
        *,
        filename: str,
        data: bytes,
        content_type: str | None,
        memory_id: str | None = None,
    ) -> DocumentRead:
        if len(data) > self.max_bytes:
            raise PayloadTooLarge(f"file is larger than the {self.max_bytes // (1024 * 1024)} MB limit")
        if not data:
            raise PayloadTooLarge("file is empty")
        if memory_id:
            self.memories.require(memory_id)

        storage_key = f"{self.owner_id}/{uuid.uuid4().hex}"
        self.blobs.put(storage_key, self.cipher.encrypt_bytes(data, self.owner_id))

        attachment = self.documents.create(
            filename=Path(filename or "document").name[:255],
            storage_key=storage_key,
            size_bytes=len(data),
            content_type=(content_type or "application/octet-stream")[:128],
            memory_id=memory_id,
        )
        self.session.commit()
        return to_document_read(attachment)

    def delete(self, document_id: str) -> None:
        attachment = self.documents.require(document_id)
        self.blobs.delete(attachment.storage_key)
        self.documents.delete(attachment)
        self.session.commit()

    # ------------------------------------------------------------------- reads
    def list(self, *, limit: int = 50, offset: int = 0) -> DocumentList:
        rows, total = self.documents.search(limit=limit, offset=offset)
        return DocumentList(
            items=[to_document_read(row) for row in rows], total=total, limit=limit, offset=offset
        )

    def list_for_memory(self, memory_id: str) -> DocumentList:
        self.memories.require(memory_id)
        rows = self.documents.list_for_memory(memory_id)
        return DocumentList(items=[to_document_read(row) for row in rows], total=len(rows), limit=len(rows), offset=0)

    def open(self, document_id: str) -> tuple[Attachment, bytes]:
        attachment = self.documents.require(document_id)
        raw = self.blobs.get(attachment.storage_key)  # FileNotFoundError if it is gone
        return attachment, self.cipher.decrypt_bytes(raw, self.owner_id)
