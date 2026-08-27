"""family foundation

Revision ID: a6500165a58f
Revises: ea2fb83ba6d5
Create Date: 2026-08-24 23:00:23.477017
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = 'a6500165a58f'
down_revision: str | None = 'ea2fb83ba6d5'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('families',
    sa.Column('name', sa.String(length=160), nullable=False),
    sa.Column('base_currency', sa.String(length=3), nullable=False),
    sa.Column('status', sa.Enum('ACTIVE', 'INACTIVE', name='family_status'), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=False),
    sa.Column('deactivated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_families_created_by_users'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_families'))
    )
    op.create_table('family_invitations',
    sa.Column('family_id', sa.UUID(), nullable=False),
    sa.Column('invited_by', sa.UUID(), nullable=False),
    sa.Column('invitee_email', sa.String(length=320), nullable=True),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('proposed_role', sa.Enum('OWNER', 'ADULT', 'MEMBER', name='family_role'), nullable=False),
    sa.Column('status', sa.Enum('PENDING', 'ACCEPTED', 'DECLINED', 'EXPIRED', 'CANCELLED', name='invitation_status'), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('accepted_by', sa.UUID(), nullable=True),
    sa.Column('accepted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['accepted_by'], ['users.id'], name=op.f('fk_family_invitations_accepted_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['family_id'], ['families.id'], name=op.f('fk_family_invitations_family_id_families'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['invited_by'], ['users.id'], name=op.f('fk_family_invitations_invited_by_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_family_invitations'))
    )
    op.create_index(op.f('ix_family_invitations_invitee_email'), 'family_invitations', ['invitee_email'], unique=False)
    op.create_index(op.f('ix_family_invitations_token_hash'), 'family_invitations', ['token_hash'], unique=True)
    op.create_index('ix_invitations_family_status', 'family_invitations', ['family_id', 'status'], unique=False)
    op.create_table('family_memberships',
    sa.Column('family_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('role', sa.Enum('OWNER', 'ADULT', 'MEMBER', name='family_role'), nullable=False),
    sa.Column('status', sa.Enum('ACTIVE', 'LEFT', 'REMOVED', name='membership_status'), nullable=False),
    sa.Column('joined_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('left_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['family_id'], ['families.id'], name=op.f('fk_family_memberships_family_id_families'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_family_memberships_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_family_memberships')),
    sa.UniqueConstraint('family_id', 'user_id', name='one_membership_per_family')
    )
    op.create_index('ix_family_memberships_family', 'family_memberships', ['family_id', 'status'], unique=False)
    op.create_index('uq_one_active_family_per_user', 'family_memberships', ['user_id'], unique=True, postgresql_where=sa.text("status = 'ACTIVE'"))


def downgrade() -> None:
    op.drop_index('uq_one_active_family_per_user', table_name='family_memberships', postgresql_where=sa.text("status = 'ACTIVE'"))
    op.drop_index('ix_family_memberships_family', table_name='family_memberships')
    op.drop_table('family_memberships')
    op.drop_index('ix_invitations_family_status', table_name='family_invitations')
    op.drop_index(op.f('ix_family_invitations_token_hash'), table_name='family_invitations')
    op.drop_index(op.f('ix_family_invitations_invitee_email'), table_name='family_invitations')
    op.drop_table('family_invitations')
    op.drop_table('families')

    # Enum types outlive their tables unless dropped explicitly, and a second
    # upgrade would then fail with "type already exists".
    for enum_name in (
        "family_status",
        "family_role",
        "membership_status",
        "invitation_status",
    ):
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
