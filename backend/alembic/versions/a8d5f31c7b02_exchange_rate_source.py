"""Record where an exchange rate came from.

Revision ID: a8d5f31c7b02
Revises: f2c6e91b8d45
"""

import sqlalchemy as sa
from alembic import op

revision = "a8d5f31c7b02"
down_revision = "f2c6e91b8d45"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "exchange_rates",
        sa.Column("source", sa.String(length=30), nullable=False, server_default="MANUAL"),
    )
    # Existing rows were all typed by hand, which is what the default says.
    # The server default is dropped so the application decides from here on.
    op.alter_column("exchange_rates", "source", server_default=None)


def downgrade() -> None:
    op.drop_column("exchange_rates", "source")
