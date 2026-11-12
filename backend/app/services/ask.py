"""Ask ECHO: grounded answers over the user's own vault, with citations.

Two layers, deliberately separable:

* **retrieval** - the blind index finds candidate memories (see `BlindIndex`);
* **composition** - a composer turns those memories into prose with `[n]` markers that
  index the `citations` array the API returns.

There are two composers and the distinction is the whole point:

* `ExtractiveComposer` quotes the stored memories. It needs no key and cannot invent a
  fact, because every sentence it prints came out of the vault.
* `GeneratedComposer` lets a model write the sentence, but only over the retrieved notes,
  and only under a rule enforced *here* rather than asked for in a prompt: if the answer
  carries no usable citation, it is discarded and the extractive answer is used instead.
  A model that cannot point at a memory does not get to speak.

`AskResponse.mode` says which one answered ("generated" or "extractive"), so a client
can always tell a quotation from a paraphrase. A model outage, a timeout or a missing
key is not an error page: it is the extractive answer, and `mode` says so.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.orm import Session

from app.core.crypto import AnyCipher, BlindIndex, get_default_cipher
from app.db.models import Memory
from app.repositories.memories import MemoryRepository, PersonRepository
from app.schemas import AskResponse, Citation
from app.services.llm import LLMClient, LLMError

logger = logging.getLogger("echo.ask")

MAX_CITATIONS = 4
MAX_ANSWER_SENTENCES = 3
MAX_GENERATED_CHARS = 1200
MARKER_RE = re.compile(r"\[(\d{1,2})\]")

GENERATED_SYSTEM_PROMPT = """You answer questions about one person's own private notes.

Rules, in order:
1. Use only the numbered notes you are given. Never add outside knowledge, guesses or
   general advice.
2. End every factual claim with the marker of the note it came from, like [1] or [2].
   A sentence with no marker is a sentence you may not write.
3. If the notes do not answer the question, say so in one short sentence and stop.
4. At most three sentences. Plain, warm, direct. Do not mention "the notes" or repeat
   the question; just answer it."""


@dataclass(frozen=True)
class Retrieved:
    memory: Memory
    title: str
    content: str


@dataclass(frozen=True)
class Composed:
    """An answer plus what it stands on.

    `cited` is 1-based indices into `retrieved`; an empty tuple means "all of them",
    which is what the extractive composer means by design.
    """

    answer: str
    mode: str
    cited: tuple[int, ...] = ()


class AnswerComposer(Protocol):
    def compose(self, question: str, retrieved: list[Retrieved], *, person: str | None) -> Composed: ...


def _sentences(text: str, limit: int = MAX_ANSWER_SENTENCES) -> list[str]:
    clean = re.sub(r"\s+", " ", text).strip()
    if not clean:
        return []
    parts = re.split(r"(?<=[.!?])\s+", clean)
    return [part.strip() for part in parts if part.strip()][:limit]


class ExtractiveComposer:
    """Quotes the stored memories, with [n] markers pointing at the citation list."""

    mode = "extractive"

    def compose(self, question: str, retrieved: list[Retrieved], *, person: str | None) -> Composed:
        if not retrieved:
            return Composed(
                "Nothing in your vault matches that yet. If you tell me, I can store it: "
                'try a capture like "the plumber is coming Friday morning".',
                self.mode,
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
        return Composed("\n".join(lines), self.mode)


class GeneratedComposer:
    """A model writes the answer, over retrieved notes only, and must cite them.

    It never raises: anything that goes wrong (no client, a timeout, a refusal, an
    unusable answer) returns the extractive composition instead. The caller still
    validates the citations, so a model answer that cites nothing is caught even if
    the model was convincing.
    """

    mode = "generated"

    def __init__(self, llm: LLMClient, *, fallback: AnswerComposer | None = None) -> None:
        self.llm = llm
        self.fallback = fallback or ExtractiveComposer()

    @staticmethod
    def _notes(retrieved: list[Retrieved], question: str, person: str | None) -> str:
        blocks = []
        for index, item in enumerate(retrieved, start=1):
            created = item.memory.created_at.strftime("%Y-%m-%d") if item.memory.created_at else "date unknown"
            blocks.append(f"[{index}] {created} — {item.title}\n{item.content}")
        subject = f" The notes are about {person}." if person else ""
        return "Notes:\n\n" + "\n\n".join(blocks) + f"{subject}\n\nQuestion: {question}"

    def compose(self, question: str, retrieved: list[Retrieved], *, person: str | None) -> Composed:
        if not retrieved:
            # Nothing to ground on: a model here could only invent something.
            return self.fallback.compose(question, retrieved, person=person)

        try:
            answer = self.llm.complete(
                system=GENERATED_SYSTEM_PROMPT,
                user=self._notes(retrieved, question, person),
                max_tokens=400,
            )
        except LLMError as exc:
            # Deliberately one line, no question text: this runs per request.
            logger.warning("model answer unavailable (%s); answering extractively", exc)
            return self.fallback.compose(question, retrieved, person=person)

        if len(answer) > MAX_GENERATED_CHARS:
            logger.warning("model answer was implausibly long; answering extractively")
            return self.fallback.compose(question, retrieved, person=person)

        return Composed(answer, self.mode)


def _prune_citations(answer: str, cited: tuple[int, ...], count: int) -> tuple[str, list[int]]:
    """Renumber markers so `[n]` always indexes the citation list actually returned.

    A marker pointing outside the notes is removed rather than rendered: it is the
    visible symptom of the model citing something that does not exist. Renumbering keeps
    a two-note answer citing `[1] [2]` instead of `[2] [3]`.
    """
    used: list[int] = []
    for match in MARKER_RE.finditer(answer):
        index = int(match.group(1))
        if 1 <= index <= count and index not in used:
            used.append(index)
    if cited:
        used = [index for index in used if index in cited]
    if not used:
        return answer, []

    mapping = {old: new for new, old in enumerate(used, start=1)}

    def _swap(match: re.Match[str]) -> str:
        index = int(match.group(1))
        return f"[{mapping[index]}]" if index in mapping else ""

    rewritten = MARKER_RE.sub(_swap, answer)
    rewritten = re.sub(r"[ \t]{2,}", " ", rewritten)
    rewritten = re.sub(r"\s+([.,;:!?])", r"\1", rewritten).strip()
    return rewritten, used


class AskService:
    def __init__(
        self,
        session: Session,
        owner_id: str,
        *,
        cipher: AnyCipher | None = None,
        composer: AnswerComposer | None = None,
        llm: LLMClient | None = None,
    ) -> None:
        self.session = session
        self.owner_id = owner_id
        self.cipher = cipher or get_default_cipher()
        self.memories = MemoryRepository(session, owner_id, cipher=self.cipher)
        self.people = PersonRepository(session, owner_id, cipher=self.cipher)
        self.extractive = ExtractiveComposer()
        if composer is not None:
            self.composer = composer
        elif llm is not None:
            self.composer = GeneratedComposer(llm, fallback=self.extractive)
        else:
            self.composer = self.extractive

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

        composed = (
            self.composer.compose(question, retrieved, person=person)
            if retrieved
            else self.extractive.compose(question, retrieved, person=person)
        )
        answer, indices = _prune_citations(composed.answer, composed.cited, len(retrieved))
        mode = composed.mode

        if mode == "generated" and not indices:
            # The one rule a generated answer cannot break: no claim without a source.
            logger.warning("model answer cited nothing usable; answering extractively")
            composed = self.extractive.compose(question, retrieved, person=person)
            answer, indices = _prune_citations(composed.answer, composed.cited, len(retrieved))
            mode = "extractive"

        picked = [retrieved[index - 1] for index in (indices or range(1, len(retrieved) + 1))]
        return AskResponse(
            question=question,
            answer=answer,
            citations=[
                Citation(memory_id=item.memory.id, title=item.title, created_at=item.memory.created_at)
                for item in picked
            ],
            mode=mode,
            matched=len(retrieved),
        )
