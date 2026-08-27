"""An account can be kept out of the net-worth totals.

Revision ID: a1c4e70d5b92
Revises: c9e1f4a70b83
"""

import sqlalchemy as sa
from alembic import op

revision = "a1c4e70d5b92"
down_revision = "c9e1f4a70b83"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "accounts",
        sa.Column(
            "excluded_from_totals",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    # The default exists only to fill the existing rows. Leaving it in place
    # would let an INSERT that forgets the column quietly succeed, and the
    # model supplies it on every write.
    op.alter_column("accounts", "excluded_from_totals", server_default=None)


def downgrade() -> None:
    op.drop_column("accounts", "excluded_from_totals")
