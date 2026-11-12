"""The optional model provider: bounded, grounded, and never load-bearing.

The failure these tests care about is not "the model is wrong" (it will be, sometimes).
It is "the model's output reached the user or the vault without a source". Every path
here checks that a model can add fluency but cannot add facts.
"""
from __future__ import annotations

import dataclasses
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.services.extraction import extract_proposals_with_model
from app.services.llm import DEFAULT_MODEL, LLMClient, LLMError, build_llm
from app.main import create_app

NOTE = (
    "Chidi promised to fix the generator on Friday. He borrowed my laptop last week. "
    "The generator is in the backyard shed."
)


class FakeLLM:
    """A provider that returns whatever the test says, and records what it was asked."""

    def __init__(self, *, text: str = "", payload: dict | None = None, error: Exception | None = None):
        self.text = text
        self.payload = payload
        self.error = error
        self.calls: list[dict] = []

    def complete(self, *, system: str, user: str, json_mode: bool = False, max_tokens: int = 700, temperature: float = 0.0) -> str:
        self.calls.append({"system": system, "user": user, "json_mode": json_mode})
        if self.error is not None:
            raise self.error
        return json.dumps(self.payload) if json_mode and self.payload is not None else self.text


def _configured(**overrides):
    """Settings with a provider configured, without touching the environment."""
    return dataclasses.replace(
        settings,
        llm_provider="openai",
        openai_api_key="sk-test-not-a-real-key",
        llm_extraction=True,
        **overrides,
    )


def _client(handler) -> LLMClient:
    return LLMClient(api_key="sk-test-not-a-real-key", model=DEFAULT_MODEL, transport=httpx.MockTransport(handler))


# ------------------------------------------------------------------ the client
def test_no_provider_configured_means_no_client():
    assert build_llm(dataclasses.replace(settings, llm_provider=None, openai_api_key=None)) is None
    # A key with no provider named is not enough: nothing is inferred.
    assert build_llm(dataclasses.replace(settings, llm_provider=None, openai_api_key="sk-test")) is None
    assert build_llm(_configured()) is not None


def test_the_request_is_what_openai_expects():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": "  hello  "}}]})

    answer = _client(handler).complete(system="be brief", user="who is John", json_mode=True)

    assert answer == "hello"
    assert seen["url"] == "https://api.openai.com/v1/chat/completions"
    assert seen["auth"] == "Bearer sk-test-not-a-real-key"
    assert seen["body"]["model"] == DEFAULT_MODEL
    assert seen["body"]["response_format"] == {"type": "json_object"}
    assert [m["role"] for m in seen["body"]["messages"]] == ["system", "user"]
    assert seen["body"]["messages"][0]["content"] == "be brief"


def test_a_provider_error_becomes_llm_error_without_leaking_the_key():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"message": "slow down"}})

    with pytest.raises(LLMError) as raised:
        _client(handler).complete(system="s", user="u")
    assert "sk-test-not-a-real-key" not in str(raised.value)


def test_a_transport_failure_becomes_llm_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("too slow", request=request)

    with pytest.raises(LLMError):
        _client(handler).complete(system="s", user="u")


def test_an_unusable_body_becomes_llm_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": []})

    with pytest.raises(LLMError):
        _client(handler).complete(system="s", user="u")


# ------------------------------------------------------- answers that cite or fall back
def _viz(client, create_memory, owner):
    first = create_memory(
        owner["headers"],
        title="John borrowed my laptop",
        content="He took the MacBook last week and promised to bring it back tomorrow.",
    )
    second = create_memory(
        owner["headers"],
        title="Generator is in the shed",
        content="The generator lives in the backyard shed behind the mango tree.",
    )
    return first, second


def test_a_generated_answer_is_used_when_it_cites(make_user, create_memory, session_factory):
    owner = make_user()
    first, _ = _viz(None, create_memory, owner)
    fake = FakeLLM(text="John borrowed your laptop and returns it tomorrow [1].")
    app = create_app(session_factory=session_factory, llm=fake)
    client = TestClient(app)

    body = client.post("/api/ask", json={"question": "who borrowed my laptop"}, headers=owner["headers"]).json()

    assert body["mode"] == "generated"
    assert "John" in body["answer"]
    # The marker indexes the citation list the client receives.
    assert body["answer"].rstrip().endswith("[1].")
    assert len(body["citations"]) == 1
    assert body["citations"][0]["memory_id"] == first["id"]
    assert fake.calls, "the model should have been asked"
    assert "[1]" in fake.calls[0]["user"] and "laptop" in fake.calls[0]["user"]


def test_an_uncited_model_answer_is_discarded(make_user, create_memory, session_factory):
    owner = make_user()
    _viz(None, create_memory, owner)
    fake = FakeLLM(text="John took your MacBook and will bring it back tomorrow.")
    app = create_app(session_factory=session_factory, llm=fake)

    body = TestClient(app).post("/api/ask", json={"question": "who borrowed my laptop"}, headers=owner["headers"]).json()

    # The smooth answer is gone: what the user gets is the quotation, with its marker.
    assert body["mode"] == "extractive"
    assert "John took your MacBook" not in body["answer"]
    assert "[1]" in body["answer"]
    assert body["citations"]


def test_a_citation_to_a_note_that_does_not_exist_is_discarded(make_user, create_memory, session_factory):
    owner = make_user()
    _viz(None, create_memory, owner)
    fake = FakeLLM(text="John borrowed the laptop [9]. He returns it on Friday [12].")
    app = create_app(session_factory=session_factory, llm=fake)

    body = TestClient(app).post("/api/ask", json={"question": "who borrowed my laptop"}, headers=owner["headers"]).json()

    assert body["mode"] == "extractive"
    assert "[9]" not in body["answer"] and "[12]" not in body["answer"]


def test_a_provider_failure_falls_back_to_quotations(make_user, create_memory, session_factory):
    owner = make_user()
    _viz(None, create_memory, owner)
    fake = FakeLLM(error=LLMError("model returned HTTP 503"))
    app = create_app(session_factory=session_factory, llm=fake)

    response = TestClient(app).post("/api/ask", json={"question": "who borrowed my laptop"}, headers=owner["headers"])

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "extractive"
    assert "[1]" in body["answer"]


def test_nothing_retrieved_never_calls_the_model(make_user, session_factory):
    owner = make_user()
    fake = FakeLLM(text="something invented [1]")
    app = create_app(session_factory=session_factory, llm=fake)

    body = TestClient(app).post("/api/ask", json={"question": "what did I decide about the boat"}, headers=owner["headers"]).json()

    assert body["matched"] == 0 and body["citations"] == []
    assert fake.calls == [], "a model with no notes to read could only invent something"


# --------------------------------------------------- markers point where they say
@pytest.mark.parametrize(
    ("answer", "cited", "count", "expected_text", "expected_indices"),
    [
        # A subset keeps its order and is renumbered from 1.
        ("Returns tomorrow [3]. Shed key [1].", (), 3, "Returns tomorrow [1]. Shed key [2].", [3, 1]),
        ("Only [2].", (), 3, "Only [1].", [2]),
        # Out-of-range markers disappear instead of dangling.
        ("Real [1], invented [7].", (), 2, "Real [1], invented.", [1]),
        # The composer can narrow what it used.
        ("A [1] B [2] C [3]", (2, 3), 3, "A  B [1] C [2]", [2, 3]),
        # Nothing usable at all.
        ("No markers here.", (), 3, "No markers here.", []),
    ],
)
def test_prune_citations(answer, cited, count, expected_text, expected_indices):
    from app.services.ask import _prune_citations

    text, indices = _prune_citations(answer, cited, count)
    assert indices == expected_indices
    assert " ".join(text.split()) == " ".join(expected_text.split())


# ------------------------------------------------- extract, but never invent a source
def test_model_extraction_keeps_grounded_proposals_and_drops_the_rest():
    fake = FakeLLM(
        payload={
            "proposals": [
                {
                    "title": "Chidi will fix the generator on Friday",
                    "content": "Chidi promised to fix the generator on Friday.",
                    "source_text": "Chidi promised to fix the generator on Friday.",
                    "category": "promises",
                    "confidence": 0.9,
                },
                {
                    "title": "Chidi owes you 50000 naira",
                    "content": "Chidi owes you money for the repairs.",
                    "source_text": "Chidi owes you 50000 naira for the repairs.",
                    "category": "clients",
                    "confidence": 0.8,
                },
                {
                    "title": "Generator is in the backyard shed",
                    "content": "The generator is in the backyard shed.",
                    "source_text": "the generator is in the BACKYARD   shed.",
                    "category": "maintenance",
                    "confidence": 0.7,
                },
            ]
        }
    )

    proposals = extract_proposals_with_model(NOTE, llm=fake)

    assert proposals is not None
    titles = [proposal.title for proposal in proposals]
    # The invented debt is gone; the others survive, including one that only differs by
    # case and spacing from the note.
    assert len(proposals) == 2
    assert not any("naira" in title for title in titles)
    assert proposals[0].source_text in NOTE
    assert proposals[0].category == "promises"
    assert 0.0 <= proposals[0].confidence <= 1.0


def test_model_extraction_returns_none_when_nothing_is_grounded():
    fake = FakeLLM(payload={"proposals": [{"title": "x", "content": "y", "source_text": "a fact nobody wrote", "category": "work"}]})
    assert extract_proposals_with_model(NOTE, llm=fake) is None


def test_extraction_falls_back_to_rules_on_bad_json_and_errors():
    note = NOTE
    assert extract_proposals_with_model(note, llm=FakeLLM(text="not json at all")) is None
    assert extract_proposals_with_model(note, llm=FakeLLM(error=LLMError("boom"))) is None
    # A well-formed but empty answer also defers to the rules: a note is never swallowed.
    assert extract_proposals_with_model(note, llm=FakeLLM(payload={"proposals": []})) is None


def test_extraction_coerces_categories_and_clamps_confidence():
    fake = FakeLLM(
        payload={
            "proposals": [
                {
                    "title": "Backyard shed",
                    "content": "The generator is in the backyard shed.",
                    "source_text": "The generator is in the backyard shed.",
                    "category": "garden-implements",
                    "confidence": 4.2,
                },
                {
                    "title": "Duplicate",
                    "content": "dup",
                    "source_text": "The generator is in the backyard shed.",
                    "category": "maintenance",
                    "confidence": 0.5,
                },
            ]
        }
    )

    proposals = extract_proposals_with_model(NOTE, llm=fake)

    assert proposals is not None and len(proposals) == 1, "the duplicate is dropped"
    assert proposals[0].category == "general"
    assert proposals[0].confidence == 1.0


# ------------------------------------------------------------------ the worker path
CONTRACT_NOTE = "Ade promised to send the contract on Monday. The spare key is under the blue pot."


def _capture(client, owner, text=CONTRACT_NOTE):
    response = client.post("/api/captures", json={"text": text}, headers=owner["headers"])
    assert response.status_code == 202, response.text


def test_the_worker_uses_the_model_and_records_which_extractor_ran(monkeypatch, client, make_user, session_factory):
    from app.db.models import AuditLog
    from app.worker import run_once

    owner = make_user()
    _capture(client, owner)
    fake = FakeLLM(
        payload={
            "proposals": [
                {
                    "title": "Ade will send the contract on Monday",
                    "content": "Ade promised to send the contract on Monday.",
                    "source_text": "Ade promised to send the contract on Monday.",
                    "category": "promises",
                    "confidence": 0.9,
                }
            ]
        }
    )
    monkeypatch.setattr("app.worker.build_llm", lambda: fake)

    stats = run_once(session_factory, worker_id="model-worker")
    assert stats.done == 1 and stats.failed == 0

    pending = client.get("/api/proposals", params={"status": "pending"}, headers=owner["headers"]).json()
    assert pending["total"] == 1
    assert pending["items"][0]["source_text"] == "Ade promised to send the contract on Monday."
    assert fake.calls and fake.calls[0]["json_mode"] is True

    with session_factory() as session:
        audit = session.query(AuditLog).filter(AuditLog.action == "capture.extracted").one()
        assert audit.detail["extractor"] == "model"


def test_an_invented_model_proposal_never_reaches_the_queue(monkeypatch, client, make_user, session_factory):
    from app.worker import run_once

    owner = make_user()
    _capture(client, owner)
    fake = FakeLLM(
        payload={
            "proposals": [
                {
                    "title": "Ade owes you 400000 naira",
                    "content": "Ade owes you 400000 naira for the contract.",
                    "source_text": "Ade owes you 400000 naira for the contract.",
                    "category": "clients",
                    "confidence": 0.95,
                }
            ]
        }
    )
    monkeypatch.setattr("app.worker.build_llm", lambda: fake)

    run_once(session_factory, worker_id="model-worker")

    pending = client.get("/api/proposals", params={"status": "pending"}, headers=owner["headers"]).json()
    assert pending["total"] >= 1, "the rule-based pass still produced proposals"
    assert not any("naira" in item["title"] for item in pending["items"])
    assert all(item["source_text"] in CONTRACT_NOTE for item in pending["items"])
