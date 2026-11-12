"""Proposals: AI output is a state machine, approval creates exactly one memory."""
from __future__ import annotations

PROPOSAL = {
    "title": "John borrowed the laptop",
    "content": "Promised to return it tomorrow.",
    "source_text": "john borrowed my laptop yesterday and said he'd bring it back tomorrow",
    "category": "belongings",
    "confidence": 0.87,
}


def test_proposal_starts_pending_and_creates_no_memory(client, make_user):
    user = make_user()
    created = client.post("/api/proposals", json=PROPOSAL, headers=user["headers"])
    assert created.status_code == 201
    body = created.json()
    assert body["status"] == "pending"
    assert body["memory_id"] is None
    assert client.get("/api/memories", headers=user["headers"]).json()["total"] == 0


def test_approve_creates_memory_once(client, make_user):
    user = make_user()
    proposal = client.post("/api/proposals", json=PROPOSAL, headers=user["headers"]).json()

    approved = client.post(f"/api/proposals/{proposal['id']}/approve", headers=user["headers"])
    assert approved.status_code == 200
    body = approved.json()
    assert body["proposal"]["status"] == "approved"
    assert body["memory"]["source"] == "ai_extraction"
    assert body["memory"]["confidence"] == 0.87
    assert body["memory"]["content"] == PROPOSAL["content"]

    second = client.post(f"/api/proposals/{proposal['id']}/approve", headers=user["headers"])
    assert second.status_code == 409
    assert client.get("/api/memories", headers=user["headers"]).json()["total"] == 1


def test_reject_creates_no_memory_and_blocks_later_approval(client, make_user):
    user = make_user()
    proposal = client.post("/api/proposals", json=PROPOSAL, headers=user["headers"]).json()

    rejected = client.post(f"/api/proposals/{proposal['id']}/reject", headers=user["headers"])
    assert rejected.status_code == 200
    assert rejected.json()["memory"] is None
    assert client.get("/api/memories", headers=user["headers"]).json()["total"] == 0

    late = client.post(f"/api/proposals/{proposal['id']}/approve", headers=user["headers"])
    assert late.status_code == 409


def test_invalid_confidence_is_rejected(client, make_user):
    user = make_user()
    bad = dict(PROPOSAL, confidence=7.5)
    assert client.post("/api/proposals", json=bad, headers=user["headers"]).status_code == 422


def test_proposal_list_filters_by_status(client, make_user):
    user = make_user()
    first = client.post("/api/proposals", json=PROPOSAL, headers=user["headers"]).json()
    client.post("/api/proposals", json=PROPOSAL, headers=user["headers"])
    client.post(f"/api/proposals/{first['id']}/approve", headers=user["headers"])

    pending = client.get("/api/proposals", params={"status": "pending"}, headers=user["headers"]).json()
    approved = client.get("/api/proposals", params={"status": "approved"}, headers=user["headers"]).json()
    assert pending["total"] == 1 and approved["total"] == 1


def test_decisions_are_audited(client, make_user, make_admin):
    user = make_user()
    proposal = client.post("/api/proposals", json=PROPOSAL, headers=user["headers"]).json()
    client.post(f"/api/proposals/{proposal['id']}/approve", headers=user["headers"])

    admin = make_admin()
    entries = client.get("/admin/audit", params={"limit": 50}, headers=admin["headers"]).json()["items"]
    actions = {entry["action"] for entry in entries}
    # The approval is a recorded state transition, not a UI step we cannot inspect.
    assert {"proposal.created", "proposal.approved", "memory.created"} <= actions
    approved = next(entry for entry in entries if entry["action"] == "proposal.approved")
    assert approved["detail"]["memory_id"]
