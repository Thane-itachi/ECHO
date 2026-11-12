"""Ask ECHO: retrieval + a grounded answer with citations."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import current_user, get_cipher, get_db
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
) -> AskResponse:
    """Answer from the caller's own vault only, and cite what was used.

    `mode` is "extractive" today: the answer quotes stored memories. It becomes
    "generated" only if a model provider is configured, so a client can always tell
    a quotation from a paraphrase.
    """
    return AskService(db, user.id, cipher=cipher).ask(payload.question)
