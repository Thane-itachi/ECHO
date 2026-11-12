"""seal administrator TOTP seeds

`admin_users.mfa_secret` used to be an ordinary varchar: a database dump handed over
every administrator's second factor, which quietly turned "MFA is mandatory" into
"MFA is mandatory until someone reads the backups".

The column now stores a value sealed under the system key derivation
(`HKDF(EchoDataKey, salt=echo/system-secret/v1)`), which is unrelated to any user's
content key. This migration widens the column for databases that care about varchar
lengths and seals the rows that are still plaintext. Reading is tolerant either way, so
an upgrade cannot lock an administrator out even if the data key is missing.

Revision ID: c4a1e9d7b260
Revises: 8b7d41c2e5a0
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.core.crypto import get_default_cipher

revision: str = "c4a1e9d7b260"
down_revision: Union[str, Sequence[str], None] = "8b7d41c2e5a0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        # SQLite stores the longer sealed value in the existing column and a batch
        # alter would rebuild the table (dropping its CHECK constraint), so only the
        # databases with real varchar limits need the type change.
        op.alter_column(
            "admin_users",
            "mfa_secret",
            existing_type=sa.String(length=64),
            type_=sa.Text(),
            existing_nullable=False,
        )
    _seal_plaintext_rows(bind)


def _seal_plaintext_rows(bind) -> None:
    cipher = get_default_cipher()
    rows = bind.execute(sa.text("SELECT id, mfa_secret FROM admin_users")).fetchall()
    for row_id, value in rows:
        if not value or cipher.is_sealed(value):
            continue
        bind.execute(
            sa.text("UPDATE admin_users SET mfa_secret = :sealed WHERE id = :id"),
            {"sealed": cipher.seal(value), "id": row_id},
        )


def downgrade() -> None:
    bind = op.get_bind()
    cipher = get_default_cipher()
    rows = bind.execute(sa.text("SELECT id, mfa_secret FROM admin_users")).fetchall()
    for row_id, value in rows:
        if not value or not cipher.is_sealed(value):
            continue
        bind.execute(
            sa.text("UPDATE admin_users SET mfa_secret = :plain WHERE id = :id"),
            {"plain": cipher.unseal(value), "id": row_id},
        )
    if bind.dialect.name != "sqlite":
        op.alter_column(
            "admin_users",
            "mfa_secret",
            existing_type=sa.Text(),
            type_=sa.String(length=64),
            existing_nullable=False,
        )
