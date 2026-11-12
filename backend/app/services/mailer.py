"""Outbound email.

One narrow surface: hand a message over, and either it was accepted or it raised.
Resend is the wired provider; the log mailer keeps local development honest (you can
read the code out of the API log) and refuses to be the production path.

Codes are the only thing this sends today. Reminder delivery can use the same seam
without new plumbing.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Protocol

import httpx

from app.core.config import settings

logger = logging.getLogger("echo.mail")


class MailError(Exception):
    """The provider refused the message, or could not be reached."""


@dataclass(frozen=True)
class EmailMessage:
    to: str
    subject: str
    text: str
    html: str | None = None
    headers: dict[str, str] = field(default_factory=dict)


class Mailer(Protocol):
    name: str

    def send(self, message: EmailMessage) -> None: ...


class LogMailer:
    """No provider: write the message to the log.

    Deliberately loud at WARNING so a code is never silently swallowed. In production it
    only exists when someone set `ECHO_MAILER=log` on purpose (see `build_mailer`), and
    then the line says so.
    """

    name = "log"

    def __init__(self, *, explicit: bool = False) -> None:
        self.explicit = explicit

    def send(self, message: EmailMessage) -> None:
        reason = "ECHO_MAILER=log" if self.explicit else "no provider"
        logger.warning(
            "email (not sent, %s) to=%s subject=%s\n%s", reason, message.to, message.subject, message.text
        )


class ResendMailer:
    """https://resend.com — POST /emails with a bearer key."""

    name = "resend"

    def __init__(self, api_key: str, *, sender: str, base_url: str, timeout: float) -> None:
        self.api_key = api_key
        self.sender = sender
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def send(self, message: EmailMessage) -> None:
        body: dict = {
            "from": self.sender,
            "to": [message.to],
            "subject": message.subject,
            "text": message.text,
        }
        if message.html:
            body["html"] = message.html
        if message.headers:
            body["headers"] = message.headers
        try:
            response = httpx.post(
                f"{self.base_url}/emails",
                json=body,
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                timeout=self.timeout,
            )
        except httpx.HTTPError as exc:  # network, DNS, timeout
            raise MailError(f"could not reach the mail provider: {exc}") from exc
        if response.status_code >= 400:
            raise MailError(f"mail provider refused the message ({response.status_code}): {response.text[:200]}")


class CapturingMailer:
    """Test double: keeps every message in memory so tests can read the code."""

    name = "capture"

    def __init__(self) -> None:
        self.sent: list[EmailMessage] = []

    def send(self, message: EmailMessage) -> None:
        self.sent.append(message)

    def last(self, to: str | None = None) -> EmailMessage | None:
        for message in reversed(self.sent):
            if to is None or message.to == to.strip().lower():
                return message
        return None

    def code_for(self, email: str) -> str:
        """Pull the six digits out of the most recent message to that address."""
        import re

        message = self.last(email)
        if message is None:
            raise AssertionError(f"no email was sent to {email}")
        match = re.search(r"\b(\d{6})\b", message.text)
        if match is None:
            raise AssertionError(f"no code in {message.text!r}")
        return match.group(1)


def build_mailer() -> Mailer:
    if settings.email_enabled:
        return ResendMailer(
            settings.resend_api_key or "",
            sender=settings.email_from,
            base_url=settings.resend_base_url,
            timeout=settings.email_timeout_seconds,
        )
    if settings.mailer == "log":
        # An explicit choice, not a fallback: a deploy with no provider runs, and every
        # message it would have sent is in the log. load_settings() refuses this in
        # production while address verification is on, because a code nobody receives is
        # a sign-up that cannot finish.
        return LogMailer(explicit=True)
    if settings.is_production:
        # load_settings() already refuses this combination; belt and braces.
        raise RuntimeError("no mail provider configured in production")
    return LogMailer()


def describe(mailer: Mailer) -> str:
    if isinstance(mailer, ResendMailer):
        return f"resend (from {mailer.sender})"
    if settings.is_production:
        return "none — ECHO_MAILER=log, so messages are written to the log and never sent"
    return "none — codes are logged, not delivered"
