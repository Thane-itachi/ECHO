"""Create an administrator, or mint a link that does it without you.

Two ways in:

    # 1. The good one: they choose their own password and authenticator secret.
    python -m app.scripts.create_admin --email ops@example.com --invite

    # 2. The old one: you set both, then hand the secret over out of band.
    python -m app.scripts.create_admin --email ops@example.com --role founder

`--invite` prints a single-use link (72 hours by default). The person opening it sets
their own password and scans their own QR code; nobody, including whoever ran this
command, ever learns either secret. Use `--revoke-invites` to kill links you regret.

There is **no** `--no-mfa` flag: an administrator row cannot exist without an enrolled
secret, and login cannot mint a token without a verified code. `--rotate` replaces an
existing account's secret, which is the shell-level recovery path when the only
administrator is locked out.
"""
from __future__ import annotations

import argparse
import getpass
import os

from app.admin import enrolment
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
    parser.add_argument(
        "--invite",
        action="store_true",
        help="mint a single-use enrolment link instead of setting a password here",
    )
    parser.add_argument(
        "--revoke-invites", action="store_true", help="cancel every open enrolment link for this email"
    )
    parser.add_argument(
        "--expires-hours", type=int, default=72, help="how long an enrolment link lives (default 72)"
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("ECHO_WEB_BASE_URL", "http://127.0.0.1:5173"),
        help="web origin used to print the enrolment URL",
    )
    args = parser.parse_args()

    engine = build_engine()
    create_all(engine)
    factory = build_session_factory(engine)

    with factory() as session:
        repo = AdminRepository(session)

        if args.revoke_invites:
            revoked = enrolment.revoke_invites(session, email=args.email)
            print(f"revoked {revoked} open enrolment link(s) for {args.email.strip().lower()}")
            return

        if args.invite:
            invite, token = enrolment.issue_invite(
                session,
                email=args.email,
                role=args.role or "founder",
                issued_by=None,
                ttl_hours=args.expires_hours,
            )
            print(f"enrolment link for {invite.email} (role: {invite.role})")
            print(f"expires: {invite.expires_at:%Y-%m-%d %H:%M} UTC ({args.expires_hours}h)")
            print(f"open:    {args.base_url.rstrip('/')}/admin/enrol?token={token}")
            print("single use, and only they see the password and the authenticator secret")
            return

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
