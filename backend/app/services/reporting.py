"""Dashboard and net worth (Implementation Plan Phases 22-23).

Two rules govern everything here.

*Private data is excluded before aggregation, not after.* Filtering a total
after the fact leaks the total. The account scope is narrowed first, and the
sums are computed from what survives.

*A shared account counts once.* Aggregating across memberships would count a
household account once per member (Data Model section 51), so scoping is done
by account, never by joining through membership rows.

Personal reporting deliberately does not attribute half a shared balance to
each member (section 49). It reports what you own, and shows the household's
shared position beside it.
"""

from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.core.money import serialize
from app.db.enums import (
    AccountNature,
    LoanDirection,
    LoanStatus,
    TransactionStatus,
    TransactionType,
    Visibility,
    nature_for,
)
from app.models.finance import Account, Transaction
from app.models.loans import Loan
from app.models.user import User
from app.services import authz
from app.services.loans import outstanding_principal
from app.services.posting import PostingService

ZERO = Decimal("0")


def _loans_in_scope(db: DbSession, access: authz.Access, context: str) -> list[Loan]:
    if context == "family":
        if not access.in_family:
            return []
        stmt = select(Loan).where(
            Loan.family_id == access.family_id,
            Loan.visibility.in_((Visibility.FAMILY_VISIBLE, Visibility.SHARED)),
            Loan.status != LoanStatus.ARCHIVED,
        )
    else:
        stmt = select(Loan).where(
            Loan.owner_user_id == access.user.id,
            Loan.visibility != Visibility.SHARED,
            Loan.status != LoanStatus.ARCHIVED,
        )
    return list(db.scalars(stmt))


def _shared_loans(db: DbSession, access: authz.Access) -> list[Loan]:
    if not access.in_family:
        return []
    return list(
        db.scalars(
            select(Loan).where(
                Loan.family_id == access.family_id,
                Loan.visibility == Visibility.SHARED,
                Loan.status != LoanStatus.ARCHIVED,
            )
        )
    )


def _position(db: DbSession, accounts: list[Account], loans: list[Loan]) -> dict:
    """Assets, liabilities and the difference, for one set of records."""
    posting = PostingService(db)
    assets = ZERO
    liabilities = ZERO

    for account in accounts:
        balance = posting.balance_of(account)
        if nature_for(account.account_type) is AccountNature.LIABILITY:
            liabilities += balance
        else:
            assets += balance

    for loan in loans:
        outstanding = outstanding_principal(db, loan)
        if loan.direction is LoanDirection.PAYABLE:
            liabilities += outstanding
        else:
            # Money owed to you is something you own.
            assets += outstanding

    return {
        "assets": serialize(assets),
        "liabilities": serialize(liabilities),
        "net_worth": serialize(assets - liabilities),
    }


def net_worth(db: DbSession, *, user: User, context: str = "personal") -> dict:
    """Implementation Plan Phase 23."""
    access = authz.resolve(db, user)

    if context == "family":
        accounts = list(db.scalars(authz.visible_accounts(db, access, context="family")))
        loans = _loans_in_scope(db, access, "family")
        payload = _position(db, accounts, loans)
        payload.update(
            context="family",
            currency=user.base_currency,
            account_count=len(accounts),
            loan_count=len(loans),
        )
        return payload

    # Personal: what you own, with shared shown beside it rather than split.
    owned = [
        a
        for a in db.scalars(authz.visible_accounts(db, access))
        if a.owner_user_id == user.id and a.visibility is not Visibility.SHARED
    ]
    payload = _position(db, owned, _loans_in_scope(db, access, "personal"))

    shared_accounts = [
        a
        for a in db.scalars(authz.visible_accounts(db, access))
        if a.visibility is Visibility.SHARED
    ]
    shared_loans = _shared_loans(db, access)
    payload.update(
        context="personal",
        currency=user.base_currency,
        account_count=len(owned),
        loan_count=len(_loans_in_scope(db, access, "personal")),
        # Presented separately: attributing half a household balance to each
        # member would be a guess dressed up as a number.
        shared=(
            {
                **_position(db, shared_accounts, shared_loans),
                "account_count": len(shared_accounts),
                "loan_count": len(shared_loans),
            }
            if shared_accounts or shared_loans
            else None
        ),
    )
    return payload


def _month_bounds(today: date) -> tuple[date, date]:
    start = today.replace(day=1)
    end = (
        start.replace(year=start.year + 1, month=1)
        if start.month == 12
        else start.replace(month=start.month + 1)
    )
    return start, end


def month_flows(
    db: DbSession, *, user: User, access: authz.Access, context: str, today: date
) -> dict:
    """Income and expense for the current month.

    Data Model section 52: transfers and adjustments are excluded. Moving your
    own money is neither earning nor spending, and counting it as either is the
    fastest way to make a dashboard lie.
    """
    from app.core.timezone import day_start

    account_ids = select(
        authz.visible_accounts(db, access, include_archived=True, context=context).subquery().c.id
    )
    start, end = _month_bounds(today)

    totals = {}
    for label, kind in (("income", TransactionType.INCOME), ("expense", TransactionType.EXPENSE)):
        rows = db.scalars(
            select(Transaction.amount).where(
                Transaction.account_id.in_(account_ids),
                Transaction.transaction_type == kind,
                Transaction.status == TransactionStatus.COMPLETED,
                Transaction.deleted_at.is_(None),
                Transaction.occurred_at >= day_start(start, user.timezone),
                Transaction.occurred_at < day_start(end, user.timezone),
            )
        ).all()
        totals[label] = sum(rows, ZERO)

    saved = totals["income"] - totals["expense"]
    rate = (
        (saved / totals["income"] * 100).quantize(Decimal("0.01")) if totals["income"] > 0 else None
    )
    return {
        "month": start.isoformat(),
        "income": serialize(totals["income"]),
        "expense": serialize(totals["expense"]),
        "saved": serialize(saved),
        "savings_rate": str(rate) if rate is not None else None,
    }


def dashboard(db: DbSession, *, user: User, context: str = "personal") -> dict:
    """Implementation Plan Phase 22."""
    from app.core.timezone import to_local
    from app.db.base import utcnow
    from app.services import loans as loan_service
    from app.services import planning as planning_service
    from app.services.transactions import list_transactions, serialize_transaction

    access = authz.resolve(db, user)
    today = to_local(utcnow(), user.timezone).date()

    if context == "family" and not access.in_family:
        # Asking for a household view without a household is not an error, it
        # is simply empty.
        return {
            "context": "family",
            "currency": user.base_currency,
            "in_family": False,
            "net_worth": None,
            "month": None,
            "upcoming": [],
            "recent": [],
        }

    upcoming = planning_service.list_planned(db, user=user, limit=5, context=context)
    recent, _ = list_transactions(db, user=user, limit=5, context=context)

    payload = {
        "context": context,
        "currency": user.base_currency,
        "in_family": access.in_family,
        "net_worth": net_worth(db, user=user, context=context),
        "month": month_flows(db, user=user, access=access, context=context, today=today),
        "upcoming": [
            planning_service.serialize_planned(p, timezone_name=user.timezone, today=today)
            for p in upcoming
        ],
        "recent": [serialize_transaction(t) for t in recent],
    }
    if context == "personal":
        payload["loans"] = loan_service.upcoming_payments(
            db, user=user, today=today, horizon_days=30
        )

    from app.services.insights import generate as generate_insights

    payload["insights"] = generate_insights(db, user=user, context=context)
    return payload


def spending_trend(
    db: DbSession,
    *,
    user: User,
    context: str = "personal",
    days: int = 30,
    today: date | None = None,
) -> dict:
    """Daily spending over a window, and how it compares with the one before.

    Expenses only. A transfer moves your own money and a loan principal
    repayment settles a debt you already carried — counting either as spending
    is the fastest way to make a chart lie, and the same rule the rest of the
    reporting follows.

    Every day in the window gets a row, including the ones with nothing on
    them. A chart drawn from only the days that had spending would space them
    evenly and quietly misrepresent when the money went.
    """
    from app.core.timezone import day_start, to_local
    from app.db.base import utcnow

    access = authz.resolve(db, user)
    today = today or to_local(utcnow(), user.timezone).date()

    account_ids = select(
        authz.visible_accounts(db, access, include_archived=True, context=context).subquery().c.id
    )

    # Inclusive of today, so a 30-day window is today plus the 29 before it.
    start = today - timedelta(days=days - 1)
    previous_start = start - timedelta(days=days)

    def _expenses(window_start: date, window_end: date) -> list[tuple[datetime, Decimal]]:
        return list(
            db.execute(
                select(Transaction.occurred_at, Transaction.amount).where(
                    Transaction.account_id.in_(account_ids),
                    Transaction.transaction_type == TransactionType.EXPENSE,
                    Transaction.status == TransactionStatus.COMPLETED,
                    Transaction.deleted_at.is_(None),
                    Transaction.occurred_at >= day_start(window_start, user.timezone),
                    Transaction.occurred_at < day_start(window_end, user.timezone),
                )
            ).all()
        )

    by_day: dict[date, Decimal] = {}
    for occurred_at, amount in _expenses(start, today + timedelta(days=1)):
        # Bucketed by the user's local day, so a late-night purchase lands on
        # the day they made it rather than the following UTC one.
        local_day = to_local(occurred_at, user.timezone).date()
        by_day[local_day] = by_day.get(local_day, ZERO) + Decimal(amount)

    points = []
    day = start
    while day <= today:
        points.append({"date": day.isoformat(), "amount": serialize(by_day.get(day, ZERO))})
        day += timedelta(days=1)

    total = sum(by_day.values(), ZERO)
    previous_total = sum(
        (Decimal(amount) for _, amount in _expenses(previous_start, start)), ZERO
    )

    # Averaged over the whole window rather than over the days that had
    # spending: "what does a day cost me" is the question, and the quiet days
    # are part of the answer.
    average = (total / days).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    change = None
    if previous_total > 0:
        change = ((total - previous_total) / previous_total * 100).quantize(Decimal("1"))

    busiest = max(by_day.items(), key=lambda pair: pair[1], default=None)

    return {
        "context": context,
        "currency": user.base_currency,
        "days": days,
        "starts_on": start.isoformat(),
        "ends_on": today.isoformat(),
        "total": serialize(total),
        "previous_total": serialize(previous_total),
        "change_percentage": str(change) if change is not None else None,
        "daily_average": serialize(average),
        "busiest_day": (
            {"date": busiest[0].isoformat(), "amount": serialize(busiest[1])}
            if busiest and busiest[1] > 0
            else None
        ),
        "points": points,
    }
