"""favorite account preference

Revision ID: e433e638f2b8
Revises: 7f8b8ea92fe3
Create Date: 2026-08-24 18:27:16.239352
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = 'e433e638f2b8'
down_revision: str | None = '7f8b8ea92fe3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('user_preferences', sa.Column('favorite_account_id', sa.UUID(), nullable=True))
    op.create_foreign_key(op.f('fk_user_preferences_favorite_account_id_accounts'), 'user_preferences', 'accounts', ['favorite_account_id'], ['id'], ondelete='SET NULL')


def downgrade() -> None:
    op.drop_constraint(op.f('fk_user_preferences_favorite_account_id_accounts'), 'user_preferences', type_='foreignkey')
    op.drop_column('user_preferences', 'favorite_account_id')
