"""Ask ECHO: retrieval + a grounded answer with citations."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import current_user, get_cipher, get_db, get_llm
from app.core.crypto import AnyCipher
from app.db.models import User
from app.schemas import AskRequest, AskResponse
from app.services.ask import AskService

router = APIRouter(prefix="/api/ask", tags=["ask"])


@router.post("", response_model=AskResponse)
def ask(
    payload: AskRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    cipher: AnyCipher = Depends(get_cipher),
    llm=Depends(get_llm),
) -> AskResponse:
    """Answer from the caller's own vault only, and cite what was used.

    `mode` is "extractive" when no model provider is configured: the answer quotes
    stored memories. With one, it is "generated" and the model writes the sentence over
    those same notes, with every claim carrying a citation marker. Either way the
    citations come from retrieval, never from the model.
    """
    return AskService(db, user.id, cipher=cipher, llm=llm).ask(payload.question)
