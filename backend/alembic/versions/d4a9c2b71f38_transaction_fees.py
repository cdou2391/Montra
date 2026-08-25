"""Fees charged on a transaction.

A fee is its own transaction row rather than a column on the one it relates
to: the money really left the account, so it has to be in the ledger as its
own movement. The link records what it was charged on.

Revision ID: d4a9c2b71f38
Revises: c7f3a1d8e604
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "d4a9c2b71f38"
down_revision = "c7f3a1d8e604"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "transactions",
        sa.Column("fee_for_transaction_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_transactions_fee_for_transaction_id_transactions",
        "transactions",
        "transactions",
        ["fee_for_transaction_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_transactions_fee_for_transaction_id", "transactions", ["fee_for_transaction_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_transactions_fee_for_transaction_id", table_name="transactions")
    op.drop_constraint(
        "fk_transactions_fee_for_transaction_id_transactions", "transactions", type_="foreignkey"
    )
    op.drop_column("transactions", "fee_for_transaction_id")
