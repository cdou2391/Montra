"""Card expiry notifications.

The expiry columns already exist on accounts; what is
new is a notification type for them.

Revision ID: b1c4e7d2a9f0
Revises: a6500165a58f
"""

from alembic import op

revision = "b1c4e7d2a9f0"
down_revision = "a6500165a58f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Autogenerate does not notice new members of an existing enum, and
    # ALTER TYPE ... ADD VALUE cannot run inside a transaction on older
    # servers, so it is issued with autocommit.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'CARD_EXPIRING'")


def downgrade() -> None:
    # Postgres cannot drop a single enum value. Rows carrying it are rewritten
    # to SYSTEM so nothing dangles; the label itself stays behind.
    op.execute(
        "UPDATE notifications SET notification_type = 'SYSTEM' "
        "WHERE notification_type = 'CARD_EXPIRING'"
    )
