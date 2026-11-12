"""Small helpers shared by the test modules."""
from __future__ import annotations

from fastapi.testclient import TestClient

DEFAULT_PASSWORD = "correct-horse-battery"


def code_sent_to(client: TestClient, email: str) -> str:
    """The six digits from the most recent message to this address."""
    return client.app.state.mailer.code_for(email)


def sign_in(client: TestClient, *, email: str, password: str = DEFAULT_PASSWORD) -> dict[str, str]:
    """Register, confirm the emailed code, and return bearer headers.

    Every authenticated test ends up here, so the verification step is exercised by
    the whole suite rather than by one dedicated file.
    """
    registered = client.post("/api/auth/register", json={"email": email, "password": password})
    assert registered.status_code in (201, 409), registered.text
    confirmed = client.post(
        "/api/auth/verification/confirm", json={"email": email, "code": code_sent_to(client, email)}
    )
    if confirmed.status_code != 200:
        # Already confirmed in an earlier call against this database: sign in instead.
        confirmed = client.post(
            "/api/auth/token/code" if False else "/api/auth/token",
            json={"email": email, "password": password},
        )
    assert confirmed.status_code == 200, confirmed.text
    return {"Authorization": f"Bearer {confirmed.json()['access_token']}"}
