"""Rename the default fee category to Transaction Fees.

"Banking Fees" is wrong for a mobile-money charge, which is most of them
here. Existing users keep their data and get the new name.

Revision ID: e5b8d3c04a17
Revises: d4a9c2b71f38
"""

import sqlalchemy as sa
from alembic import op

revision = "e5b8d3c04a17"
down_revision = "d4a9c2b71f38"
branch_labels = None
depends_on = None

OLD = "Banking Fees"
NEW = "Transaction Fees"

# Only the shipped category is touched: a category the user created with that
# name is theirs, and renaming it would be us editing their filing. The NOT
# EXISTS guard covers the user who has already made their own "Transaction
# Fees", where a blind rename would collide with the (user, name, type)
# uniqueness constraint.
RENAME = """
UPDATE categories AS c
   SET name = :new
 WHERE c.name = :old
   AND c.is_system IS TRUE
   AND c.category_type = 'EXPENSE'
   AND NOT EXISTS (
       SELECT 1 FROM categories AS other
        WHERE other.user_id = c.user_id
          AND other.name = :new
          AND other.category_type = c.category_type
   )
"""


def _rename(old: str, new: str) -> None:
    op.get_bind().execute(sa.text(RENAME), {"old": old, "new": new})


def upgrade() -> None:
    _rename(OLD, NEW)


def downgrade() -> None:
    _rename(NEW, OLD)
