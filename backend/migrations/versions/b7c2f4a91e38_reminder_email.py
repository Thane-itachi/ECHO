"""reminder email: an opt-out flag, and a retrying outbox

Two halves of the same delivery.

`users.reminder_email_enabled` is the switch the account holder owns. It defaults to
true, because the existing behaviour was "reminders are scheduled and the email rows
are written", and a reminder nobody is told about is the bug this fixes. Existing
accounts keep receiving reminders until they say otherwise; every message carries a
one-click way to stop.

The outbox grows `attempts`, `last_error` and `available_at`. A provider outage used
to be a single shot: the row was marked failed and the reminder was lost. Now a
transient failure backs off and is retried, and only a message that keeps failing is
marked failed.

Revision ID: b7c2f4a91e38
Revises: 896e19f68b2c
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b7c2f4a91e38"
down_revision: Union[str, Sequence[str], None] = "896e19f68b2c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(
            sa.Column("reminder_email_enabled", sa.Boolean(), nullable=False, server_default=sa.true())
        )
    with op.batch_alter_table("users") as batch:
        batch.alter_column("reminder_email_enabled", server_default=None)

    with op.batch_alter_table("outbox") as batch:
        batch.add_column(sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("last_error", sa.Text(), nullable=True))
        batch.add_column(sa.Column("available_at", sa.DateTime(), nullable=True))
    with op.batch_alter_table("outbox") as batch:
        batch.alter_column("attempts", server_default=None)

    # `suppressed` joins pending/sent/failed. SQLite enforces CHECK constraints only
    # when the table is rebuilt, which batch_alter_table does; PostgreSQL needs the old
    # constraint dropped first.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE outbox DROP CONSTRAINT IF EXISTS ck_outbox_status")
        op.execute(
            "ALTER TABLE outbox ADD CONSTRAINT ck_outbox_status "
            "CHECK (status IN ('pending', 'sent', 'failed', 'suppressed'))"
        )
    else:
        with op.batch_alter_table("outbox", recreate="always") as batch:
            batch.drop_constraint("ck_outbox_status", type_="check")
            batch.create_check_constraint(
                "ck_outbox_status", "status IN ('pending', 'sent', 'failed', 'suppressed')"
            )


def downgrade() -> None:
    bind = op.get_bind()
    op.execute("UPDATE outbox SET status = 'failed' WHERE status = 'suppressed'")
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE outbox DROP CONSTRAINT IF EXISTS ck_outbox_status")
        op.execute(
            "ALTER TABLE outbox ADD CONSTRAINT ck_outbox_status CHECK (status IN ('pending', 'sent', 'failed'))"
        )
    else:
        with op.batch_alter_table("outbox", recreate="always") as batch:
            batch.drop_constraint("ck_outbox_status", type_="check")
            batch.create_check_constraint("ck_outbox_status", "status IN ('pending', 'sent', 'failed')")
    with op.batch_alter_table("outbox") as batch:
        batch.drop_column("available_at")
        batch.drop_column("last_error")
        batch.drop_column("attempts")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("reminder_email_enabled")
