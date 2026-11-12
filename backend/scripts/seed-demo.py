#!/usr/bin/env python3
"""Seed ECHO with a demo account so the live app has something in it.

Creates demo@echo.local / echo-demo-2026 with a handful of memories, people,
one pending capture and two reminders. Idempotent enough for demo use: running it
twice against the same database just adds the rows again, so drop echo.db first
if you want a clean slate.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone

import httpx

BASE = "http://127.0.0.1:8000/api"
EMAIL = "demo@echo.local"
PASSWORD = "echo-demo-2026"

PEOPLE = [
    ("John", "Neighbour on the third floor. Borrowed the MacBook."),
    ("Ngozi", "Landlord. Handles the boiler and building repairs."),
]

MEMORIES = [
    (
        "John borrowed my laptop",
        "He took the MacBook yesterday evening and promised to bring it back "
        "tomorrow morning before 9. Charger went with it.",
        "belongings",
    ),
    (
        "Boiler repair promised for Friday",
        "Ngozi said a plumber would come Friday between 9 and 11 to look at the "
        "pressure valve. Nobody has confirmed since Tuesday.",
        "maintenance",
    ),
    (
        "Ada's birthday is 3 March",
        "She mentioned it at dinner and said she is not doing anything big this year. "
        "She likes ceramics, not gift cards.",
        "people",
    ),
    (
        "Invoice 118 sent to Bright Foods",
        "Sent on 4 November for 40,000 naira, payment terms 14 days. Ask for the "
        "accounts contact next time, the generic inbox never answers.",
        "clients",
    ),
    (
        "Car service due at 60,000 km",
        "Currently at 58,400 km, so roughly another month of driving. The last "
        "service was done at the workshop on Adeola street.",
        "maintenance",
    ),
]

REMINDERS = [
    ("Get the laptop back from John", 1, 9),
    ("Chase Bright Foods about invoice 118", 6, 10),
]

PROPOSAL = (
    "Chidi needs the pricing deck by Friday",
    "He asked for the updated pricing deck before the meeting on Friday and "
    "wants the enterprise tier options included.",
    "work",
    "Chidi: can you send me the pricing deck before Friday? Include the enterprise tiers please.",
)


def main() -> int:
    with httpx.Client(timeout=15) as client:
        registered = client.post(f"{BASE}/auth/register", json={"email": EMAIL, "password": PASSWORD})
        if registered.status_code not in (201, 409):
            print("could not register demo user:", registered.status_code, registered.text[:200])
            return 1
        token = client.post(f"{BASE}/auth/token", json={"email": EMAIL, "password": PASSWORD}).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        existing = client.get(f"{BASE}/memories", headers=headers, params={"limit": 1}).json()
        if existing["total"] > 0:
            print(f"already seeded ({existing['total']} memories) — nothing to do")
            return 0

        for name, notes in PEOPLE:
            client.post(f"{BASE}/people", headers=headers, json={"name": name, "notes": notes})

        for title, content, category in MEMORIES:
            created = client.post(
                f"{BASE}/memories",
                headers=headers,
                json={"title": title, "content": content, "category": category},
            )
            created.raise_for_status()

        now = datetime.now(timezone.utc)
        for title, days, hour in REMINDERS:
            due = (now + timedelta(days=days)).replace(hour=hour, minute=0, second=0, microsecond=0)
            client.post(
                f"{BASE}/reminders",
                headers=headers,
                json={"title": title, "due_at": due.isoformat()},
            ).raise_for_status()

        title, memory, category, source = PROPOSAL
        client.post(
            f"{BASE}/proposals",
            headers=headers,
            json={
                "title": title,
                "content": memory,
                "category": category,
                "source_text": source,
                "confidence": 0.82,
            },
        ).raise_for_status()

        summary = {
            "memories": client.get(f"{BASE}/memories", headers=headers).json()["total"],
            "people": client.get(f"{BASE}/people", headers=headers).json()["total"],
            "pending_proposals": client.get(f"{BASE}/proposals", headers=headers, params={"status": "pending"}).json()["total"],
            "reminders": client.get(f"{BASE}/reminders", headers=headers).json()["total"],
        }
        print("seeded:", summary)
    print(f"sign in with {EMAIL} / {PASSWORD}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
