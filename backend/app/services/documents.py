"""Documents: attachments stored encrypted on disk, owned by exactly one user.

The database keeps metadata (name, size, type, owner, optional memory link); the
bytes live outside the database, encrypted with the same per-user key as memory
content. A stolen `storage/` directory is therefore as useless as a stolen database:
without the master key there is nothing to read.

`storage_key` is generated server-side (`<owner>/<random>`), never taken from the
uploaded filename, so a filename like `../../etc/passwd` cannot escape the storage
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
from app.services.serializers import to_document_read


class DocumentService:
    def __init__(
        self,
        session: Session,
        owner_id: str,
        *,
        cipher: AnyCipher | None = None,
        storage_dir: str | Path | None = None,
        max_bytes: int | None = None,
    ) -> None:
        self.session = session
        self.owner_id = owner_id
        self.cipher = cipher or get_default_cipher()
        self.storage_dir = Path(storage_dir or settings.storage_dir)
        self.max_bytes = max_bytes or settings.max_upload_bytes
        self.documents = AttachmentRepository(session, owner_id)
        self.memories = MemoryRepository(session, owner_id, cipher=self.cipher)

    # ------------------------------------------------------------------ paths
    def _path(self, storage_key: str) -> Path:
        root = self.storage_dir.resolve()
        path = (root / storage_key).resolve()
        if root not in path.parents:
            raise PayloadTooLarge("invalid storage key")
        return path

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
        path = self._path(storage_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(self.cipher.encrypt_bytes(data, self.owner_id))

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
        path = self._path(attachment.storage_key)
        if path.exists():
            path.unlink()
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
        path = self._path(attachment.storage_key)
        if not path.exists():
            raise FileNotFoundError(attachment.storage_key)
        return attachment, self.cipher.decrypt_bytes(path.read_bytes(), self.owner_id)
