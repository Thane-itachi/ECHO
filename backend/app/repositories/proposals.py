from __future__ import annotations

from typing import Any

from app.core.crypto import ContentCipher, NullCipher, get_default_cipher
from app.core.time import utcnow
from app.db.models import MemoryProposal
from app.repositories.base import OwnedRepository, OwnershipViolation

_UNSET: Any = object()


class ProposalRepository(OwnedRepository[MemoryProposal]):
    model = MemoryProposal

    def __init__(self, session, owner_id: str, *, cipher: ContentCipher | NullCipher | None = None) -> None:
        super().__init__(session, owner_id)
        self.cipher = cipher or get_default_cipher()

    def read_title(self, proposal: MemoryProposal) -> str:
        return self.cipher.decrypt(proposal.title_enc, self.owner_id)

    def read_content(self, proposal: MemoryProposal) -> str:
        return self.cipher.decrypt(proposal.content_enc, self.owner_id)

    def read_source_text(self, proposal: MemoryProposal) -> str:
        return self.cipher.decrypt(proposal.source_text_enc, self.owner_id)

    def create(
        self,
        *,
        title: str,
        content: str,
        source_text: str,
        category: str = "general",
        confidence: float | None = None,
    ) -> MemoryProposal:
        proposal = MemoryProposal(
            user_id=self.owner_id,
            status="pending",
            title_enc=self.cipher.encrypt(title, self.owner_id),
            content_enc=self.cipher.encrypt(content, self.owner_id),
            source_text_enc=self.cipher.encrypt(source_text, self.owner_id),
            category=category,
            confidence=confidence,
        )
        return self.add(proposal)

    def decide(self, proposal: MemoryProposal, *, status: str, decided_by: str, memory_id: str | None = None) -> MemoryProposal:
        if proposal.user_id != self.owner_id:
            raise OwnershipViolation("refusing to decide a proposal belonging to another owner")
        proposal.status = status
        proposal.decided_at = utcnow()
        proposal.decided_by = decided_by
        if memory_id is not None:
            proposal.memory_id = memory_id
        return proposal

    def list_by_status(self, *, status: str | None = None, limit: int = 50, offset: int = 0):
        stmt = self.scoped_query()
        if status:
            stmt = stmt.where(MemoryProposal.status == status)
        return self.list_page(stmt.order_by(MemoryProposal.created_at.desc()), limit=limit, offset=offset)
