"""Memory extraction: turn a pasted note into *proposals*, never memories.

The extractor is deterministic and rule-based on purpose:

* it runs with no model provider, no network and no key, so it is testable and free;
* its output is a proposal row (`pending`), so a wrong extraction costs the user one
  "Reject" click instead of a corrupted vault;
* every proposal keeps the source sentence (`source_text`), so the user can always
  see what it was derived from, and `confidence` says how sure the rules were.

`extract_proposals()` is pure: text in, proposals out. The worker (`app/worker.py`)
owns persistence, so the extraction logic can be tested without a database and later
swapped for an LLM call without touching the queue.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.schemas import Category, ProposalCreate

# Word lists are plain data: adding a category cue is a one-line change, and the
# scoring loop below never needs editing.
CATEGORY_CUES: dict[str, tuple[str, ...]] = {
    "belongings": (
        "borrow", "borrowed", "lend", "lent", "return", "gave back", "laptop", "charger",
        "phone", "keys", "book", "umbrella", "mine", "my",
    ),
    "promises": (
        "promised", "promise", "will", "agreed", "said he would", "said she would",
        "supposed to", "owe", "swore",
    ),
    "money": ("invoice", "paid", "payment", "naira", "dollar", "refund", "owe", "cost", "price"),
    "maintenance": (
        "repair", "fixed", "fix", "plumber", "electrician", "service", "serviced", "boiler",
        "leak", "broken", "workshop", "mechanic",
    ),
    "people": ("birthday", "anniversary", "married", "sister", "brother", "mother", "father", "friend"),
    "work": ("meeting", "deadline", "project", "client", "manager", "office", "standup", "report"),
    "clients": ("client", "customer", "contract", "proposal", "quote", "vendor"),
    "documents": ("receipt", "certificate", "document", "contract", "form", "passport", "id card"),
    "plans": ("plan", "planning", "next week", "next month", "trip", "travel", "visit", "booked"),
    "events": ("yesterday", "last week", "met", "happened", "went", "came over"),
}
# `money` and `people` above are cues for categories that exist in the architecture;
# they map onto the closest stored category when scoring.

PROMISE_RE = re.compile(
    r"\b(promised? to|promised that|will|agreed to|is going to|said (?:he|she) would)\b", re.I
)
DATE_RE = re.compile(
    r"\b(today|tomorrow|tonight|yesterday|next week|next month|"
    r"monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
    r"by \w+|on \w+ \d{1,2}|\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?)\b",
    re.I,
)
NAME_RE = re.compile(r"\b([A-Z][a-z]{2,})\b")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")
MIN_WORDS = 3


@dataclass(frozen=True)
class Extracted:
    title: str
    content: str
    source_text: str
    category: str
    confidence: float
    cues: tuple[str, ...] = field(default=())

    def to_proposal(self) -> ProposalCreate:
        return ProposalCreate(
            title=self.title,
            content=self.content,
            source_text=self.source_text,
            category=Category(self.category),
            confidence=round(self.confidence, 2),
        )


def _score_categories(sentence: str) -> tuple[str, list[str]]:
    lowered = sentence.lower()
    best_category = "general"
    best_hits: list[str] = []
    for category, cues in CATEGORY_CUES.items():
        hits = [cue for cue in cues if cue in lowered]
        if len(hits) > len(best_hits):
            best_category, best_hits = category, hits
    if best_category in {"money", "people"}:
        # Not stored categories: fold them into the closest real one.
        best_category = "clients" if best_category == "money" else "people"
    return best_category, best_hits


MODAL_RE = re.compile(r"\b(promised|promises|promise|will|agreed|going to|said)\b", re.I)


def _truncate_words(text: str, limit: int = 90) -> str:
    """Cut at a word boundary: a title ending mid-word reads like a bug."""
    if len(text) <= limit:
        return text
    cut = text[: limit - 1].rstrip()
    if " " in cut:
        cut = cut[: cut.rfind(" ")]
    return f"{cut.rstrip(' ,;:-')}…"


def _title_for(sentence: str, *, person: str | None, is_promise: bool) -> str:
    """A short, readable title. Never rewrites a sentence that already states the fact.

    The earlier version glued "will" onto every promise, which produced titles like
    "Tuesday will tuesday: Chidi promised to fix the generator". The rule now is: keep
    the sentence, and only add the missing subject (!) when there is none.
    """
    text = re.sub(r"\s+", " ", sentence.strip().rstrip(".!?")).strip()
    if not text:
        return "Note"
    lowered = text.lower()

    if is_promise and not MODAL_RE.search(lowered):
        text = f"{person or 'Someone'} will {text[0].lower() + text[1:]}"
    elif person and person.lower() not in lowered:
        text = f"{person}: {text}"

    text = _truncate_words(text)
    return text[:1].upper() + text[1:]


def _guess_person(sentence: str, known_people: tuple[str, ...]) -> str | None:
    lowered = sentence.lower()
    for name in known_people:
        if name and name.lower() in lowered:
            return name
    # Fall back to the first capitalised word that is not the first word of the sentence.
    tokens = sentence.split()
    for token in tokens[1:]:
        match = NAME_RE.fullmatch(token.strip(",.:;"))
        if match and match.group(1).lower() not in {"echo", "i", "the"}:
            return match.group(1)
    return None


def extract_proposals(text: str, *, known_people: tuple[str, ...] = ()) -> list[Extracted]:
    """Split the note into sentences and propose the ones that carry information."""
    proposals: list[Extracted] = []
    seen: set[str] = set()

    for raw in SENTENCE_SPLIT_RE.split(text):
        sentence = re.sub(r"\s+", " ", raw or "").strip()
        if not sentence:
            continue
        words = sentence.split()
        if len(words) < MIN_WORDS:
            continue
        key = " ".join(word.lower() for word in words[:8])
        if key in seen:
            continue
        seen.add(key)

        category, cues = _score_categories(sentence)
        person = _guess_person(sentence, known_people)
        is_promise = bool(PROMISE_RE.search(sentence))
        has_date = bool(DATE_RE.search(sentence))

        confidence = 0.45 + 0.1 * min(len(cues), 3) + (0.1 if is_promise else 0.0) + (0.1 if has_date else 0.0)
        if category == "general" and not cues:
            confidence = min(confidence, 0.5)

        proposals.append(
            Extracted(
                title=_title_for(sentence, person=person, is_promise=is_promise),
                content=sentence,
                source_text=sentence,
                category=category,
                confidence=min(confidence, 0.9),
                cues=tuple(cues),
            )
        )
    return proposals


def extract_reminder_hint(text: str) -> str | None:
    """The date phrase a reminder could be built from, if the note has one."""
    match = DATE_RE.search(text)
    return match.group(0) if match else None
