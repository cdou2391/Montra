"""initial schema

Revision ID: e29f20da4150
Revises: 
Create Date: 2026-08-23 23:51:33.312658
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = 'e29f20da4150'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('users',
    sa.Column('email', sa.String(length=320), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('display_name', sa.String(length=120), nullable=True),
    sa.Column('base_currency', sa.String(length=3), nullable=False),
    sa.Column('timezone', sa.String(length=64), nullable=False),
    sa.Column('status', sa.Enum('ACTIVE', 'DISABLED', name='user_status'), nullable=False),
    sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_users'))
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_table('categories',
    sa.Column('user_id', sa.UUID(), nullable=True),
    sa.Column('family_id', sa.UUID(), nullable=True),
    sa.Column('parent_category_id', sa.UUID(), nullable=True),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('category_type', sa.Enum('INCOME', 'EXPENSE', name='category_type'), nullable=False),
    sa.Column('is_system', sa.Boolean(), nullable=False),
    sa.Column('status', sa.Enum('ACTIVE', 'ARCHIVED', name='category_status'), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['parent_category_id'], ['categories.id'], name=op.f('fk_categories_parent_category_id_categories'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_categories_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_categories')),
    sa.UniqueConstraint('user_id', 'name', 'category_type', name='user_category_name')
    )
    op.create_index(op.f('ix_categories_family_id'), 'categories', ['family_id'], unique=False)
    op.create_index(op.f('ix_categories_user_id'), 'categories', ['user_id'], unique=False)
    op.create_table('institutions',
    sa.Column('user_id', sa.UUID(), nullable=True),
    sa.Column('name', sa.String(length=160), nullable=False),
    sa.Column('type', sa.Enum('BANK', 'MOBILE_MONEY', 'CARD_ISSUER', 'OTHER', name='institution_type'), nullable=True),
    sa.Column('country_code', sa.String(length=2), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_institutions_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_institutions'))
    )
    op.create_table('sessions',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_sessions_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sessions'))
    )
    op.create_index(op.f('ix_sessions_token_hash'), 'sessions', ['token_hash'], unique=True)
    op.create_index(op.f('ix_sessions_user_id'), 'sessions', ['user_id'], unique=False)
    op.create_table('user_preferences',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('hide_balances', sa.Boolean(), nullable=False),
    sa.Column('persist_balance_privacy', sa.Boolean(), nullable=False),
    sa.Column('default_context', sa.Enum('PERSONAL', 'FAMILY', name='context_type'), nullable=False),
    sa.Column('default_reminder_days', sa.Integer(), nullable=True),
    sa.Column('notifications_enabled', sa.Boolean(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_user_preferences_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_user_preferences')),
    sa.UniqueConstraint('user_id', name=op.f('uq_user_preferences_user_id'))
    )
    op.create_table('accounts',
    sa.Column('owner_user_id', sa.UUID(), nullable=True),
    sa.Column('family_id', sa.UUID(), nullable=True),
    sa.Column('institution_id', sa.UUID(), nullable=True),
    sa.Column('name', sa.String(length=160), nullable=False),
    sa.Column('account_type', sa.Enum('CHECKING', 'SAVINGS', 'CASH', 'MOBILE_MONEY', 'CREDIT_CARD', 'PREPAID_CARD', 'INVESTMENT', 'OTHER', name='account_type'), nullable=False),
    sa.Column('ownership_type', sa.Enum('PERSONAL', 'JOINT', name='ownership_type'), nullable=False),
    sa.Column('visibility', sa.Enum('PRIVATE', 'FAMILY_VISIBLE', 'SHARED', name='visibility'), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('opening_balance', sa.Numeric(precision=20, scale=4), nullable=False),
    sa.Column('opening_balance_date', sa.Date(), nullable=False),
    sa.Column('account_identifier', sa.String(length=64), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('status', sa.Enum('ACTIVE', 'ARCHIVED', name='account_status'), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=False),
    sa.Column('archived_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('(owner_user_id IS NOT NULL) OR (family_id IS NOT NULL)', name=op.f('ck_accounts_owner_or_family_required')),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_accounts_created_by_users'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['institution_id'], ['institutions.id'], name=op.f('fk_accounts_institution_id_institutions'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['owner_user_id'], ['users.id'], name=op.f('fk_accounts_owner_user_id_users'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_accounts'))
    )
    op.create_index(op.f('ix_accounts_family_id'), 'accounts', ['family_id'], unique=False)
    op.create_index('ix_accounts_owner_status', 'accounts', ['owner_user_id', 'status'], unique=False)
    op.create_index(op.f('ix_accounts_owner_user_id'), 'accounts', ['owner_user_id'], unique=False)
    op.create_table('transfers',
    sa.Column('source_account_id', sa.UUID(), nullable=False),
    sa.Column('destination_account_id', sa.UUID(), nullable=False),
    sa.Column('source_amount', sa.Numeric(precision=20, scale=4), nullable=False),
    sa.Column('destination_amount', sa.Numeric(precision=20, scale=4), nullable=False),
    sa.Column('source_currency', sa.String(length=3), nullable=False),
    sa.Column('destination_currency', sa.String(length=3), nullable=False),
    sa.Column('transfer_date', sa.Date(), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('status', sa.Enum('COMPLETED', 'CANCELLED', name='transfer_status'), nullable=False),
    sa.Column('idempotency_key', sa.String(length=255), nullable=True),
    sa.Column('created_by', sa.UUID(), nullable=False),
    sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('destination_amount > 0', name=op.f('ck_transfers_destination_amount_positive')),
    sa.CheckConstraint('source_account_id <> destination_account_id', name=op.f('ck_transfers_distinct_transfer_accounts')),
    sa.CheckConstraint('source_amount > 0', name=op.f('ck_transfers_source_amount_positive')),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_transfers_created_by_users'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['destination_account_id'], ['accounts.id'], name=op.f('fk_transfers_destination_account_id_accounts'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['source_account_id'], ['accounts.id'], name=op.f('fk_transfers_source_account_id_accounts'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_transfers')),
    sa.UniqueConstraint('created_by', 'idempotency_key', name='transfer_idempotency')
    )
    op.create_index(op.f('ix_transfers_idempotency_key'), 'transfers', ['idempotency_key'], unique=False)
    op.create_table('transactions',
    sa.Column('account_id', sa.UUID(), nullable=False),
    sa.Column('transaction_type', sa.Enum('INCOME', 'EXPENSE', 'TRANSFER', 'ADJUSTMENT', name='transaction_type'), nullable=False),
    sa.Column('amount', sa.Numeric(precision=20, scale=4), nullable=False),
    sa.Column('direction', sa.Enum('INCREASE', 'DECREASE', name='ledger_direction'), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('transaction_date', sa.Date(), nullable=False),
    sa.Column('status', sa.Enum('PENDING', 'COMPLETED', 'CANCELLED', name='transaction_status'), nullable=False),
    sa.Column('category_id', sa.UUID(), nullable=True),
    sa.Column('merchant', sa.String(length=160), nullable=True),
    sa.Column('description', sa.String(length=255), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('reference', sa.String(length=120), nullable=True),
    sa.Column('transfer_id', sa.UUID(), nullable=True),
    sa.Column('created_by', sa.UUID(), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('amount > 0', name=op.f('ck_transactions_amount_positive')),
    sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], name=op.f('fk_transactions_account_id_accounts'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['category_id'], ['categories.id'], name=op.f('fk_transactions_category_id_categories'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_transactions_created_by_users'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['transfer_id'], ['transfers.id'], name=op.f('fk_transactions_transfer_id_transfers'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_transactions'))
    )
    op.create_index('ix_transactions_account_date', 'transactions', ['account_id', 'transaction_date'], unique=False)
    op.create_index('ix_transactions_account_status_date', 'transactions', ['account_id', 'status', 'transaction_date'], unique=False)
    op.create_index(op.f('ix_transactions_transfer_id'), 'transactions', ['transfer_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_transactions_transfer_id'), table_name='transactions')
    op.drop_index('ix_transactions_account_status_date', table_name='transactions')
    op.drop_index('ix_transactions_account_date', table_name='transactions')
    op.drop_table('transactions')
    op.drop_index(op.f('ix_transfers_idempotency_key'), table_name='transfers')
    op.drop_table('transfers')
    op.drop_index(op.f('ix_accounts_owner_user_id'), table_name='accounts')
    op.drop_index('ix_accounts_owner_status', table_name='accounts')
    op.drop_index(op.f('ix_accounts_family_id'), table_name='accounts')
    op.drop_table('accounts')
    op.drop_table('user_preferences')
    op.drop_index(op.f('ix_sessions_user_id'), table_name='sessions')
    op.drop_index(op.f('ix_sessions_token_hash'), table_name='sessions')
    op.drop_table('sessions')
    op.drop_table('institutions')
    op.drop_index(op.f('ix_categories_user_id'), table_name='categories')
    op.drop_index(op.f('ix_categories_family_id'), table_name='categories')
    op.drop_table('categories')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')
