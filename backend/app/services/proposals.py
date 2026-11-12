"""Proposals (fix #5): AI output is a state machine, not a modal.

pending -> approved (creates exactly one memory) | rejected.
Approving twice is a 409, not a duplicated memory.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.crypto import ContentCipher, NullCipher, get_default_cipher
from app.core.errors import Conflict
from app.core.time import utcnow
from app.db.models import MemoryProposal
from app.repositories.memories import MemoryRepository
from app.repositories.proposals import ProposalRepository
from app.repositories.system import AuditRepository
from app.schemas import ProposalCreate, ProposalDecision, ProposalList, ProposalRead
from app.services.serializers import to_memory_read, to_proposal_read


class ProposalService:
    def __init__(self, session: Session, owner_id: str, *, cipher: ContentCipher | NullCipher | None = None) -> None:
        self.session = session
        self.owner_id = owner_id
        self.cipher = cipher or get_default_cipher()
        self.proposals = ProposalRepository(session, owner_id, cipher=self.cipher)
        self.memories = MemoryRepository(session, owner_id, cipher=self.cipher)
        self.audit = AuditRepository(session)

    def create(self, payload: ProposalCreate) -> ProposalRead:
        proposal = self.proposals.create(
            title=payload.title,
            content=payload.content,
            source_text=payload.source_text,
            category=payload.category.value,
            confidence=payload.confidence,
        )
        self.session.flush()
        self.audit.record(
            action="proposal.created",
            actor_id=self.owner_id,
            actor_type="user",
            target_type="proposal",
            target_id=proposal.id,
            detail={"confidence": payload.confidence},
        )
        self.session.commit()
        return to_proposal_read(proposal, self.proposals)

    def get(self, proposal_id: str) -> ProposalRead:
        return to_proposal_read(self.proposals.require(proposal_id), self.proposals)

    def list(self, *, status: str | None = None, limit: int = 50, offset: int = 0) -> ProposalList:
        rows, total = self.proposals.list_by_status(status=status, limit=limit, offset=offset)
        return ProposalList(
            items=[to_proposal_read(row, self.proposals) for row in rows],
            total=total,
            limit=limit,
            offset=offset,
        )

    def _decide(self, proposal: MemoryProposal, *, status: str) -> ProposalDecision:
        if proposal.status != "pending":
            raise Conflict(f"proposal is already {proposal.status}")
        memory = None
        if status == "approved":
            memory = self.memories.create(
                title=proposal.title,
                content=self.proposals.read_content(proposal),
                category=proposal.category,
                source="ai_extraction",
                confidence=proposal.confidence,
            )
            self.session.flush()
            # Same audit trail whether a memory arrives via the API or via approval.
            self.audit.record(
                action="memory.created",
                actor_id=self.owner_id,
                actor_type="user",
                target_type="memory",
                target_id=memory.id,
                detail={"source": "ai_extraction", "via": "proposal", "proposal_id": proposal.id},
            )
        self.proposals.decide(
            proposal,
            status=status,
            decided_by=self.owner_id,
            memory_id=memory.id if memory else None,
        )
        self.audit.record(
            action=f"proposal.{status}",
            actor_id=self.owner_id,
            actor_type="user",
            target_type="proposal",
            target_id=proposal.id,
            detail={"memory_id": memory.id if memory else None},
        )
        self.session.commit()
        return ProposalDecision(
            proposal=to_proposal_read(proposal, self.proposals),
            memory=to_memory_read(memory, self.memories) if memory else None,
        )

    def approve(self, proposal_id: str) -> ProposalDecision:
        return self._decide(self.proposals.require(proposal_id), status="approved")

    def reject(self, proposal_id: str) -> ProposalDecision:
        return self._decide(self.proposals.require(proposal_id), status="rejected")


def proposals_pending_count(session: Session, owner_id: str) -> int:
    from sqlalchemy import func, select

    stmt = (
        select(func.count())
        .select_from(MemoryProposal)
        .where(MemoryProposal.user_id == owner_id, MemoryProposal.status == "pending")
    )
    return int(session.scalar(stmt) or 0)
