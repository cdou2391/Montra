"""record occurrence time not just date

Transactions, transfers and account opening balances move from DATE to
TIMESTAMP WITH TIME ZONE, so Montra records when money actually moved rather
than only which day it moved on.

Existing rows are backfilled at local midnight of the stored date, using each
row's owning user's timezone, so a recorded date keeps its calendar day for
users on either side of UTC. Autogenerate wanted an add-then-drop here, which
would have discarded every stored date.

Revision ID: 852d7a61ba3d
Revises: e29f20da4150
Create Date: 2026-08-24 14:12:04.617522
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "852d7a61ba3d"
down_revision: str | None = "e29f20da4150"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- accounts ----------------------------------------------------------
    op.add_column(
        "accounts", sa.Column("opening_balance_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.execute(
        """
        UPDATE accounts a
           SET opening_balance_at =
               (a.opening_balance_date::timestamp AT TIME ZONE COALESCE(u.timezone, 'UTC'))
          FROM users u
         WHERE u.id = a.owner_user_id
        """
    )
    # Accounts with no owner (purely shared, once Family ships) fall back to UTC.
    op.execute(
        """
        UPDATE accounts
           SET opening_balance_at = (opening_balance_date::timestamp AT TIME ZONE 'UTC')
         WHERE opening_balance_at IS NULL
        """
    )
    op.alter_column("accounts", "opening_balance_at", nullable=False)
    op.drop_column("accounts", "opening_balance_date")

    # --- transactions ------------------------------------------------------
    op.add_column(
        "transactions", sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.execute(
        """
        UPDATE transactions t
           SET occurred_at =
               (t.transaction_date::timestamp AT TIME ZONE COALESCE(u.timezone, 'UTC'))
          FROM users u
         WHERE u.id = t.created_by
        """
    )
    op.execute(
        """
        UPDATE transactions
           SET occurred_at = (transaction_date::timestamp AT TIME ZONE 'UTC')
         WHERE occurred_at IS NULL
        """
    )
    op.alter_column("transactions", "occurred_at", nullable=False)

    op.drop_index("ix_transactions_account_date", table_name="transactions")
    op.drop_index("ix_transactions_account_status_date", table_name="transactions")
    op.create_index(
        "ix_transactions_account_occurred", "transactions", ["account_id", "occurred_at"]
    )
    op.create_index(
        "ix_transactions_account_status_occurred",
        "transactions",
        ["account_id", "status", "occurred_at"],
    )
    op.drop_column("transactions", "transaction_date")

    # --- transfers ---------------------------------------------------------
    op.add_column("transfers", sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True))
    op.execute(
        """
        UPDATE transfers t
           SET occurred_at =
               (t.transfer_date::timestamp AT TIME ZONE COALESCE(u.timezone, 'UTC'))
          FROM users u
         WHERE u.id = t.created_by
        """
    )
    op.execute(
        """
        UPDATE transfers
           SET occurred_at = (transfer_date::timestamp AT TIME ZONE 'UTC')
         WHERE occurred_at IS NULL
        """
    )
    op.alter_column("transfers", "occurred_at", nullable=False)
    op.drop_column("transfers", "transfer_date")


def downgrade() -> None:
    """Reverses the schema. Time of day is lost, which is the point of the
    column being added — a downgrade cannot invent it back."""
    op.add_column("transfers", sa.Column("transfer_date", sa.DATE(), nullable=True))
    op.execute(
        """
        UPDATE transfers t
           SET transfer_date =
               (t.occurred_at AT TIME ZONE COALESCE(u.timezone, 'UTC'))::date
          FROM users u
         WHERE u.id = t.created_by
        """
    )
    op.execute(
        "UPDATE transfers SET transfer_date = (occurred_at AT TIME ZONE 'UTC')::date "
        "WHERE transfer_date IS NULL"
    )
    op.alter_column("transfers", "transfer_date", nullable=False)
    op.drop_column("transfers", "occurred_at")

    op.add_column("transactions", sa.Column("transaction_date", sa.DATE(), nullable=True))
    op.execute(
        """
        UPDATE transactions t
           SET transaction_date =
               (t.occurred_at AT TIME ZONE COALESCE(u.timezone, 'UTC'))::date
          FROM users u
         WHERE u.id = t.created_by
        """
    )
    op.execute(
        "UPDATE transactions SET transaction_date = (occurred_at AT TIME ZONE 'UTC')::date "
        "WHERE transaction_date IS NULL"
    )
    op.alter_column("transactions", "transaction_date", nullable=False)
    op.drop_index("ix_transactions_account_status_occurred", table_name="transactions")
    op.drop_index("ix_transactions_account_occurred", table_name="transactions")
    op.create_index(
        "ix_transactions_account_status_date",
        "transactions",
        ["account_id", "status", "transaction_date"],
    )
    op.create_index(
        "ix_transactions_account_date", "transactions", ["account_id", "transaction_date"]
    )
    op.drop_column("transactions", "occurred_at")

    op.add_column("accounts", sa.Column("opening_balance_date", sa.DATE(), nullable=True))
    op.execute(
        """
        UPDATE accounts a
           SET opening_balance_date =
               (a.opening_balance_at AT TIME ZONE COALESCE(u.timezone, 'UTC'))::date
          FROM users u
         WHERE u.id = a.owner_user_id
        """
    )
    op.execute(
        "UPDATE accounts SET opening_balance_date = (opening_balance_at AT TIME ZONE 'UTC')::date "
        "WHERE opening_balance_date IS NULL"
    )
    op.alter_column("accounts", "opening_balance_date", nullable=False)
    op.drop_column("accounts", "opening_balance_at")
