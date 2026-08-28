"""Deterministic insights.

Arithmetic over the caller's authorized scope — no model, so each insight can
be checked by hand. Two rules:

*Only say something when there is something to say.* One that fires every month
is furniture, so each has a threshold and returns nothing below it.

*Never see more than the viewer does.* Scope comes from the same authorization
as everywhere else, so a household insight cannot leak a private account.
"""

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from app.core.money import format_money, serialize
from app.db.enums import (
    AccountType,
    Frequency,
    LoanDirection,
    LoanStatus,
    PlannedType,
    RecurringStatus,
    TransactionStatus,
    TransactionType,
)
from app.models.finance import Category, Transaction
from app.models.planning import RecurringRule
from app.models.user import User
from app.services import authz
from app.services.posting import PostingService

ZERO = Decimal("0")

# Below these, an insight is noise rather than news.
SPENDING_SHIFT_THRESHOLD = Decimal("15")
UTILIZATION_THRESHOLD = Decimal("50")

# Monthly equivalent of each cadence, for totalling subscriptions.
PER_MONTH = {
    Frequency.DAILY: Decimal("30"),
    Frequency.WEEKLY: Decimal("4.33"),
    Frequency.MONTHLY: Decimal("1"),
    Frequency.QUARTERLY: Decimal("0.3333"),
    Frequency.YEARLY: Decimal("0.0833"),
}


def _month_range(today: date, back: int = 0) -> tuple[date, date]:
    month = today.month - back
    year = today.year
    while month <= 0:
        month += 12
        year -= 1
    start = date(year, month, 1)
    end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return start, end


def _spend_by_category(
    db: DbSession, *, user: User, account_ids, start: date, end: date
) -> dict[str, Decimal]:
    from app.core.timezone import day_start

    rows = db.execute(
        select(
            func.coalesce(Category.name, "Uncategorised"),
            func.sum(Transaction.amount),
        )
        .select_from(Transaction)
        .outerjoin(Category, Category.id == Transaction.category_id)
        .where(
            Transaction.account_id.in_(account_ids),
            Transaction.transaction_type == TransactionType.EXPENSE,
            Transaction.status == TransactionStatus.COMPLETED,
            Transaction.deleted_at.is_(None),
            Transaction.occurred_at >= day_start(start, user.timezone),
            Transaction.occurred_at < day_start(end, user.timezone),
        )
        .group_by(Category.name)
    ).all()
    return {name: Decimal(total or 0) for name, total in rows}


def _insight(code: str, title: str, detail: str, tone: str = "neutral", **extra) -> dict:
    return {"code": code, "title": title, "detail": detail, "tone": tone, **extra}


def generate(db: DbSession, *, user: User, context: str = "personal") -> list[dict]:
    """Everything worth saying about this scope, most useful first."""
    from app.core.timezone import to_local
    from app.db.base import utcnow
    from app.services import credit_cards, reporting
    from app.services.forecast import cash_flow

    access = authz.resolve(db, user)
    today = to_local(utcnow(), user.timezone).date()
    currency = user.base_currency
    insights: list[dict] = []

    accounts = list(db.scalars(authz.visible_accounts(db, access, context=context)))
    if not accounts:
        return insights

    account_ids = [a.id for a in accounts]

    # --- spending shift, this month against last -------------------------
    this_start, this_end = _month_range(today)
    last_start, last_end = _month_range(today, back=1)
    now_spend = _spend_by_category(
        db, user=user, account_ids=account_ids, start=this_start, end=this_end
    )
    then_spend = _spend_by_category(
        db, user=user, account_ids=account_ids, start=last_start, end=last_end
    )

    biggest = None
    for name, amount in now_spend.items():
        previous = then_spend.get(name, ZERO)
        if previous <= 0:
            continue
        change = (amount - previous) / previous * 100
        if abs(change) < SPENDING_SHIFT_THRESHOLD:
            continue
        if biggest is None or abs(change) > abs(biggest[1]):
            biggest = (name, change, amount, previous)

    if biggest:
        name, change, amount, previous = biggest
        direction = "more" if change > 0 else "less"
        insights.append(
            _insight(
                "spending_shift",
                f"{name} spending is {abs(change).quantize(Decimal('1'))}% {direction}",
                f"{format_money(amount, currency)} this month against "
                f"{format_money(previous, currency)} last month.",
                tone="warning" if change > 0 else "positive",
                category=name,
                change_percent=str(change.quantize(Decimal("0.1"))),
                currency=currency,
            )
        )

    # --- savings rate -----------------------------------------------------
    flows = reporting.month_flows(db, user=user, access=access, context=context, today=today)
    if flows["savings_rate"] is not None:
        rate = Decimal(flows["savings_rate"])
        insights.append(
            _insight(
                "savings_rate",
                f"You are saving {rate.quantize(Decimal('1'))}% of income",
                f"{format_money(Decimal(flows['income']), currency)} in, "
                f"{format_money(Decimal(flows['expense']), currency)} out this month.",
                tone="positive" if rate >= 10 else "warning",
                value=flows["savings_rate"],
                currency=currency,
            )
        )

    # --- recurring commitments -------------------------------------------
    #
    # What leaves every month whether or not you do anything. A loan instalment
    # is exactly that, and it does not appear as a recurring rule: instalments
    # come from each loan's own schedule, which is why the upcoming screen has
    # to merge two sources. Counting only the rules left the two largest fixed
    # payments out of a figure whose whole claim is "before anything else".
    #
    # Receivables stay out: money owed to you is not a payment you make.
    from app.services import currency as currency_service
    from app.services.reporting import _loans_in_scope

    converter = currency_service.converter_for(db, user=user)

    def _monthly(amount, frequency, interval, code) -> Decimal | None:
        """One cadence's worth, per month, in the base currency."""
        if amount is None or frequency is None:
            return None
        each = Decimal(amount) * PER_MONTH.get(frequency, Decimal("1")) / (interval or 1)
        # Converted, not added raw: a dollar subscription is not one franc.
        return converter.convert(each, code)

    rules = list(
        db.scalars(
            select(RecurringRule).where(
                RecurringRule.account_id.in_(account_ids),
                RecurringRule.status == RecurringStatus.ACTIVE,
                RecurringRule.planned_type == PlannedType.EXPENSE,
            )
        )
    )
    commitments = [
        value
        for r in rules
        if (value := _monthly(r.amount, r.frequency, r.interval_value, r.currency)) is not None
    ]

    instalments = [
        value
        for loan in _loans_in_scope(db, access, context)
        if loan.direction is LoanDirection.PAYABLE
        and loan.status is LoanStatus.ACTIVE
        and (
            value := _monthly(
                loan.expected_payment_amount, loan.payment_frequency, 1, loan.currency
            )
        )
        is not None
    ]

    if commitments or instalments:
        monthly = sum(commitments, ZERO) + sum(instalments, ZERO)
        count = len(commitments) + len(instalments)
        detail = f"About {format_money(monthly, currency)} a month before anything else."
        if instalments:
            # Named, because a loan instalment is not something most people
            # think of as a subscription, and the number jumps without it.
            detail += (
                f" Includes {len(instalments)} loan "
                f"{'instalments' if len(instalments) != 1 else 'instalment'}."
            )
        insights.append(
            _insight(
                "recurring_total",
                f"{count} recurring payment{'s' if count != 1 else ''}",
                detail,
                value=serialize(monthly),
                count=count,
                currency=currency,
            )
        )

    # --- credit utilization ----------------------------------------------
    posting = PostingService(db)
    for account in accounts:
        if account.account_type is not AccountType.CREDIT_CARD or not account.credit_limit:
            continue
        limit = Decimal(account.credit_limit)
        if limit <= 0:
            continue
        used = posting.balance_of(account) / limit * 100
        if used < UTILIZATION_THRESHOLD:
            continue
        insights.append(
            _insight(
                "credit_utilization",
                f"{account.name} is {used.quantize(Decimal('1'))}% used",
                f"{format_money(posting.balance_of(account), currency)} of "
                f"{format_money(limit, currency)}.",
                tone="warning" if used < 80 else "negative",
                account_id=str(account.id),
                value=str(used.quantize(Decimal("0.1"))),
                currency=currency,
            )
        )

    # --- cards approaching their expiry ----------------------------------
    for account in accounts:
        if account.account_type not in credit_cards.CARD_ACCOUNT_TYPES:
            continue
        state = credit_cards.expiry_state(account, today=today)
        if state is None or state["status"] == "VALID":
            continue
        days = state["days_remaining"]
        if days < 0:
            title = f"{account.name} has expired"
        elif days == 0:
            title = f"{account.name} expires today"
        else:
            title = f"{account.name} expires in {days} day{'s' if days != 1 else ''}"
        detail = state["advice"]
        insights.append(
            _insight(
                "card_expiring",
                title,
                detail,
                tone="negative" if days < 0 else "warning",
                account_id=str(account.id),
                currency=currency,
            )
        )

    # --- what is coming, and whether it fits -----------------------------
    forecast = cash_flow(db, user=user, context=context, period="30d")
    if Decimal(forecast["upcoming_expenses"]) > 0:
        due = format_money(Decimal(forecast["upcoming_expenses"]), currency)
        left = format_money(Decimal(forecast["projected_ending_balance"]), currency)
        insights.append(
            _insight(
                "upcoming_commitments",
                f"{due} due in the next 30 days",
                f"Leaving about {left} if nothing else changes.",
                value=forecast["upcoming_expenses"],
                currency=currency,
            )
        )
    for warning in forecast["warnings"]:
        insights.append(
            _insight(
                "projected_shortfall",
                warning["message"],
                f"Projected {format_money(Decimal(warning['projected_balance']), currency)} "
                "on that date.",
                tone="negative",
                account_id=warning["account_id"],
                currency=currency,
            )
        )

    # Problems first: a shortfall matters more than a savings rate.
    order = {"negative": 0, "warning": 1, "neutral": 2, "positive": 3}
    insights.sort(key=lambda i: order.get(i["tone"], 2))
    return insights
