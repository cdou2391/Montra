"""Category management and the default category set (PRD sections 19.1-19.2)."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.db.enums import CategoryStatus, CategoryType
from app.models.finance import Category

DEFAULT_INCOME_CATEGORIES = [
    "Salary",
    "Bonus",
    "Business",
    "Investment income",
    "Interest",
    "Refund",
    "Gift",
    "Other",
]

DEFAULT_EXPENSE_CATEGORIES = [
    "Food",
    "Groceries",
    "Restaurants",
    "Housing",
    "Rent",
    "Mortgage",
    "Utilities",
    "Internet",
    "Transport",
    "Fuel",
    "Shopping",
    "Entertainment",
    "Education",
    "Healthcare",
    "Family",
    "Subscriptions",
    "Insurance",
    "Transaction Fees",
    "Travel",
    "Gifts",
    "Other",
]


# The category a fee is filed under, whatever the charge it was taken on was
# for. Part of the default set, so it exists for every user without asking.
# Named for the transaction rather than the institution: a mobile-money charge
# is a fee on a transaction, and nobody would file it under a bank.
FEE_CATEGORY_NAME = "Transaction Fees"


def fee_category_id(db: DbSession, *, user_id: uuid.UUID) -> uuid.UUID | None:
    """The user's fee category, if they still have it.

    Returns None rather than recreating it: a user who archived or renamed the
    category has said something about how they want their spending filed, and
    quietly resurrecting it would override that. An uncategorised fee is a
    smaller problem than a category that will not stay deleted.
    """
    return db.scalar(
        select(Category.id).where(
            Category.user_id == user_id,
            Category.name == FEE_CATEGORY_NAME,
            Category.category_type == CategoryType.EXPENSE,
            Category.status == CategoryStatus.ACTIVE,
        )
    )


def create_default_categories(db: DbSession, *, user_id: uuid.UUID) -> list[Category]:
    categories = [
        Category(user_id=user_id, name=name, category_type=CategoryType.INCOME, is_system=True)
        for name in DEFAULT_INCOME_CATEGORIES
    ] + [
        Category(user_id=user_id, name=name, category_type=CategoryType.EXPENSE, is_system=True)
        for name in DEFAULT_EXPENSE_CATEGORIES
    ]
    db.add_all(categories)
    return categories


def list_categories(
    db: DbSession,
    *,
    user_id: uuid.UUID,
    category_type: CategoryType | None = None,
    include_archived: bool = False,
) -> list[Category]:
    stmt = select(Category).where(Category.user_id == user_id)
    if category_type is not None:
        stmt = stmt.where(Category.category_type == category_type)
    if not include_archived:
        stmt = stmt.where(Category.status == CategoryStatus.ACTIVE)
    return list(db.scalars(stmt.order_by(Category.category_type, Category.name)))
