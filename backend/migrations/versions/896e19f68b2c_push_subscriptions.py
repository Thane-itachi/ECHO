"""push subscriptions

One row per browser or phone that agreed to receive notifications. The endpoint is
unique: the same device signing in as another user must not leave the first account
able to notify it.

Revision ID: 896e19f68b2c
Revises: f19a6c3d5b72
Create Date: 2026-11-12 12:17:13.675985
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "896e19f68b2c"
down_revision: Union[str, Sequence[str], None] = "f19a6c3d5b72"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "push_subscriptions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("endpoint", sa.String(length=512), nullable=False),
        sa.Column("p256dh", sa.String(length=200), nullable=False),
        sa.Column("auth", sa.String(length=64), nullable=False),
        sa.Column("user_agent", sa.String(length=200), nullable=True),
        sa.Column("failure_count", sa.Integer(), nullable=False),
        sa.Column("last_success_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("endpoint", name="uq_push_subscriptions_endpoint"),
    )
    op.create_index(
        "ix_push_subscriptions_user_id", "push_subscriptions", ["user_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_push_subscriptions_user_id", table_name="push_subscriptions")
    op.drop_table("push_subscriptions")
