"""A shared table of published exchange rates.

Revision ID: b6e0a47d92c1
Revises: a8d5f31c7b02
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "b6e0a47d92c1"
down_revision = "a8d5f31c7b02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "market_rates",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("base_currency", sa.String(length=3), nullable=False),
        sa.Column("quote_currency", sa.String(length=3), nullable=False),
        sa.Column("rate", sa.Numeric(20, 8), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("base_currency", "quote_currency", name="market_currency_pair"),
        sa.CheckConstraint("rate > 0", name="market_rate_positive"),
        sa.CheckConstraint("base_currency <> quote_currency", name="market_rate_distinct"),
    )
    op.create_index("ix_market_rates_base", "market_rates", ["base_currency"])


def downgrade() -> None:
    op.drop_table("market_rates")
