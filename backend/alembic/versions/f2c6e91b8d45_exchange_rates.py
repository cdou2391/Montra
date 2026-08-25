"""User-maintained exchange rates.

Reporting only: a converted value never replaces an original amount (Data
Model section 65).

Revision ID: f2c6e91b8d45
Revises: e5b8d3c04a17
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "f2c6e91b8d45"
down_revision = "e5b8d3c04a17"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "exchange_rates",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("base_currency", sa.String(length=3), nullable=False),
        sa.Column("quote_currency", sa.String(length=3), nullable=False),
        sa.Column("rate", sa.Numeric(20, 8), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "base_currency", "quote_currency", name="user_currency_pair"
        ),
        sa.CheckConstraint("rate > 0", name="exchange_rate_positive"),
        sa.CheckConstraint("base_currency <> quote_currency", name="exchange_rate_distinct"),
    )
    op.create_index("ix_exchange_rates_user_id", "exchange_rates", ["user_id"])


def downgrade() -> None:
    op.drop_table("exchange_rates")
