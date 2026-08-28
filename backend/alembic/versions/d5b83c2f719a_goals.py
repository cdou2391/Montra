"""Goals, and the tag that links a transfer to one.

Revision ID: d5b83c2f719a
Revises: c3a7f10e6b48
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "d5b83c2f719a"
down_revision = "c3a7f10e6b48"
branch_labels = None
depends_on = None


def upgrade() -> None:
    postgresql.ENUM("ACTIVE", "ACHIEVED", "ARCHIVED", name="goal_status").create(
        op.get_bind(), checkfirst=True
    )
    goal_status = postgresql.ENUM(name="goal_status", create_type=False)

    op.create_table(
        "goals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "owner_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("family_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("accounts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("target_amount", sa.Numeric(20, 4), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("target_date", sa.Date(), nullable=True),
        sa.Column(
            "visibility",
            postgresql.ENUM(
                "PRIVATE", "FAMILY_VISIBLE", "SHARED", name="visibility", create_type=False
            ),
            nullable=False,
            server_default="PRIVATE",
        ),
        sa.Column("status", goal_status, nullable=False, server_default="ACTIVE"),
        sa.Column("achieved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("target_amount > 0", name="goal_target_positive"),
    )
    op.create_index("ix_goals_owner_user_id", "goals", ["owner_user_id"])
    op.create_index("ix_goals_family_id", "goals", ["family_id"])

    # A contribution is a real transfer; this only says which goal it was for.
    # SET NULL on delete, so removing a goal never removes the movement.
    op.add_column(
        "transfers", sa.Column("goal_id", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.create_foreign_key(
        "fk_transfers_goal_id", "transfers", "goals", ["goal_id"], ["id"], ondelete="SET NULL"
    )
    op.create_index("ix_transfers_goal_id", "transfers", ["goal_id"])

    # Autogenerate does not notice new members of an existing enum, and
    # ALTER TYPE ... ADD VALUE cannot run inside a transaction on older
    # servers, so these are issued with autocommit.
    with op.get_context().autocommit_block():
        for value in ("GOAL_ACHIEVED", "GOAL_SHORTFALL"):
            op.execute(f"ALTER TYPE notification_type ADD VALUE IF NOT EXISTS '{value}'")
        op.execute("ALTER TYPE reminder_entity ADD VALUE IF NOT EXISTS 'GOAL'")


def downgrade() -> None:
    op.drop_index("ix_transfers_goal_id", table_name="transfers")
    op.drop_constraint("fk_transfers_goal_id", "transfers", type_="foreignkey")
    op.drop_column("transfers", "goal_id")
    op.drop_table("goals")
    op.execute("DROP TYPE IF EXISTS goal_status")
    # Postgres cannot remove a value from an enum type. The notification and
    # reminder members stay behind, which is harmless: nothing reads them once
    # the goals are gone.
