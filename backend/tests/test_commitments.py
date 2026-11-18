"""People hold more than notes: what they are to you, the dates you keep, and
what is still owed between you.

The rules under test are the ones the rest of ECHO is judged by: ownership never
leaks, nothing is stored in the clear, and a commitment becomes a reminder only
when someone presses the button.
"""
from __future__ import annotations

import base64
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.core.crypto import ContentCipher, new_data_key
from app.main import create_app
from app.services.mailer import CapturingMailer
from tests.support import sign_in


@pytest.fixture()
def sealed(session_factory):
    """A client whose vault is really encrypted, so "at rest" claims can be checked."""
    cipher = ContentCipher(base64.urlsafe_b64decode(new_data_key()))
    app = create_app(session_factory=session_factory, cipher=cipher)
    app.state.mailer = CapturingMailer()
    with TestClient(app) as client:
        yield client


def _person(client, headers, **payload):
    body = {"name": "Daniel", **payload}
    response = client.post("/api/people", json=body, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def test_a_person_carries_a_relationship_and_key_dates(client, make_user):
    owner = make_user()
    person = _person(
        client,
        owner["headers"],
        relationship="my landlord",
        key_dates=[{"label": "birthday", "date": "1979-04-12"}],
    )

    assert person["relationship"] == "my landlord"
    assert person["key_dates"][0]["label"] == "birthday"
    assert person["key_dates"][0]["date"] == "1979-04-12"
    assert person["open_commitments"] == 0

    read = client.get(f"/api/people/{person['id']}", headers=owner["headers"])
    assert read.status_code == 200
    assert read.json()["relationship"] == "my landlord"


def test_the_relationship_is_encrypted_at_rest(sealed, session_factory):
    headers = sign_in(sealed, email="sealed-rel@example.com")
    owner = {"headers": headers}
    person = _person(sealed, owner["headers"], relationship="my sister", notes="owes me nothing")

    from sqlalchemy import text

    with session_factory() as session:
        row = session.execute(
            text("SELECT relationship_enc, notes_enc, dates_enc FROM people WHERE id = :id"), {"id": person["id"]}
        ).one()
    assert row[0] and "sister" not in row[0]
    assert row[1] and "nothing" not in row[1]


def test_promises_and_things_lent_are_counted_on_the_person(client, make_user):
    owner = make_user()
    person = _person(client, owner["headers"])

    first = client.post(
        "/api/commitments",
        json={"kind": "promise", "text": "send him the project document on Friday", "person_id": person["id"]},
        headers=owner["headers"],
    )
    assert first.status_code == 201, first.text
    assert first.json()["person_name"] == "Daniel"

    client.post(
        "/api/commitments",
        json={"kind": "lent", "text": "my drill", "person_id": person["id"]},
        headers=owner["headers"],
    )

    listed = client.get(f"/api/people?limit=50", headers=owner["headers"]).json()
    assert listed["items"][0]["open_commitments"] == 2

    # and closing one takes the count back down
    done = client.patch(
        f"/api/commitments/{first.json()['id']}", json={"status": "done"}, headers=owner["headers"]
    )
    assert done.status_code == 200
    assert done.json()["status"] == "done"
    assert client.get(f"/api/people/{person['id']}", headers=owner["headers"]).json()["open_commitments"] == 1


def test_commitments_are_encrypted_and_owner_scoped(sealed, session_factory):
    alice = {"headers": sign_in(sealed, email="sealed-alice@example.com")}
    bob = {"headers": sign_in(sealed, email="sealed-bob@example.com")}
    person = _person(sealed, alice["headers"], name="Ada")
    client = sealed
    created = client.post(
        "/api/commitments",
        json={"kind": "borrowed", "text": "her ladder", "person_id": person["id"]},
        headers=alice["headers"],
    )
    assert created.status_code == 201, created.text

    from sqlalchemy import text

    with session_factory() as session:
        stored = session.execute(
            text("SELECT text_enc FROM commitments WHERE id = :id"), {"id": created.json()["id"]}
        ).scalar_one()
    assert "ladder" not in stored

    # Bob sees nothing, and cannot touch it by id.
    assert client.get("/api/commitments", headers=bob["headers"]).json()["total"] == 0
    assert client.get(f"/api/people/{person['id']}", headers=bob["headers"]).status_code == 404
    assert (
        client.patch(
            f"/api/commitments/{created.json()['id']}", json={"status": "done"}, headers=bob["headers"]
        ).status_code
        == 404
    )


def test_a_commitment_can_come_from_a_note(client, make_user, create_memory):
    owner = make_user()
    memory = create_memory(owner["headers"], title="James and the document", content="I promised it on Friday.")

    created = client.post(
        "/api/commitments",
        json={"kind": "promise", "text": "send James the document", "memory_id": memory["id"]},
        headers=owner["headers"],
    )
    assert created.status_code == 201, created.text
    assert created.json()["memory_id"] == memory["id"]


def test_one_tap_turns_a_commitment_into_a_reminder(client, make_user):
    owner = make_user()
    person = _person(client, owner["headers"])
    soon = (date.today() + timedelta(days=3)).isoformat()
    created = client.post(
        "/api/commitments",
        json={"kind": "promise", "text": "return the drill", "person_id": person["id"], "due_on": soon},
        headers=owner["headers"],
    ).json()

    reminded = client.post(f"/api/commitments/{created['id']}/remind", json={}, headers=owner["headers"])
    assert reminded.status_code == 201, reminded.text
    reminder = reminded.json()
    assert "Daniel" in reminder["title"] and "drill" in reminder["title"]
    assert reminder["due_at"].startswith(soon)

    # pressing twice must not schedule a second notification
    again = client.post(f"/api/commitments/{created['id']}/remind", json={}, headers=owner["headers"])
    assert again.status_code == 201
    assert again.json()["id"] == reminder["id"]

    listed = client.get("/api/reminders", headers=owner["headers"]).json()
    assert len([item for item in listed["items"] if item["status"] == "scheduled"]) == 1


def test_reminding_a_past_commitment_is_refused(client, make_user):
    owner = make_user()
    created = client.post(
        "/api/commitments",
        json={"kind": "promise", "text": "something overdue"},
        headers=owner["headers"],
    ).json()
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    response = client.post(
        f"/api/commitments/{created['id']}/remind", json={"due_at": past}, headers=owner["headers"]
    )
    assert response.status_code == 422
    assert "already due" in response.json()["error"]["message"]


def test_due_soon_lists_only_dated_open_work(client, make_user):
    owner = make_user()
    today = date.today()
    client.post(
        "/api/commitments",
        json={"kind": "promise", "text": "this week", "due_on": (today + timedelta(days=2)).isoformat()},
        headers=owner["headers"],
    )
    client.post(
        "/api/commitments",
        json={"kind": "promise", "text": "next year", "due_on": (today + timedelta(days=300)).isoformat()},
        headers=owner["headers"],
    )
    client.post(
        "/api/commitments", json={"kind": "lent", "text": "no date at all"}, headers=owner["headers"]
    )

    due = client.get("/api/commitments/due?days=14", headers=owner["headers"]).json()
    assert [item["text"] for item in due["items"]] == ["this week"]


def test_deleting_a_person_keeps_the_commitment_but_loses_the_name(client, make_user):
    owner = make_user()
    person = _person(client, owner["headers"])
    client.post(
        "/api/commitments",
        json={"kind": "lent", "text": "his ladder", "person_id": person["id"]},
        headers=owner["headers"],
    )
    assert client.delete(f"/api/people/{person['id']}", headers=owner["headers"]).status_code == 204

    remaining = client.get("/api/commitments", headers=owner["headers"]).json()
    assert remaining["total"] == 1
    assert remaining["items"][0]["person_id"] is None
    assert remaining["items"][0]["text"] == "his ladder"


def test_the_person_list_can_be_edited(client, make_user):
    owner = make_user()
    person = _person(client, owner["headers"])
    patched = client.patch(
        f"/api/people/{person['id']}",
        json={"relationship": "my accountant", "key_dates": [{"label": "tax year end", "date": "2027-04-05", "repeats_yearly": False}]},
        headers=owner["headers"],
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["relationship"] == "my accountant"
    assert patched.json()["key_dates"][0]["repeats_yearly"] is False
