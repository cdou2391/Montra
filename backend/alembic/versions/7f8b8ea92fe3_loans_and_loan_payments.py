"""loans and loan payments

Revision ID: 7f8b8ea92fe3
Revises: 7e6359b3c1b6
Create Date: 2026-08-24 16:36:07.647478
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = '7f8b8ea92fe3'
down_revision: str | None = '7e6359b3c1b6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# These enum types already exist from earlier migrations. Declared with
# create_type=False so create_table reuses them instead of emitting a
# CREATE TYPE that fails with "type already exists".
VISIBILITY = postgresql.ENUM(
    "PRIVATE", "FAMILY_VISIBLE", "SHARED", name="visibility", create_type=False
)
OWNERSHIP_TYPE = postgresql.ENUM(
    "PERSONAL", "JOINT", name="ownership_type", create_type=False
)
FREQUENCY = postgresql.ENUM(
    "DAILY", "WEEKLY", "MONTHLY", "QUARTERLY", "YEARLY",
    name="recurrence_frequency", create_type=False,
)


def upgrade() -> None:
    op.create_table('loans',
    sa.Column('owner_user_id', sa.UUID(), nullable=True),
    sa.Column('family_id', sa.UUID(), nullable=True),
    sa.Column('direction', sa.Enum('PAYABLE', 'RECEIVABLE', name='loan_direction'), nullable=False),
    sa.Column('visibility', VISIBILITY, nullable=False),
    sa.Column('ownership_type', OWNERSHIP_TYPE, nullable=False),
    sa.Column('name', sa.String(length=160), nullable=False),
    sa.Column('counterparty', sa.String(length=160), nullable=True),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('original_principal', sa.Numeric(precision=20, scale=4), nullable=False),
    sa.Column('opening_outstanding_principal', sa.Numeric(precision=20, scale=4), nullable=False),
    sa.Column('interest_rate', sa.Numeric(precision=10, scale=6), nullable=True),
    sa.Column('start_date', sa.Date(), nullable=False),
    sa.Column('end_date', sa.Date(), nullable=True),
    sa.Column('expected_payment_amount', sa.Numeric(precision=20, scale=4), nullable=True),
    sa.Column('payment_frequency', FREQUENCY, nullable=True),
    sa.Column('next_payment_date', sa.Date(), nullable=True),
    sa.Column('status', sa.Enum('ACTIVE', 'SETTLED', 'ARCHIVED', name='loan_status'), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_by', sa.UUID(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('end_date IS NULL OR end_date >= start_date', name=op.f('ck_loans_loan_end_after_start')),
    sa.CheckConstraint('opening_outstanding_principal >= 0', name=op.f('ck_loans_opening_outstanding_non_negative')),
    sa.CheckConstraint('original_principal >= 0', name=op.f('ck_loans_original_principal_non_negative')),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_loans_created_by_users'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['owner_user_id'], ['users.id'], name=op.f('fk_loans_owner_user_id_users'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_loans'))
    )
    op.create_index(op.f('ix_loans_family_id'), 'loans', ['family_id'], unique=False)
    op.create_index('ix_loans_owner_status', 'loans', ['owner_user_id', 'status'], unique=False)
    op.create_index(op.f('ix_loans_owner_user_id'), 'loans', ['owner_user_id'], unique=False)
    op.create_table('loan_payments',
    sa.Column('loan_id', sa.UUID(), nullable=False),
    sa.Column('account_id', sa.UUID(), nullable=False),
    sa.Column('payment_date', sa.Date(), nullable=False),
    sa.Column('total_amount', sa.Numeric(precision=20, scale=4), nullable=False),
    sa.Column('principal_amount', sa.Numeric(precision=20, scale=4), nullable=False),
    sa.Column('interest_amount', sa.Numeric(precision=20, scale=4), nullable=False),
    sa.Column('fee_amount', sa.Numeric(precision=20, scale=4), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('idempotency_key', sa.String(length=255), nullable=True),
    sa.Column('created_by', sa.UUID(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('fee_amount >= 0', name=op.f('ck_loan_payments_loan_fee_non_negative')),
    sa.CheckConstraint('interest_amount >= 0', name=op.f('ck_loan_payments_loan_interest_non_negative')),
    sa.CheckConstraint('principal_amount + interest_amount + fee_amount = total_amount', name=op.f('ck_loan_payments_loan_payment_allocation_balances')),
    sa.CheckConstraint('principal_amount >= 0', name=op.f('ck_loan_payments_loan_principal_non_negative')),
    sa.CheckConstraint('total_amount > 0', name=op.f('ck_loan_payments_loan_payment_total_positive')),
    sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], name=op.f('fk_loan_payments_account_id_accounts'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_loan_payments_created_by_users'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['loan_id'], ['loans.id'], name=op.f('fk_loan_payments_loan_id_loans'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_loan_payments')),
    sa.UniqueConstraint('created_by', 'idempotency_key', name='loan_payment_idempotency')
    )
    op.create_index('ix_loan_payments_loan_date', 'loan_payments', ['loan_id', 'payment_date'], unique=False)
    op.create_index(op.f('ix_loan_payments_loan_id'), 'loan_payments', ['loan_id'], unique=False)
    op.add_column('transactions', sa.Column('loan_payment_id', sa.UUID(), nullable=True))
    op.create_index(op.f('ix_transactions_loan_payment_id'), 'transactions', ['loan_payment_id'], unique=False)
    op.create_foreign_key(op.f('fk_transactions_loan_payment_id_loan_payments'), 'transactions', 'loan_payments', ['loan_payment_id'], ['id'], ondelete='CASCADE')


def downgrade() -> None:
    op.drop_constraint(op.f('fk_transactions_loan_payment_id_loan_payments'), 'transactions', type_='foreignkey')
    op.drop_index(op.f('ix_transactions_loan_payment_id'), table_name='transactions')
    op.drop_column('transactions', 'loan_payment_id')
    op.drop_index(op.f('ix_loan_payments_loan_id'), table_name='loan_payments')
    op.drop_index('ix_loan_payments_loan_date', table_name='loan_payments')
    op.drop_table('loan_payments')
    op.drop_index(op.f('ix_loans_owner_user_id'), table_name='loans')
    op.drop_index('ix_loans_owner_status', table_name='loans')
    op.drop_index(op.f('ix_loans_family_id'), table_name='loans')
    op.drop_table('loans')

    # Alembic drops the tables but leaves the enum types, which would make
    # upgrading again fail with "type already exists".
    for enum_name in ("loan_direction", "loan_status"):
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
