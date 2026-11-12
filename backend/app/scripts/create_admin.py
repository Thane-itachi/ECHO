"""Create (or rotate) an administrator.

    python -m app.scripts.create_admin --email ops@example.com --role founder

Prints the TOTP secret once and the `otpauth://` URL to scan. There is **no**
`--no-mfa` flag any more: an administrator row cannot exist without an enrolled
secret, and login cannot mint a token without a verified code. If someone is locked
out, `--rotate` issues a new secret for an existing account; that is the only
recovery path, and it is a deliberate shell-level action.
"""
from __future__ import annotations

import argparse
import getpass

from app.core.mfa import generate_secret, otpauth_url, totp_now
from app.core.security import hash_password
from app.db.models import ADMIN_ROLES, AdminUser
from app.db.session import build_engine, build_session_factory, create_all
from app.repositories.system import AdminRepository


def main() -> None:
    parser = argparse.ArgumentParser(description="Create or rotate an ECHO admin account")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", help="omit to be prompted")
    parser.add_argument(
        "--role",
        default=None,
        choices=ADMIN_ROLES,
        help="founder | platform_admin | support_admin (default: founder for the first admin)",
    )
    parser.add_argument("--rotate", action="store_true", help="issue a new TOTP secret for this account")
    args = parser.parse_args()

    engine = build_engine()
    create_all(engine)
    factory = build_session_factory(engine)

    with factory() as session:
        repo = AdminRepository(session)
        existing = repo.by_email(args.email)
        password = args.password
        if password is None and (existing is None or not args.rotate):
            password = getpass.getpass("admin password: ")

        secret = generate_secret()
        if existing is None:
            if password is None:
                parser.error("--password is required when creating an account")
            role = args.role or "founder"
            admin = AdminUser(
                email=args.email.strip().lower(),
                password_hash=hash_password(password),
                mfa_secret=secret,
                role=role,
                is_active=True,
            )
            session.add(admin)
            action = "created"
        else:
            admin = existing
            if password:
                admin.password_hash = hash_password(password)
            if args.rotate:
                admin.mfa_secret = secret
            else:
                secret = admin.mfa_secret
            if args.role:
                admin.role = args.role
            admin.is_active = True
            action = "updated"
        session.commit()

        print(f"admin {action}: {admin.email} (role: {admin.role})")
        print(f"TOTP secret: {secret}")
        print(f"otpauth:     {otpauth_url(secret, admin.email)}")
        print(f"current code: {totp_now(secret)}")


if __name__ == "__main__":
    main()
