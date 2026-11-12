"""Ask ECHO: grounded answers over the user's own vault, with citations.

This is deliberately two layers:

* retrieval - the blind index finds candidate memories (see `BlindIndex`);
* composition - `AnswerComposer` turns those memories into a sentence with citation
  markers. The default composer is **extractive**: it quotes what the user stored and
  never invents facts it cannot point at.

`ExtractiveComposer` is the honest default, not a placeholder: with no model provider
configured, a template that quotes the source beats a small model that hallucinates.
A future `LLMComposer` (behind `ECHO_LLM_*` settings) implements the same
`compose(question, memories) -> (answer, mode)` contract; the API contract does not
change, and `mode` in the response says which one answered, so a client can never
mistake one for the other.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.orm import Session

from app.core.crypto import AnyCipher, BlindIndex, get_default_cipher
from app.db.models import Memory
from app.repositories.memories import MemoryRepository, PersonRepository
from app.schemas import AskResponse, Citation

MAX_CITATIONS = 4
MAX_ANSWER_SENTENCES = 3


@dataclass(frozen=True)
class Retrieved:
    memory: Memory
    title: str
    content: str


class AnswerComposer(Protocol):
    mode: str

    def compose(self, question: str, retrieved: list[Retrieved], *, person: str | None) -> str: ...


def _sentences(text: str, limit: int = MAX_ANSWER_SENTENCES) -> list[str]:
    clean = re.sub(r"\s+", " ", text).strip()
    if not clean:
        return []
    parts = re.split(r"(?<=[.!?])\s+", clean)
    return [part.strip() for part in parts if part.strip()][:limit]


class ExtractiveComposer:
    """Quotes the stored memories, with [n] markers pointing at the citation list."""

    mode = "extractive"

    def compose(self, question: str, retrieved: list[Retrieved], *, person: str | None) -> str:
        if not retrieved:
            return (
                "Nothing in your vault matches that yet. If you tell me, I can store it: "
                "try a capture like \"the plumber is coming Friday morning\"."
            )

        lines: list[str] = []
        intro = f"About {person}: " if person else ""
        for index, item in enumerate(retrieved, start=1):
            sentences = _sentences(item.content, limit=2)
            body = " ".join(sentences) if sentences else item.title
            if index == 1:
                lines.append(f"{intro}{item.title}. {body} [{index}]")
            else:
                lines.append(f"Also related: {item.title} — {body} [{index}]")
        return "\n".join(lines)


class AskService:
    def __init__(
        self,
        session: Session,
        owner_id: str,
        *,
        cipher: AnyCipher | None = None,
        composer: AnswerComposer | None = None,
    ) -> None:
        self.session = session
        self.owner_id = owner_id
        self.cipher = cipher or get_default_cipher()
        self.memories = MemoryRepository(session, owner_id, cipher=self.cipher)
        self.people = PersonRepository(session, owner_id, cipher=self.cipher)
        self.composer = composer or ExtractiveComposer()

    # --------------------------------------------------------------- retrieval
    def _retrieve(self, question: str) -> tuple[list[Retrieved], str | None]:
        rows, _ = self.memories.search(q=question, limit=MAX_CITATIONS)
        if not rows:
            # Forgiving second pass: any single word. "Who borrowed the laptop?" should
            # still find "John borrowed my laptop" when the filler words do not match.
            longest = sorted(BlindIndex.words(question), key=len, reverse=True)[:1]
            if longest:
                rows, _ = self.memories.search(q=longest[0], limit=MAX_CITATIONS)

        person = self._mentioned_person(question)
        if not rows and person:
            rows, _ = self.memories.search(q=person, limit=MAX_CITATIONS)

        return [
            Retrieved(memory=row, title=self.memories.read_title(row), content=self.memories.read_content(row))
            for row in rows
        ], person

    def _mentioned_person(self, question: str) -> str | None:
        lowered = question.lower()
        for person in self.people.search(limit=100)[0]:
            if person.name and person.name.lower() in lowered:
                return person.name
        return None

    # ------------------------------------------------------------------- answer
    def ask(self, question: str) -> AskResponse:
        retrieved, person = self._retrieve(question)
        answer = self.composer.compose(question, retrieved, person=person)
        return AskResponse(
            question=question,
            answer=answer,
            citations=[
                Citation(memory_id=item.memory.id, title=item.title, created_at=item.memory.created_at)
                for item in retrieved
            ],
            mode=getattr(self.composer, "mode", "extractive"),
            matched=len(retrieved),
        )
