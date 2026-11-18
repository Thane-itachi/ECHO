"""people hold commitments, and what they are to you

The People page used to be a name and a paragraph. Three questions it could not
answer are the ones people actually ask: who is this person to me, what dates do
I keep for them, and what is still owed between us.

`people` gains two encrypted columns - the relationship label and the key dates
as JSON - because both are as personal as the notes beside them. `commitments`
is a new table for promises, things lent and things borrowed: one row each, in
either direction, optionally pinned to the note and the person it came from, and
optionally carrying a date so it can become a reminder in one tap.

Revision ID: d3f8a2b6c741
Revises: b7c2f4a91e38
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d3f8a2b6c741"
down_revision: Union[str, Sequence[str], None] = "b7c2f4a91e38"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

KINDS = ("promise", "lent", "borrowed")
STATUSES = ("open", "done", "dropped")


def upgrade() -> None:
    with op.batch_alter_table("people") as batch:
        batch.add_column(sa.Column("relationship_enc", sa.Text(), nullable=True))
        batch.add_column(sa.Column("dates_enc", sa.Text(), nullable=True))

    op.create_table(
        "commitments",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("person_id", sa.String(length=36), sa.ForeignKey("people.id", ondelete="SET NULL"), nullable=True),
        sa.Column("memory_id", sa.String(length=36), sa.ForeignKey("memories.id", ondelete="SET NULL"), nullable=True),
        sa.Column("kind", sa.String(length=16), nullable=False, server_default="promise"),
        sa.Column("text_enc", sa.Text(), nullable=False),
        sa.Column("due_on", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="open"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(f"kind IN {tuple(KINDS)}", name="ck_commitments_kind"),
        sa.CheckConstraint(f"status IN {tuple(STATUSES)}", name="ck_commitments_status"),
    )
    op.create_index("ix_commitments_user_id", "commitments", ["user_id"])
    op.create_index("ix_commitments_person_id", "commitments", ["person_id"])
    op.create_index("ix_commitments_due_on", "commitments", ["due_on"])
    op.create_index("ix_commitments_owner_status", "commitments", ["user_id", "status", "due_on"])


def downgrade() -> None:
    op.drop_index("ix_commitments_owner_status", table_name="commitments")
    op.drop_index("ix_commitments_due_on", table_name="commitments")
    op.drop_index("ix_commitments_person_id", table_name="commitments")
    op.drop_index("ix_commitments_user_id", table_name="commitments")
    op.drop_table("commitments")
    with op.batch_alter_table("people") as batch:
        batch.drop_column("dates_enc")
        batch.drop_column("relationship_enc")
