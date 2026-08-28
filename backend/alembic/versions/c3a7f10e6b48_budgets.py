"""Budgets: a spending ceiling per category, per period.

Revision ID: c3a7f10e6b48
Revises: a1c4e70d5b92
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "c3a7f10e6b48"
down_revision = "a1c4e70d5b92"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Created here, then referenced with create_type=False below. Without that
    # flag create_table issues its own CREATE TYPE and fails on the duplicate.
    postgresql.ENUM("ACTIVE", "ARCHIVED", name="budget_status").create(
        op.get_bind(), checkfirst=True
    )
    postgresql.ENUM("MONTHLY", name="budget_period").create(op.get_bind(), checkfirst=True)
    budget_status = postgresql.ENUM(name="budget_status", create_type=False)
    budget_period = postgresql.ENUM(name="budget_period", create_type=False)

    op.create_table(
        "budgets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "owner_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("family_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "category_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("categories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("amount", sa.Numeric(20, 4), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("period", budget_period, nullable=False, server_default="MONTHLY"),
        # Reuses the visibility type the accounts already use, so a budget is
        # scoped by the same three levels as everything else.
        sa.Column(
            "visibility",
            postgresql.ENUM(
                "PRIVATE", "FAMILY_VISIBLE", "SHARED", name="visibility", create_type=False
            ),
            nullable=False,
            server_default="PRIVATE",
        ),
        sa.Column("status", budget_status, nullable=False, server_default="ACTIVE"),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount > 0", name="budget_amount_positive"),
    )
    op.create_index("ix_budgets_owner_user_id", "budgets", ["owner_user_id"])
    op.create_index("ix_budgets_family_id", "budgets", ["family_id"])
    # Partial, so archiving a budget frees the category for a new one while the
    # old row stays as history.
    op.create_index(
        "uq_budget_active_category",
        "budgets",
        ["owner_user_id", "category_id"],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )


def downgrade() -> None:
    op.drop_table("budgets")
    # Dropped explicitly: dropping a table does not remove the types it used,
    # and leaving them behind makes the next upgrade fail on a duplicate.
    op.execute("DROP TYPE IF EXISTS budget_status")
    op.execute("DROP TYPE IF EXISTS budget_period")
