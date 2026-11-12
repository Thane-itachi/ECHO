"""Ask ECHO: grounded answers, citations, and no cross-tenant leakage."""
from __future__ import annotations


def test_ask_answers_from_the_vault_with_citations(client, make_user, create_memory):
    owner = make_user()
    memory = create_memory(
        owner["headers"],
        title="John borrowed my laptop",
        content="He took the MacBook yesterday evening and promised to bring it back tomorrow before 9.",
    )
    create_memory(
        owner["headers"],
        title="Ada's birthday is 3 March",
        content="She mentioned it at dinner and said she is not doing anything big this year.",
    )

    response = client.post("/api/ask", json={"question": "who borrowed my laptop"}, headers=owner["headers"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["mode"] == "extractive"
    assert body["matched"] >= 1
    assert body["citations"][0]["memory_id"] == memory["id"]
    assert "John" in body["answer"]
    assert "laptop" in body["answer"].lower()
    # The citation marker is in the text, so an answer is never unciteable prose.
    assert "[1]" in body["answer"]


def test_ask_says_so_when_nothing_matches(client, make_user):
    owner = make_user()
    response = client.post("/api/ask", json={"question": "what did I decide about the boat"}, headers=owner["headers"])
    body = response.json()
    assert body["matched"] == 0
    assert body["citations"] == []
    assert "Nothing in your vault" in body["answer"]


def test_ask_never_crosses_tenants(client, make_user, create_memory):
    alice = make_user()
    bob = make_user()
    create_memory(alice["headers"], title="John borrowed my laptop", content="He returns it tomorrow.")

    response = client.post("/api/ask", json={"question": "who borrowed the laptop"}, headers=bob["headers"])
    body = response.json()
    assert body["matched"] == 0
    assert body["citations"] == []
    assert "John" not in body["answer"]
