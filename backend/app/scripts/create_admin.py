"""Create the first admin (and optionally a demo user).

    python -m app.scripts.create_admin --email ops@example.com

Prints the TOTP secret once and the otpauth:// URL to scan. It is not stored in
plaintext anywhere except the admin row, and can be rotated by re-running.
"""
from __future__ import annotations

import argparse
import getpass

from app.core.mfa import generate_secret, otpauth_url, totp_now
from app.core.security import hash_password
from app.db.models import AdminUser
from app.db.session import build_engine, build_session_factory, create_all
from app.repositories.system import AdminRepository


def main() -> None:
    parser = argparse.ArgumentParser(description="Create or rotate an ECHO admin account")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", help="omit to be prompted")
    parser.add_argument("--no-mfa", action="store_true", help="dev only: skip TOTP on login")
    args = parser.parse_args()

    password = args.password or getpass.getpass("admin password: ")
    engine = build_engine()
    create_all(engine)
    factory = build_session_factory(engine)

    secret = generate_secret()
    with factory() as session:
        repo = AdminRepository(session)
        admin = repo.by_email(args.email)
        if admin is None:
            admin = AdminUser(email=args.email.strip().lower())
            session.add(admin)
        admin.password_hash = hash_password(password)
        admin.mfa_secret = secret
        admin.mfa_required = not args.no_mfa
        admin.is_active = True
        session.commit()
        print(f"admin ready: {admin.email}")
        print(f"TOTP secret: {secret}")
        print(f"otpauth:     {otpauth_url(secret, admin.email)}")
        print(f"current code: {totp_now(secret)}")


if __name__ == "__main__":
    main()
