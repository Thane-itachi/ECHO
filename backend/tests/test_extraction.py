"""Extraction: pure rules, durable queue, proposals instead of memories."""
from __future__ import annotations

from app.services.extraction import extract_proposals, extract_reminder_hint
from app.worker import run_once

NOTE = (
    "John borrowed my laptop yesterday evening. "
    "He promised to return it tomorrow before 9. "
    "Also the boiler needs a service, Ngozi said the plumber comes Friday between 9 and 11."
)


# ------------------------------------------------------------------ pure rules
def test_extraction_produces_one_proposal_per_informative_sentence():
    proposals = extract_proposals(NOTE, known_people=("John", "Ngozi"))
    assert len(proposals) == 3
    assert all(0.0 <= proposal.confidence <= 1.0 for proposal in proposals)
    assert all(proposal.source_text for proposal in proposals)


def test_extraction_guesses_category_and_person():
    proposals = extract_proposals(NOTE, known_people=("John", "Ngozi"))
    by_source = {proposal.source_text: proposal for proposal in proposals}

    laptop = next(p for p in proposals if "laptop" in p.source_text)
    assert laptop.category in {"belongings", "promises"}
    assert "John" in laptop.title

    boiler = next(p for p in proposals if "boiler" in p.source_text)
    assert boiler.category == "maintenance"
    assert boiler.cues


def test_extraction_skips_fragments_and_duplicates():
    proposals = extract_proposals("yes. ok.\nBuy milk today. Buy milk today.")
    assert [proposal.source_text for proposal in proposals] == ["Buy milk today."]


def test_reminder_hint_finds_a_date_phrase():
    assert extract_reminder_hint("He promised to return it tomorrow before 9.") == "tomorrow"
    assert extract_reminder_hint("Nothing time-bound here at all.") is None


# --------------------------------------------------------------- through the API
def test_capture_is_queued_not_applied(client, make_user):
    owner = make_user()
    response = client.post("/api/captures", json={"text": NOTE}, headers=owner["headers"])
    assert response.status_code == 202, response.text
    assert response.json()["queued"] is True

    # Nothing entered the vault, and no proposal exists until the worker runs.
    assert client.get("/api/memories", headers=owner["headers"]).json()["total"] == 0
    assert client.get("/api/proposals", headers=owner["headers"]).json()["total"] == 0

    first_job = response.json()["job_id"]
    repeat = client.post("/api/captures", json={"text": NOTE}, headers=owner["headers"])
    assert repeat.json()["job_id"] == first_job, "identical captures must not queue twice"


def test_worker_turns_captures_into_pending_proposals(client, make_user, create_person, session_factory):
    owner = make_user()
    create_person(owner["headers"], "John")
    client.post("/api/captures", json={"text": NOTE}, headers=owner["headers"])

    stats = run_once(session_factory, worker_id="test-worker")
    assert stats.done == 1, stats
    assert stats.failed == 0

    pending = client.get("/api/proposals", params={"status": "pending"}, headers=owner["headers"]).json()
    assert pending["total"] == 3
    titles = {item["title"] for item in pending["items"]}
    assert any("John" in title for title in titles)
    # Proposals still are not memories: approval is the only door.
    assert client.get("/api/memories", headers=owner["headers"]).json()["total"] == 0

    approved = client.post(
        f"/api/proposals/{pending['items'][0]['id']}/approve", headers=owner["headers"]
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["memory"]["source"] == "ai_extraction"
    assert client.get("/api/memories", headers=owner["headers"]).json()["total"] == 1


def test_worker_does_not_duplicate_proposals_on_rerun(client, make_user, session_factory):
    owner = make_user()
    response = client.post("/api/captures", json={"text": NOTE}, headers=owner["headers"])
    assert response.status_code == 202
    run_once(session_factory, worker_id="worker-a")

    # Re-running the same job (a retry or a re-queue) must not double the proposals.
    from app.db.models import Job

    with session_factory() as session:
        job = session.get(Job, response.json()["job_id"])
        job.status = "queued"
        job.attempts = 0
        session.commit()
    run_once(session_factory, worker_id="worker-b")

    assert client.get("/api/proposals", headers=owner["headers"]).json()["total"] == 3


def test_captures_are_owner_scoped(client, make_user, session_factory):
    alice = make_user()
    bob = make_user()
    client.post("/api/captures", json={"text": NOTE}, headers=alice["headers"])
    run_once(session_factory, worker_id="worker")

    assert client.get("/api/proposals", headers=bob["headers"]).json()["total"] == 0


def test_promise_titles_are_not_reworded():
    """Regression: a promise sentence used to gain a second, broken subject."""
    proposals = extract_proposals("Chidi from the workshop promised to fix the generator next Tuesday.")
    assert proposals[0].title == "Chidi from the workshop promised to fix the generator next Tuesday"
    assert "will" not in proposals[0].title.lower()


def test_titles_truncate_on_a_word_boundary():
    long_sentence = (
        "The landlord confirmed that the plumber will arrive between nine and eleven on Friday morning "
        "with the replacement valve and every tool he needs to finish the job properly"
    )
    title = extract_proposals(long_sentence)[0].title
    assert title.endswith("…")
    assert len(title) <= 90
    assert title[:-1].strip().split()[-1] in long_sentence.split()
