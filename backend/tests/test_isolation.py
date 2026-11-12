"""The test that matters more than the other eight combined (fix #6).

Proves user B cannot read, list, search, update, archive or delete user A's rows,
and cannot attach A's person to B's memory. Every miss must be a 404, never a 403:
the existence of another tenant's row is itself private.
"""
from __future__ import annotations


def test_user_b_cannot_read_user_a_memory(client, make_user, create_memory):
    alice, bob = make_user(), make_user()
    memory = create_memory(alice["headers"])

    response = client.get(f"/api/memories/{memory['id']}", headers=bob["headers"])
    assert response.status_code == 404
    assert "content" not in response.text


def test_user_b_cannot_update_user_a_memory(client, make_user, create_memory):
    alice, bob = make_user(), make_user()
    memory = create_memory(alice["headers"])

    response = client.patch(
        f"/api/memories/{memory['id']}", json={"title": "hijacked"}, headers=bob["headers"]
    )
    assert response.status_code == 404

    # And A's row is untouched.
    still_there = client.get(f"/api/memories/{memory['id']}", headers=alice["headers"])
    assert still_there.status_code == 200
    assert still_there.json()["title"] == memory["title"]


def test_user_b_cannot_delete_or_archive_user_a_memory(client, make_user, create_memory):
    alice, bob = make_user(), make_user()
    memory = create_memory(alice["headers"])

    assert client.delete(f"/api/memories/{memory['id']}", headers=bob["headers"]).status_code == 404
    assert client.post(f"/api/memories/{memory['id']}/archive", headers=bob["headers"]).status_code == 404
    assert client.get(f"/api/memories/{memory['id']}", headers=alice["headers"]).status_code == 200


def test_list_and_search_are_scoped(client, make_user, create_memory):
    alice, bob = make_user(), make_user()
    create_memory(alice["headers"], title="Alice private note", content="laptop serial 9981")
    create_memory(bob["headers"], title="Bob private note", content="borrowed a ladder")

    alice_items = client.get("/api/memories", headers=alice["headers"]).json()["items"]
    assert [item["title"] for item in alice_items] == ["Alice private note"]

    # Full-text search over another tenant's words returns nothing.
    hits = client.get("/api/memories", params={"q": "laptop serial"}, headers=bob["headers"]).json()
    assert hits["total"] == 0 and hits["items"] == []


def test_archived_rows_stay_private(client, make_user, create_memory):
    alice, bob = make_user(), make_user()
    memory = create_memory(alice["headers"])
    assert client.post(f"/api/memories/{memory['id']}/archive", headers=alice["headers"]).status_code == 200

    assert client.get(f"/api/memories/{memory['id']}", headers=bob["headers"]).status_code == 404
    assert client.get(
        "/api/memories", params={"include_archived": True}, headers=bob["headers"]
    ).json()["total"] == 0


def test_cannot_smuggle_user_id_into_create(client, make_user):
    alice, bob = make_user(), make_user()
    response = client.post(
        "/api/memories",
        json={"title": "spoof", "content": "spoof", "user_id": alice["id"]},
        headers=bob["headers"],
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_cannot_attach_another_tenants_person(client, make_user, create_person):
    alice, bob = make_user(), make_user()
    alice_person = create_person(alice["headers"], name="Alice's brother")

    response = client.post(
        "/api/memories",
        json={"title": "linked", "content": "linked", "person_id": alice_person["id"]},
        headers=bob["headers"],
    )
    assert response.status_code == 404


def test_proposals_are_scoped(client, make_user):
    alice, bob = make_user(), make_user()
    payload = {
        "title": "Borrowed ladder",
        "content": "Neighbour took the ladder",
        "source_text": "my neighbour took the ladder last week",
        "category": "belongings",
        "confidence": 0.8,
    }
    proposal = client.post("/api/proposals", json=payload, headers=alice["headers"]).json()

    assert client.get(f"/api/proposals/{proposal['id']}", headers=bob["headers"]).status_code == 404
    assert client.post(f"/api/proposals/{proposal['id']}/approve", headers=bob["headers"]).status_code == 404
    assert client.post(f"/api/proposals/{proposal['id']}/reject", headers=bob["headers"]).status_code == 404
    assert client.get("/api/proposals", headers=bob["headers"]).json()["total"] == 0

    # Approval by the owner still works after all that.
    approved = client.post(f"/api/proposals/{proposal['id']}/approve", headers=alice["headers"])
    assert approved.status_code == 200
    assert approved.json()["memory"]["title"] == "Borrowed ladder"


def test_reminders_are_scoped(client, make_user):
    from datetime import datetime, timedelta, timezone

    alice, bob = make_user(), make_user()
    due = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    reminder = client.post(
        "/api/reminders", json={"title": "return ladder", "due_at": due}, headers=alice["headers"]
    ).json()

    assert client.post(f"/api/reminders/{reminder['id']}/cancel", headers=bob["headers"]).status_code == 404
    assert client.get("/api/reminders", headers=bob["headers"]).json()["total"] == 0
