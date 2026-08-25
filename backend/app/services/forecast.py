"""Cash-flow forecast (Implementation Plan Phase 24).

Projects what is already known, and nothing more: today's balances plus the
planned items and loan instalments that have not happened yet. It does not
extrapolate from past spending — a forecast that invents transactions is a
guess wearing a number's clothes.

The rule that shapes the arithmetic (FSD section 112): a transfer between two
accounts that are both in scope is movement, not cash flow. It changes where
the money sits, so it matters to a single account's projection, and it must
cancel out of the household total. Counting it in both directions would make
every internal transfer look like income and expense at once.
"""

import uuid
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.core.money import serialize
from app.db.enums import (
    OPEN_PLANNED_STATUSES,
    AccountNature,
    LoanDirection,
    PlannedType,
    nature_for,
)
from app.models.planning import PlannedTransaction
from app.models.user import User
from app.services import authz
from app.services.posting import PostingService

ZERO = Decimal("0")
PERIODS = {"7d": 7, "30d": 30}


def _planned_in_window(
    db: DbSession,
    *,
    access: authz.Access,
    context: str,
    start: date,
    end: date,
    timezone_name: str,
) -> list[PlannedTransaction]:
    """Open planned items due in the window.

    Cancelled and completed items are excluded: one never happens, and the
    other is already in the balance we started from (FSD section 111).
    """
    from app.core.timezone import day_end, day_start

    account_ids = select(
        authz.visible_accounts(db, access, include_archived=True, context=context).subquery().c.id
    )
    return list(
        db.scalars(
            select(PlannedTransaction)
            .where(
                PlannedTransaction.account_id.in_(account_ids),
                PlannedTransaction.status.in_(tuple(OPEN_PLANNED_STATUSES)),
                PlannedTransaction.expected_at >= day_start(start, timezone_name),
                PlannedTransaction.expected_at < day_end(end, timezone_name),
            )
            .order_by(PlannedTransaction.expected_at)
        )
    )


def cash_flow(
    db: DbSession,
    *,
    user: User,
    context: str = "personal",
    period: str = "30d",
    account_id: uuid.UUID | None = None,
) -> dict:
    from app.core.timezone import to_local
    from app.db.base import utcnow
    from app.services import loans as loan_service

    days = PERIODS.get(period, 30)
    access = authz.resolve(db, user)
    today = to_local(utcnow(), user.timezone).date()
    end = today + timedelta(days=days)

    accounts = list(db.scalars(authz.visible_accounts(db, access, context=context)))
    if account_id is not None:
        accounts = [a for a in accounts if a.id == account_id]

    # Cash flow is about spendable money. A card's balance is debt, not cash;
    # paying it down appears as an outflow from the account that pays.
    cash_accounts = [a for a in accounts if nature_for(a.account_type) is AccountNature.ASSET]
    in_scope = {a.id for a in cash_accounts}

    posting = PostingService(db)
    balances = {a.id: posting.balance_of(a) for a in cash_accounts}
    starting = sum(balances.values(), ZERO)

    # (day, account_id or None) -> delta, plus the aggregate view.
    by_day: dict[date, Decimal] = defaultdict(lambda: ZERO)
    per_account: dict[date, dict[uuid.UUID, Decimal]] = defaultdict(
        lambda: defaultdict(lambda: ZERO)
    )
    income = ZERO
    expense = ZERO

    planned = (
        _planned_in_window(
            db,
            access=access,
            context=context,
            start=today,
            end=end,
            timezone_name=user.timezone,
        )
        if cash_accounts
        else []
    )

    for item in planned:
        day = to_local(item.expected_at, user.timezone).date()
        amount = Decimal(item.amount)
        source_in = item.account_id in in_scope
        destination_in = item.destination_account_id in in_scope

        if item.planned_type is PlannedType.TRANSFER:
            if source_in and destination_in:
                # Movement, not cash flow. It shifts money between two accounts
                # we are already counting, so the total is unchanged — but each
                # account's own projection still moves.
                per_account[day][item.account_id] -= amount
                per_account[day][item.destination_account_id] += amount
                continue
            if source_in:
                by_day[day] -= amount
                per_account[day][item.account_id] -= amount
                expense += amount
            elif destination_in:
                by_day[day] += amount
                per_account[day][item.destination_account_id] += amount
                income += amount
            continue

        if not source_in:
            # A planned item on a card: it does not move cash until it is paid.
            continue

        if item.planned_type is PlannedType.INCOME:
            by_day[day] += amount
            per_account[day][item.account_id] += amount
            income += amount
        else:
            by_day[day] -= amount
            per_account[day][item.account_id] -= amount
            expense += amount

    # Loan instalments are obligations too, but they name no account until they
    # are paid, so they move the total without a per-account warning.
    if context == "personal" and cash_accounts:
        for due in loan_service.upcoming_payments(db, user=user, today=today, horizon_days=days):
            day = date.fromisoformat(due["due_date"])
            if day < today or day > end:
                continue
            amount = Decimal(due["amount"])
            if due["direction"] == LoanDirection.PAYABLE.value:
                by_day[day] -= amount
                expense += amount
            else:
                by_day[day] += amount
                income += amount

    # Daily points, and the first day each account dips below zero.
    points = []
    running = starting
    account_running = dict(balances)
    warnings: list[dict] = []
    warned: set[uuid.UUID] = set()
    names = {a.id: a.name for a in cash_accounts}

    day = today
    while day <= end:
        running += by_day.get(day, ZERO)
        for aid, delta in per_account.get(day, {}).items():
            account_running[aid] = account_running.get(aid, ZERO) + delta
            if account_running[aid] < 0 and aid not in warned:
                warned.add(aid)
                warnings.append(
                    {
                        "account_id": str(aid),
                        "account_name": names.get(aid, "Account"),
                        "date": day.isoformat(),
                        "projected_balance": serialize(account_running[aid]),
                        "message": (
                            f"{names.get(aid, 'This account')} may fall below zero on "
                            # Read as prose, not as a machine timestamp; the
                            # machine-readable date is the field above.
                            f"{day.day} {day:%B}."
                        ),
                    }
                )
        points.append({"date": day.isoformat(), "projected_balance": serialize(running)})
        day += timedelta(days=1)

    return {
        "context": context,
        "period": period,
        "currency": user.base_currency,
        "starting_balance": serialize(starting),
        "projected_ending_balance": serialize(running),
        "upcoming_income": serialize(income),
        "upcoming_expenses": serialize(expense),
        "net_change": serialize(running - starting),
        "points": points,
        "warnings": warnings,
    }
