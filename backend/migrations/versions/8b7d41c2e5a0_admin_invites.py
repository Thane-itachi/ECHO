"""administrator enrolment links

Adds `admin_invites`: one-time, time-boxed links that let someone choose their own
administrator password and enrol their own authenticator, so no password or TOTP
secret ever passes through the person creating the account.

Revision ID: 8b7d41c2e5a0
Revises: d569c265930d
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "8b7d41c2e5a0"
down_revision: Union[str, Sequence[str], None] = "d569c265930d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "admin_invites",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.Column("issued_by", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "role IN ('founder', 'platform_admin', 'support_admin')",
            name="ck_admin_invites_role",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_admin_invites_email"), "admin_invites", ["email"], unique=False)
    op.create_index(
        op.f("ix_admin_invites_token_hash"), "admin_invites", ["token_hash"], unique=True
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_admin_invites_token_hash"), table_name="admin_invites")
    op.drop_index(op.f("ix_admin_invites_email"), table_name="admin_invites")
    op.drop_table("admin_invites")
