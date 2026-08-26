"""Light or dark, or follow the device.

Revision ID: c9e1f4a70b83
Revises: b6e0a47d92c1
"""

import sqlalchemy as sa
from alembic import op

revision = "c9e1f4a70b83"
down_revision = "b6e0a47d92c1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_preferences",
        sa.Column("theme", sa.String(length=10), nullable=False, server_default="SYSTEM"),
    )
    # Existing users follow their device, which is the least surprising thing
    # to do to someone who never asked for a theme.
    op.alter_column("user_preferences", "theme", server_default=None)


def downgrade() -> None:
    op.drop_column("user_preferences", "theme")
