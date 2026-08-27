"""recurring transfers

Revision ID: ea2fb83ba6d5
Revises: e433e638f2b8
Create Date: 2026-08-24 20:26:27.917414
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = 'ea2fb83ba6d5'
down_revision: str | None = 'e433e638f2b8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Autogenerate does not notice new enum values. TRANSFER is only added
    # here, never used in this same transaction, which Postgres allows.
    op.execute("ALTER TYPE planned_type ADD VALUE IF NOT EXISTS 'TRANSFER'")

    op.add_column('planned_transactions', sa.Column('destination_account_id', sa.UUID(), nullable=True))
    op.add_column('planned_transactions', sa.Column('completed_transfer_id', sa.UUID(), nullable=True))
    op.create_foreign_key(op.f('fk_planned_transactions_completed_transfer_id_transfers'), 'planned_transactions', 'transfers', ['completed_transfer_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key(op.f('fk_planned_transactions_destination_account_id_accounts'), 'planned_transactions', 'accounts', ['destination_account_id'], ['id'], ondelete='CASCADE')
    op.add_column('recurring_rules', sa.Column('destination_account_id', sa.UUID(), nullable=True))
    op.create_foreign_key(op.f('fk_recurring_rules_destination_account_id_accounts'), 'recurring_rules', 'accounts', ['destination_account_id'], ['id'], ondelete='CASCADE')


def downgrade() -> None:
    # Postgres cannot remove a value from an enum type. TRANSFER stays behind,
    # which is harmless: nothing reads it once the columns are gone.

    op.drop_constraint(op.f('fk_recurring_rules_destination_account_id_accounts'), 'recurring_rules', type_='foreignkey')
    op.drop_column('recurring_rules', 'destination_account_id')
    op.drop_constraint(op.f('fk_planned_transactions_destination_account_id_accounts'), 'planned_transactions', type_='foreignkey')
    op.drop_constraint(op.f('fk_planned_transactions_completed_transfer_id_transfers'), 'planned_transactions', type_='foreignkey')
    op.drop_column('planned_transactions', 'completed_transfer_id')
    op.drop_column('planned_transactions', 'destination_account_id')
