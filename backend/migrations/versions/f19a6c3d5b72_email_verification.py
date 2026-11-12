"""email verification and codes by email

Adds the columns ordinary users need to prove an address and to opt into a code at
sign-in, plus `email_codes`, which stores only keyed digests of six-digit codes.

Existing accounts are marked verified: they were created before verification existed,
and locking them out on upgrade would be a worse outcome than grandfathering them.
Their addresses are no easier to spoof after this migration than before it.

Revision ID: f19a6c3d5b72
Revises: c4a1e9d7b260
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f19a6c3d5b72"
down_revision: Union[str, Sequence[str], None] = "c4a1e9d7b260"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("email_otp_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("credentials_changed_at", sa.DateTime(), nullable=True))

    # Grandfather pre-existing accounts, then drop the server default so new rows must
    # be explicit (the application always sets it).
    op.execute("UPDATE users SET email_verified = true")
    with op.batch_alter_table("users") as batch:
        batch.alter_column("email_verified", server_default=None)
        batch.alter_column("email_otp_enabled", server_default=None)

    op.create_table(
        "email_codes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("purpose", sa.String(length=32), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("consumed_at", sa.DateTime(), nullable=True),
        sa.Column("request_ip", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "purpose IN ('verify_email','login_otp','password_reset')", name="ck_email_code_purpose"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_email_codes_email", "email_codes", ["email"])
    op.create_index("ix_email_codes_user_id", "email_codes", ["user_id"])
    op.create_index("ix_email_codes_request_ip", "email_codes", ["request_ip"])
    op.create_index("ix_email_codes_created_at", "email_codes", ["created_at"])
    op.create_index("ix_email_codes_lookup", "email_codes", ["email", "purpose", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_email_codes_lookup", table_name="email_codes")
    op.drop_index("ix_email_codes_created_at", table_name="email_codes")
    op.drop_index("ix_email_codes_request_ip", table_name="email_codes")
    op.drop_index("ix_email_codes_user_id", table_name="email_codes")
    op.drop_index("ix_email_codes_email", table_name="email_codes")
    op.drop_table("email_codes")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("credentials_changed_at")
        batch.drop_column("email_otp_enabled")
        batch.drop_column("email_verified")
