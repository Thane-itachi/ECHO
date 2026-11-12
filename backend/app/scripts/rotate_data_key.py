"""Rewrite encrypted data under the current data key (key rotation).

A master key you can never change is a master key that leaks forever. Rotation is
therefore a first-class operation, and it is deliberately three steps so that no row is
ever lost to a half-finished rewrite and no request fails mid-deploy:

1. Start the app with both keys::

       ECHO_DATA_KEY=<new>  ECHO_DATA_KEY_PREVIOUS=<old>

   Reads work immediately: the cipher tries the current key first, then the retired
   ones. New writes already use the new key. Nothing has been rewritten yet.

2. Rewrite what is left::

       python -m app.scripts.rotate_data_key --check    # what is still on the old key
       python -m app.scripts.rotate_data_key --apply    # rewrite it under the new key

3. Remove ``ECHO_DATA_KEY_PREVIOUS`` and restart. ``--check`` should now report zero.

What gets rewritten: memory titles and bodies, person notes, proposal bodies and their
source sentences, encrypted document bytes on disk, queued capture payloads, every
blind-index column (tokens are keyed, so they must be rekeyed too), and administrators'
sealed TOTP seeds.

The run is idempotent in the sense that matters: every value is decrypted to plaintext
and re-encrypted with the current key, so re-running after an interruption finishes the
job instead of encrypting ciphertext twice. Attachments are rewritten on every apply
for the same reason.
"""
from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.crypto import AnyCipher, BlindIndex, CipherError, build_cipher
from app.db.models import Attachment, Job, Memory, MemoryProposal, Person
from app.db.session import build_engine, build_session_factory

logger = logging.getLogger("echo.rotate")

BATCH_ROWS = 200


@dataclass
class Report:
    """Counts of what still needs the new key, or of what was rewritten."""

    memories: int = 0
    people: int = 0
    proposals: int = 0
    capture_jobs: int = 0
    admin_secrets: int = 0
    documents: int = 0
    document_bytes: int = 0
    unreadable: list[str] = field(default_factory=list)

    def total(self) -> int:
        return (
            self.memories
            + self.people
            + self.proposals
            + self.capture_jobs
            + self.admin_secrets
            + self.documents
        )


def _admin_secrets(session: Session) -> list[tuple[str, str]]:
    """Sealed seeds exactly as stored, bypassing the decrypting column type."""
    rows = session.execute(text("SELECT id, mfa_secret FROM admin_users")).fetchall()
    return [(row[0], row[1]) for row in rows]


def _index_terms(index: BlindIndex | None, owner_id: str, *texts: str) -> str:
    if index is not None:
        return index.index(owner_id, *texts)
    words = sorted({word for text in texts for word in BlindIndex.words(text or "")})
    return " " + " ".join(words) + " "


def _memory_needs_rewrite(cipher: AnyCipher, memory: Memory) -> bool:
    return not (
        cipher.encrypted_with_current_key(memory.title_enc, memory.user_id)
        and cipher.encrypted_with_current_key(memory.content_enc, memory.user_id)
    )


def _proposal_needs_rewrite(cipher: AnyCipher, proposal: MemoryProposal) -> bool:
    return not all(
        cipher.encrypted_with_current_key(value, proposal.user_id)
        for value in (proposal.title_enc, proposal.content_enc, proposal.source_text_enc)
    )


def _person_needs_rewrite(cipher: AnyCipher, person: Person) -> bool:
    if not person.notes_enc:
        return False
    return not cipher.encrypted_with_current_key(person.notes_enc, person.user_id)


def survey(session: Session, *, cipher: AnyCipher, storage_dir: Path) -> Report:
    """What would change. Reads only; nothing is written."""
    report = Report()

    for memory in session.scalars(select(Memory)):
        if _memory_needs_rewrite(cipher, memory):
            report.memories += 1

    for person in session.scalars(select(Person)):
        if _person_needs_rewrite(cipher, person):
            report.people += 1

    for proposal in session.scalars(select(MemoryProposal)):
        if _proposal_needs_rewrite(cipher, proposal):
            report.proposals += 1

    for job in session.scalars(select(Job).where(Job.status.in_(("queued", "running")))):
        payload = job.payload or {}
        text_enc, user_id = payload.get("text_enc"), payload.get("user_id")
        if text_enc and user_id and not cipher.encrypted_with_current_key(text_enc, user_id):
            report.capture_jobs += 1

    for _id, sealed in _admin_secrets(session):
        if not cipher.sealed_with_current_key(sealed):
            report.admin_secrets += 1

    for attachment in session.scalars(select(Attachment)):
        path = storage_dir / attachment.storage_key
        if not path.exists():
            report.unreadable.append(f"missing file: {attachment.storage_key}")
            continue
        blob = path.read_bytes()
        if not cipher.can_decrypt_bytes(blob, attachment.user_id):
            report.unreadable.append(f"document {attachment.id}: set ECHO_DATA_KEY_PREVIOUS")
        elif not cipher.bytes_with_current_key(blob, attachment.user_id):
            report.documents += 1
    return report


def rotate(
    session: Session,
    *,
    cipher: AnyCipher,
    storage_dir: Path,
    apply: bool = False,
) -> Report:
    """Rewrite everything under the current key, or (default) just report."""
    report = Report()
    index = BlindIndex.from_cipher(cipher)

    def _rewrite_memories() -> None:
        pending = 0
        for memory in session.scalars(select(Memory)):
            try:
                title = cipher.decrypt(memory.title_enc, memory.user_id)
                content = cipher.decrypt(memory.content_enc, memory.user_id)
            except CipherError:
                report.unreadable.append(f"memory {memory.id}: set ECHO_DATA_KEY_PREVIOUS")
                continue
            report.memories += 1
            if not apply:
                continue
            memory.title_enc = cipher.encrypt(title, memory.user_id)
            memory.content_enc = cipher.encrypt(content, memory.user_id)
            # Tokens are keyed, so the index is rekeyed with the content.
            memory.search_index = _index_terms(index, memory.user_id, title, content)
            pending += 1
            if pending >= BATCH_ROWS:
                session.commit()
                pending = 0
        if apply:
            session.commit()

    def _rewrite_people() -> None:
        pending = 0
        for person in session.scalars(select(Person)):
            notes = None
            if person.notes_enc:
                try:
                    notes = cipher.decrypt(person.notes_enc, person.user_id)
                except CipherError:
                    report.unreadable.append(f"person {person.id}: set ECHO_DATA_KEY_PREVIOUS")
                    continue
            report.people += 1
            if not apply:
                continue
            if notes is not None:
                person.notes_enc = cipher.encrypt(notes, person.user_id)
            person.search_index = _index_terms(index, person.user_id, person.name, notes or "")
            pending += 1
            if pending >= BATCH_ROWS:
                session.commit()
                pending = 0
        if apply:
            session.commit()

    def _rewrite_proposals() -> None:
        pending = 0
        for proposal in session.scalars(select(MemoryProposal)):
            try:
                title = cipher.decrypt(proposal.title_enc, proposal.user_id)
                content = cipher.decrypt(proposal.content_enc, proposal.user_id)
                source = cipher.decrypt(proposal.source_text_enc, proposal.user_id)
            except CipherError:
                report.unreadable.append(f"proposal {proposal.id}: set ECHO_DATA_KEY_PREVIOUS")
                continue
            report.proposals += 1
            if not apply:
                continue
            proposal.title_enc = cipher.encrypt(title, proposal.user_id)
            proposal.content_enc = cipher.encrypt(content, proposal.user_id)
            proposal.source_text_enc = cipher.encrypt(source, proposal.user_id)
            pending += 1
            if pending >= BATCH_ROWS:
                session.commit()
                pending = 0
        if apply:
            session.commit()

    def _rewrite_jobs() -> None:
        for job in session.scalars(select(Job).where(Job.status.in_(("queued", "running")))):
            payload = dict(job.payload or {})
            text_enc, user_id = payload.get("text_enc"), payload.get("user_id")
            if not text_enc or not user_id:
                continue
            try:
                text = cipher.decrypt(text_enc, user_id)
            except CipherError:
                report.unreadable.append(f"queued job {job.id}: set ECHO_DATA_KEY_PREVIOUS")
                continue
            report.capture_jobs += 1
            if apply:
                payload["text_enc"] = cipher.encrypt(text, user_id)
                job.payload = payload
        if apply:
            session.commit()

    def _rewrite_admin_secrets() -> None:
        # Raw read/write on purpose: the ORM's SealedSecret column decrypts on load, so
        # assigning the value back would look unchanged and never rewrite the row.
        for admin_id, sealed in _admin_secrets(session):
            if not sealed or cipher.sealed_with_current_key(sealed):
                continue
            try:
                secret = cipher.unseal(sealed)
            except CipherError:
                report.unreadable.append(f"admin {admin_id}: set ECHO_DATA_KEY_PREVIOUS")
                continue
            report.admin_secrets += 1
            if apply:
                session.execute(
                    text("UPDATE admin_users SET mfa_secret = :sealed WHERE id = :id"),
                    {"sealed": cipher.seal(secret), "id": admin_id},
                )
        if apply:
            session.commit()

    def _rewrite_documents() -> None:
        for attachment in session.scalars(select(Attachment)):
            path = storage_dir / attachment.storage_key
            if not path.exists():
                report.unreadable.append(f"missing file: {attachment.storage_key}")
                continue
            try:
                data = cipher.decrypt_bytes(path.read_bytes(), attachment.user_id)
            except CipherError:
                report.unreadable.append(f"document {attachment.id}: set ECHO_DATA_KEY_PREVIOUS")
                continue
            report.documents += 1
            report.document_bytes += len(data)
            if apply:
                path.write_bytes(cipher.encrypt_bytes(data, attachment.user_id))

    _rewrite_memories()
    _rewrite_people()
    _rewrite_proposals()
    _rewrite_jobs()
    _rewrite_admin_secrets()
    _rewrite_documents()
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Rotate ECHO's data encryption key.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true", help="report what is still on an old key (default)")
    group.add_argument("--apply", action="store_true", help="rewrite everything under the current key")
    parser.add_argument("--database-url", default=None, help="override ECHO_DATABASE_URL")
    parser.add_argument("--storage-dir", default=None, help="override ECHO_STORAGE_DIR")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    cipher = build_cipher()
    if not hasattr(cipher, "keys"):
        print(
            "refusing to rotate: no ECHO_DATA_KEY is configured, so there is nothing to rotate",
            file=sys.stderr,
        )
        return 2
    if len(cipher.keys) < 2 and args.apply:
        print(
            "warning: only one key is configured, so rows under a retired key cannot be read.\n"
            "         set ECHO_DATA_KEY_PREVIOUS to the old key before applying.",
            file=sys.stderr,
        )

    url = args.database_url or settings.database_url
    storage_dir = Path(args.storage_dir or settings.storage_dir)
    engine = build_engine(url)
    session_factory = build_session_factory(engine)
    try:
        with session_factory() as session:
            if args.apply:
                report = rotate(session, cipher=cipher, storage_dir=storage_dir, apply=True)
                print("rewritten under the current key:")
            else:
                report = survey(session, cipher=cipher, storage_dir=storage_dir)
                print("still encrypted with a retired key:")
            print(f"  memory rows      {report.memories}")
            print(f"  person notes     {report.people}")
            print(f"  proposals        {report.proposals}")
            print(f"  queued captures  {report.capture_jobs}")
            print(f"  admin secrets    {report.admin_secrets}")
            print(f"  documents        {report.documents} ({report.document_bytes} bytes)")
            if report.unreadable:
                print("\nnot readable with the configured keys:", file=sys.stderr)
                for line in report.unreadable[:20]:
                    print(f"  {line}", file=sys.stderr)
                return 1
            if args.apply:
                print(
                    "\nnext: remove ECHO_DATA_KEY_PREVIOUS from the environment, restart, then run --check."
                )
            return 0
    finally:
        engine.dispose()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
