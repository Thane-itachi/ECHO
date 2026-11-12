"""Memory-to-memory links, owner-scoped on both ends."""
from __future__ import annotations


def test_link_list_and_unlink(client, make_user, create_memory):
    owner = make_user()
    laptop = create_memory(owner["headers"], title="John borrowed my laptop")
    promise = create_memory(owner["headers"], title="Promise to return the laptop")

    created = client.post(
        f"/api/memories/{laptop['id']}/links",
        json={"to_memory_id": promise["id"], "kind": "supports"},
        headers=owner["headers"],
    )
    assert created.status_code == 201, created.text
    items = created.json()["items"]
    assert [item["title"] for item in items] == ["Promise to return the laptop"]
    assert items[0]["kind"] == "supports"

    # Linking twice is idempotent, not a duplicate row.
    again = client.post(
        f"/api/memories/{laptop['id']}/links",
        json={"to_memory_id": promise["id"], "kind": "supports"},
        headers=owner["headers"],
    )
    assert again.status_code == 201
    assert len(again.json()["items"]) == 1

    listed = client.get(f"/api/memories/{laptop['id']}/links", headers=owner["headers"])
    assert len(listed.json()["items"]) == 1

    removed = client.delete(
        f"/api/memories/{laptop['id']}/links/{promise['id']}", headers=owner["headers"]
    )
    assert removed.status_code == 200
    assert removed.json()["items"] == []


def test_cannot_link_another_tenants_memory(client, make_user, create_memory):
    alice = make_user()
    bob = make_user()
    alice_memory = create_memory(alice["headers"], title="Alice private")
    bob_memory = create_memory(bob["headers"], title="Bob private")

    # Bob tries to reach into Alice's memory.
    attempt = client.post(
        f"/api/memories/{alice_memory['id']}/links",
        json={"to_memory_id": bob_memory["id"]},
        headers=bob["headers"],
    )
    assert attempt.status_code == 404

    # Alice tries to link her own memory to Bob's.
    attempt = client.post(
        f"/api/memories/{alice_memory['id']}/links",
        json={"to_memory_id": bob_memory["id"]},
        headers=alice["headers"],
    )
    assert attempt.status_code == 404


def test_self_link_is_rejected(client, make_user, create_memory):
    owner = make_user()
    memory = create_memory(owner["headers"])
    response = client.post(
        f"/api/memories/{memory['id']}/links",
        json={"to_memory_id": memory["id"]},
        headers=owner["headers"],
    )
    assert response.status_code == 422
