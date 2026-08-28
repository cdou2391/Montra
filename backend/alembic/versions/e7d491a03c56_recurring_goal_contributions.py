"""A planned or recurring transfer can name the goal it is for.

Revision ID: e7d491a03c56
Revises: d5b83c2f719a
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "e7d491a03c56"
down_revision = "d5b83c2f719a"
branch_labels = None
depends_on = None

TABLES = ("recurring_rules", "planned_transactions")


def upgrade() -> None:
    for table in TABLES:
        op.add_column(
            table, sa.Column("goal_id", postgresql.UUID(as_uuid=True), nullable=True)
        )
        # SET NULL, so removing a goal never removes the schedule or the
        # occurrence: the money still moved, or is still going to.
        op.create_foreign_key(
            f"fk_{table}_goal_id", table, "goals", ["goal_id"], ["id"], ondelete="SET NULL"
        )
        op.create_index(f"ix_{table}_goal_id", table, ["goal_id"])


def downgrade() -> None:
    for table in TABLES:
        op.drop_index(f"ix_{table}_goal_id", table_name=table)
        op.drop_constraint(f"fk_{table}_goal_id", table, type_="foreignkey")
        op.drop_column(table, "goal_id")
