"""Search works, and it does not need the words.

The old design stored a lowercased plaintext copy of every memory so `LIKE` could
scan it. These tests pin the replacement: a keyed blind index that supports word and
prefix matching while the database holds no readable text at all.
"""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.crypto import ContentCipher
from app.db.models import Memory, Person
from app.main import create_app
from app.services.mailer import CapturingMailer
from tests.support import sign_in

TITLE = "Boiler repair promised for Friday"
CONTENT = "Ngozi said a plumber would come Friday between 9 and 11 to look at the pressure valve."


@pytest.fixture()
def enc_app(session_factory):
    app = create_app(session_factory=session_factory, cipher=ContentCipher(os.urandom(32)))
    app.state.mailer = CapturingMailer()
    return app


@pytest.fixture()
def enc_client(enc_app):
    with TestClient(enc_app) as client:
        yield client


def _user(client, email="enc@example.com", password="correct-horse-battery"):
    return sign_in(client, email=email, password=password)


def test_search_matches_words_and_prefixes(enc_client):
    headers = _user(enc_client)
    created = enc_client.post("/api/memories", json={"title": TITLE, "content": CONTENT}, headers=headers)
    assert created.status_code == 201, created.text

    for query in ("plumber", "boiler", "valve", "plumb", "press"):
        hits = enc_client.get("/api/memories", params={"q": query}, headers=headers).json()
        assert hits["total"] == 1, f"{query!r} should find the memory, got {hits}"
        assert hits["items"][0]["title"] == TITLE


def test_search_does_not_match_unrelated_words(enc_client):
    headers = _user(enc_client)
    enc_client.post("/api/memories", json={"title": TITLE, "content": CONTENT}, headers=headers)
    hits = enc_client.get("/api/memories", params={"q": "invoice"}, headers=headers).json()
    assert hits["total"] == 0


def test_no_plaintext_word_is_stored(enc_client, session_factory):
    headers = _user(enc_client)
    enc_client.post("/api/memories", json={"title": TITLE, "content": CONTENT}, headers=headers)
    with session_factory() as session:
        row = session.scalars(select(Memory)).one()
        surface = " ".join([row.title_enc, row.content_enc, row.search_index]).lower()
        for word in ("boiler", "plumber", "negozi", "valve", "friday", "repair"):
            assert word not in surface


def test_same_word_hashes_differently_per_user(enc_client, session_factory):
    first = _user(enc_client, email="a@example.com")
    second = _user(enc_client, email="b@example.com")
    enc_client.post("/api/memories", json={"title": "Shared word", "content": "laptop charger"}, headers=first)
    enc_client.post("/api/memories", json={"title": "Shared word", "content": "laptop charger"}, headers=second)
    with session_factory() as session:
        rows = list(session.scalars(select(Memory)))
        assert len(rows) == 2
        # Per-user keys: the same word produces different tokens, so a stolen index
        # cannot be attacked with a single wordlist across the whole platform.
        assert rows[0].search_index != rows[1].search_index


def test_people_notes_are_encrypted_and_searchable(enc_client, session_factory):
    headers = _user(enc_client)
    created = enc_client.post(
        "/api/people", json={"name": "Ngozi", "notes": "Prefers calls after 6pm, hates voicemail."}, headers=headers
    )
    assert created.status_code == 201, created.text
    assert created.json()["notes"] == "Prefers calls after 6pm, hates voicemail."
    with session_factory() as session:
        person = session.scalars(select(Person)).one()
        assert person.notes_enc is not None
        assert person.notes_enc.startswith("f1:")
        assert "voicemail" not in person.notes_enc
        assert "voicemail" not in person.search_index
