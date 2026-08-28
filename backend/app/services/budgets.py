"""Budgets: a ceiling on spending in one category, per period.

Nothing here posts, and a budget holds no money. Progress is derived from the
ledger on every read, the same rule the balances follow, so a budget can never
disagree with the transactions underneath it.

Three rules decide what counts, and each of them already applies elsewhere:

* Expenses only. Moving your own money is not spending, so transfers and
  adjustments are excluded — the same rule the month's totals use.
* Converted before it is compared. A dollar charge against a franc budget is
  converted first, because adding the raw numbers gives a wrong answer rather
  than an approximate one.
* An account kept out of the net-worth totals still spends. That flag is about
  the balance sheet; the money still left.

Each period stands alone: an unspent remainder does not carry into the next
month. Carrying it is a defensible choice too, but it has to be one or the
other, and a budget nobody can predict is a budget nobody reads.
"""

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from app.core.errors import Conflict, NotFound, ValidationFailed
from app.db.enums import (
    BudgetPeriod,
    BudgetStatus,
    CategoryStatus,
    CategoryType,
    TransactionStatus,
    TransactionType,
    Visibility,
)
from app.models.finance import Budget, Category, Transaction
from app.models.user import User
from app.services import authz, currency

ZERO = Decimal("0")

# How close to the limit counts as worth warning about. Under this a budget is
# just a number going up; over it, the month is at risk.
NEAR_LIMIT = Decimal("0.80")


def period_bounds(today: date) -> tuple[date, date]:
    """The calendar month `today` falls in, as a half-open range."""
    start = today.replace(day=1)
    end = (
        start.replace(year=start.year + 1, month=1)
        if start.month == 12
        else start.replace(month=start.month + 1)
    )
    return start, end


def _visible(db: DbSession, access: authz.Access, context: str):
    """Budgets the caller may see, scoped the way accounts are."""
    if context == "family":
        if not access.in_family:
            return select(Budget).where(False)
        return select(Budget).where(
            Budget.family_id == access.family_id,
            Budget.visibility.in_((Visibility.FAMILY_VISIBLE, Visibility.SHARED)),
            Budget.status == BudgetStatus.ACTIVE,
        )
    return select(Budget).where(
        Budget.owner_user_id == access.user.id,
        Budget.status == BudgetStatus.ACTIVE,
    )


def _spent_by_category(
    db: DbSession, *, user: User, account_ids, start: date, end: date, converter
) -> tuple[dict, set[str]]:
    """Completed spending per category in the window, in the base currency."""
    from app.core.timezone import day_start

    rows = db.execute(
        select(Transaction.category_id, Transaction.amount, Transaction.currency).where(
            Transaction.account_id.in_(account_ids),
            Transaction.transaction_type == TransactionType.EXPENSE,
            Transaction.status == TransactionStatus.COMPLETED,
            Transaction.deleted_at.is_(None),
            Transaction.category_id.is_not(None),
            Transaction.occurred_at >= day_start(start, user.timezone),
            Transaction.occurred_at < day_start(end, user.timezone),
        )
    ).all()

    totals: dict = {}
    unconverted: set[str] = set()
    for category_id, amount, code in rows:
        converted = converter.convert(Decimal(amount), code)
        if converted is None:
            unconverted.add(code.upper())
            continue
        totals[category_id] = totals.get(category_id, ZERO) + converted
    return totals, unconverted


def _state(spent: Decimal, limit: Decimal) -> str:
    if spent > limit:
        return "OVER"
    if limit > 0 and spent / limit >= NEAR_LIMIT:
        return "NEAR"
    return "UNDER"


def _projection(spent: Decimal, today: date, start: date, end: date) -> Decimal:
    """What this period ends at if the rest of it looks like the part so far.

    A budget that only reports after the fact is a receipt. This is the part
    that can say something while there is still time to act on it.
    """
    elapsed = (today - start).days + 1
    total_days = (end - start).days
    if elapsed <= 0 or elapsed >= total_days:
        return spent
    return (spent / elapsed * total_days).quantize(Decimal("0.01"))


def status(db: DbSession, *, user: User, context: str = "personal", today: date | None = None):
    """Every visible budget with what has been spent against it."""
    from app.core.money import serialize
    from app.core.timezone import to_local
    from app.db.base import utcnow

    access = authz.resolve(db, user)
    today = today or to_local(utcnow(), user.timezone).date()
    start, end = period_bounds(today)

    budgets = list(db.scalars(_visible(db, access, context)))
    if not budgets:
        return {
            "period_start": start.isoformat(),
            "period_end": end.isoformat(),
            "currency": user.base_currency,
            "budgets": [],
            "totals": None,
            "unconverted_currencies": [],
        }

    account_ids = select(
        authz.visible_accounts(db, access, include_archived=True, context=context).subquery().c.id
    )
    converter = currency.converter_for(db, user=user)
    spent_by_category, unconverted = _spent_by_category(
        db, user=user, account_ids=account_ids, start=start, end=end, converter=converter
    )

    rows = []
    total_limit = ZERO
    total_spent = ZERO
    for budget in budgets:
        limit = Decimal(budget.amount)
        spent = spent_by_category.get(budget.category_id, ZERO)
        total_limit += limit
        total_spent += spent
        rows.append(
            {
                "id": str(budget.id),
                "category": {
                    "id": str(budget.category_id),
                    "name": budget.category.name if budget.category else "Category",
                },
                "amount": serialize(limit),
                "spent": serialize(spent),
                # Negative once it is over, which is the number people want:
                # "how far past" rather than "zero left".
                "remaining": serialize(limit - spent),
                "used_percent": str(
                    (spent / limit * 100).quantize(Decimal("0.1")) if limit > 0 else Decimal("0")
                ),
                "projected": serialize(_projection(spent, today, start, end)),
                "state": _state(spent, limit),
                "currency": budget.currency,
                "visibility": budget.visibility.value,
                "period": budget.period.value,
            }
        )

    rows.sort(key=lambda r: (r["state"] != "OVER", r["state"] != "NEAR", r["category"]["name"]))
    return {
        "period_start": start.isoformat(),
        "period_end": end.isoformat(),
        "currency": user.base_currency,
        "budgets": rows,
        "totals": {
            "amount": serialize(total_limit),
            "spent": serialize(total_spent),
            "remaining": serialize(total_limit - total_spent),
        },
        # Named rather than silently dropped, as everywhere else a total is
        # built from more than one currency.
        "unconverted_currencies": sorted(unconverted),
    }


def serialize_budget(budget: Budget) -> dict:
    """The budget itself, without the derived spending.

    Used by the write endpoints, which have just changed the limit and have no
    reason to re-run the period's arithmetic to say so.
    """
    from app.core.money import serialize

    return {
        "id": str(budget.id),
        "category": {
            "id": str(budget.category_id),
            "name": budget.category.name if budget.category else "Category",
        },
        "amount": serialize(Decimal(budget.amount)),
        "currency": budget.currency,
        "period": budget.period.value,
        "visibility": budget.visibility.value,
        "status": budget.status.value,
    }


def _category_for(db: DbSession, *, user: User, category_id) -> Category:
    category = db.get(Category, category_id)
    if category is None or (category.user_id is not None and category.user_id != user.id):
        raise NotFound("Category not found.", code="CATEGORY_NOT_FOUND")
    if category.category_type is not CategoryType.EXPENSE:
        raise ValidationFailed(
            "Only a spending category can have a budget.",
            code="BUDGET_CATEGORY_NOT_EXPENSE",
        )
    if category.status is CategoryStatus.ARCHIVED:
        raise ValidationFailed("That category is archived.", code="CATEGORY_ARCHIVED")
    return category


def create_budget(
    db: DbSession,
    *,
    user: User,
    category_id,
    amount: Decimal,
    visibility: Visibility = Visibility.PRIVATE,
    period: BudgetPeriod = BudgetPeriod.MONTHLY,
) -> Budget:
    if amount <= 0:
        raise ValidationFailed(
            details=[{"field": "amount", "message": "A budget must be more than zero."}]
        )
    _category_for(db, user=user, category_id=category_id)

    existing = db.scalar(
        select(Budget).where(
            Budget.owner_user_id == user.id,
            Budget.category_id == category_id,
            Budget.status == BudgetStatus.ACTIVE,
        )
    )
    if existing is not None:
        raise Conflict(
            "That category already has a budget.",
            code="BUDGET_ALREADY_EXISTS",
        )

    from app.services.accounts import _resolve_sharing

    budget = Budget(
        owner_user_id=user.id,
        family_id=_resolve_sharing(db, user=user, visibility=visibility, family_id=None),
        category_id=category_id,
        amount=amount,
        currency=user.base_currency,
        period=period,
        visibility=visibility,
        created_by=user.id,
    )
    db.add(budget)
    db.flush()
    return budget


def get_budget(db: DbSession, budget_id, user: User) -> Budget:
    budget = db.get(Budget, budget_id)
    # 404 rather than 403, so the API never confirms someone else's exists.
    if budget is None or budget.owner_user_id != user.id:
        raise NotFound("Budget not found.", code="BUDGET_NOT_FOUND")
    return budget


def update_budget(
    db: DbSession,
    *,
    user: User,
    budget: Budget,
    amount: Decimal | None = None,
    visibility: Visibility | None = None,
) -> Budget:
    if amount is not None:
        if amount <= 0:
            raise ValidationFailed(
                details=[{"field": "amount", "message": "A budget must be more than zero."}]
            )
        budget.amount = amount
    if visibility is not None:
        from app.services.accounts import _resolve_sharing

        # Derived from the caller's own membership, never from the request, so
        # a client cannot share a budget into a household it is not in.
        budget.family_id = _resolve_sharing(
            db, user=user, visibility=visibility, family_id=budget.family_id
        )
        budget.visibility = visibility
    db.flush()
    return budget


def archive_budget(db: DbSession, budget: Budget) -> Budget:
    """Archived rather than deleted: what you used to aim for is history.

    It also frees the category, since the unique index only covers live rows.
    """
    if budget.status is BudgetStatus.ARCHIVED:
        raise Conflict("Budget is already archived.", code="BUDGET_ALREADY_ARCHIVED")
    budget.status = BudgetStatus.ARCHIVED
    db.flush()
    return budget


def count_active(db: DbSession, *, user: User) -> int:
    return db.scalar(
        select(func.count())
        .select_from(Budget)
        .where(Budget.owner_user_id == user.id, Budget.status == BudgetStatus.ACTIVE)
    )
