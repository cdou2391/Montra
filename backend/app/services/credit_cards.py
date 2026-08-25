"""Credit-card behaviour layered over the account and posting models.

Implementation Plan Phase 9. Nothing here computes a balance or a ledger
direction of its own: outstanding balance comes from PostingService, and a card
payment is a transfer, so it goes through transfer_funds like any other.

The three properties the plan asks to guard:

    Purchase  = Expense + increased liability
    Payment   = reduced cash + reduced liability
    Payment  != Expense
"""

import calendar
from datetime import UTC, date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.orm import Session as DbSession

from app.core.errors import Conflict, ValidationFailed
from app.db.enums import AccountNature, AccountStatus, AccountType, nature_for
from app.models.finance import Account, Transfer
from app.models.user import User
from app.services.posting import PostingService

# Utilization bands from UI/UX section 36. Returned by the API so the client
# does not re-derive thresholds and drift from them.
UTILIZATION_BANDS = ((30, "NORMAL"), (60, "NEUTRAL"), (80, "WARNING"))


# Both kinds of plastic carry an expiry date. Everything else in this module is
# credit-specific, but an expiry belongs to the card, not to how it is funded.
CARD_ACCOUNT_TYPES = (AccountType.CREDIT_CARD, AccountType.PREPAID_CARD)


def _expiry_advice(account: Account, *, expired: bool) -> str:
    prepaid = account.account_type is AccountType.PREPAID_CARD
    if expired:
        if prepaid:
            return "Any balance left on it may no longer be reachable."
        return "Recurring charges on this card will be failing."
    if prepaid:
        return "Spend or move the balance before then."
    return "Order a replacement and move any recurring charges across."


def require_card(account: Account) -> Account:
    if account.account_type not in CARD_ACCOUNT_TYPES:
        raise ValidationFailed(
            "This account is not a card.",
            code="NOT_A_CARD",
            details=[{"field": "account_id", "message": "Expected a card account."}],
        )
    return account


# How much warning is useful before a card stops working: long enough to order
# a replacement and move recurring charges across, short enough that the notice
# still feels current.
EXPIRY_NOTICE_DAYS = 60


def expiry_date(account: Account) -> date | None:
    """The last day the card works.

    A card printed 08/28 is good for the whole of August 2028, so expiry falls
    at the end of that month rather than on its first day.
    """
    if account.expiry_month is None or account.expiry_year is None:
        return None
    last_day = calendar.monthrange(account.expiry_year, account.expiry_month)[1]
    return date(account.expiry_year, account.expiry_month, last_day)


def expiry_state(account: Account, *, today: date | None = None) -> dict | None:
    """Expiry as the UI needs it, so the client never derives month-ends."""
    expires_on = expiry_date(account)
    if expires_on is None:
        return None
    today = today or datetime.now().date()
    days_remaining = (expires_on - today).days
    if days_remaining < 0:
        status = "EXPIRED"
    elif days_remaining <= EXPIRY_NOTICE_DAYS:
        status = "EXPIRING"
    else:
        status = "VALID"
    return {
        "expires_on": expires_on.isoformat(),
        "days_remaining": days_remaining,
        "status": status,
        # What to do about it depends on what the card holds: a credit card
        # carries charges to move, a prepaid card carries money to lose. The
        # rule lives here so the notification and the screen cannot drift.
        "advice": _expiry_advice(account, expired=status == "EXPIRED"),
    }


def require_credit_card(account: Account) -> Account:
    if account.account_type is not AccountType.CREDIT_CARD:
        raise ValidationFailed(
            "This account is not a credit card.",
            code="NOT_A_CREDIT_CARD",
            details=[{"field": "account_id", "message": "Expected a CREDIT_CARD account."}],
        )
    return account


def utilization_band(percentage: Decimal | None) -> str | None:
    if percentage is None:
        return None
    for ceiling, name in UTILIZATION_BANDS:
        if percentage <= ceiling:
            return name
    return "HIGH"


def next_occurrence(day_of_month: int, *, today: date) -> date:
    """Next calendar date falling on that day of the month.

    Clamped to the length of the target month, so a card due on the 31st still
    resolves in February rather than raising.
    """

    def clamp(year: int, month: int) -> date:
        return date(year, month, min(day_of_month, calendar.monthrange(year, month)[1]))

    candidate = clamp(today.year, today.month)
    if candidate >= today:
        return candidate
    year, month = (today.year + 1, 1) if today.month == 12 else (today.year, today.month + 1)
    return clamp(year, month)


def summary(db: DbSession, account: Account, *, today: date | None = None) -> dict:
    """Card position: what is owed, what is left, and what falls due."""
    require_credit_card(account)
    today = today or datetime.now().date()

    posting = PostingService(db)
    outstanding = posting.balance_of(account)

    limit = Decimal(account.credit_limit) if account.credit_limit is not None else None
    available: Decimal | None = None
    utilization: Decimal | None = None

    if limit is not None:
        # Available credit can legitimately go negative when a card is over its
        # limit. Reporting the real number beats clamping to zero and hiding it.
        available = limit - outstanding
        if limit > 0:
            utilization = (outstanding / limit * 100).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )

    due_date = (
        next_occurrence(account.payment_due_day, today=today)
        if account.payment_due_day is not None
        else None
    )

    from app.core.money import serialize, serialize_rate

    return {
        "account_id": str(account.id),
        "currency": account.currency,
        "outstanding_balance": serialize(outstanding),
        "available_credit": serialize(available) if available is not None else None,
        "credit_limit": serialize(limit) if limit is not None else None,
        "utilization_percentage": str(utilization) if utilization is not None else None,
        "utilization_band": utilization_band(utilization),
        "statement_balance": (
            serialize(Decimal(account.statement_balance))
            if account.statement_balance is not None
            else None
        ),
        "minimum_payment": (
            serialize(Decimal(account.minimum_payment))
            if account.minimum_payment is not None
            else None
        ),
        "payment_due_date": due_date.isoformat() if due_date else None,
        "statement_closing_day": account.statement_closing_day,
        "interest_rate": (
            serialize_rate(account.interest_rate) if account.interest_rate is not None else None
        ),
        "expiry_month": account.expiry_month,
        "expiry_year": account.expiry_year,
        "expiry": expiry_state(account, today=today),
    }


def pay_card(
    db: DbSession,
    *,
    user: User,
    card: Account,
    source: Account,
    amount: Decimal,
    occurred_at: datetime,
    idempotency_key: str | None = None,
) -> Transfer:
    """Pay down a card from another account.

    A convenience wrapper over the posting engine, not a second code path. The
    engine resolves both sides from account nature, which is what keeps a
    payment out of expense analytics: both entries are TRANSFER, and both are
    DECREASE — the asset loses value and the liability loses debt.
    """
    require_credit_card(card)

    if nature_for(source.account_type) is not AccountNature.ASSET:
        raise ValidationFailed(
            "A card payment must come from an asset account.",
            code="INVALID_PAYMENT_SOURCE",
            details=[
                {
                    "field": "source_account_id",
                    "message": "Choose a bank, cash or mobile money account.",
                }
            ],
        )
    if source.status is not AccountStatus.ACTIVE or card.status is not AccountStatus.ACTIVE:
        raise Conflict("Archived accounts cannot be used.", code="ACCOUNT_ARCHIVED")

    return PostingService(db).transfer_funds(
        source=source,
        destination=card,
        source_amount=amount,
        destination_amount=amount,
        occurred_at=occurred_at,
        actor_id=user.id,
        notes=f"Payment to {card.name}",
        idempotency_key=idempotency_key,
    )


def top_up_prepaid(
    db: DbSession,
    *,
    user: User,
    card: Account,
    source: Account,
    amount: Decimal,
    occurred_at: datetime,
    idempotency_key: str | None = None,
) -> Transfer:
    """Load funds onto a prepaid card.

    Prepaid cards are assets, so a top-up is an ordinary asset-to-asset move:
    money changes location, net worth does not change, and no expense is
    recorded (Implementation Plan Phase 10).
    """
    if card.account_type is not AccountType.PREPAID_CARD:
        raise ValidationFailed(
            "This account is not a prepaid card.",
            code="NOT_A_PREPAID_CARD",
            details=[{"field": "account_id", "message": "Expected a PREPAID_CARD account."}],
        )

    return PostingService(db).transfer_funds(
        source=source,
        destination=card,
        source_amount=amount,
        destination_amount=amount,
        occurred_at=occurred_at,
        actor_id=user.id,
        notes=f"Top-up to {card.name}",
        idempotency_key=idempotency_key,
    )


def card_fields_payload(account: Account) -> dict | None:
    """Card metadata for account serialization, omitted for non-cards."""
    if account.account_type is not AccountType.CREDIT_CARD:
        return None
    from app.core.money import serialize, serialize_rate

    return {
        "credit_limit": (
            serialize(Decimal(account.credit_limit)) if account.credit_limit is not None else None
        ),
        "statement_balance": (
            serialize(Decimal(account.statement_balance))
            if account.statement_balance is not None
            else None
        ),
        "statement_closing_day": account.statement_closing_day,
        "payment_due_day": account.payment_due_day,
        "minimum_payment": (
            serialize(Decimal(account.minimum_payment))
            if account.minimum_payment is not None
            else None
        ),
        "interest_rate": (
            serialize_rate(account.interest_rate) if account.interest_rate is not None else None
        ),
        "expiry_month": account.expiry_month,
        "expiry_year": account.expiry_year,
    }


# An expiry date applies to any card; the rest describes a line of credit.
EXPIRY_FIELDS = frozenset({"expiry_month", "expiry_year"})


def apply_card_fields(account: Account, values: dict) -> None:
    """Set card metadata, rejecting it on accounts it cannot describe."""
    if not values:
        return
    named = {k for k, v in values.items() if v is not None}
    if named - EXPIRY_FIELDS:
        require_credit_card(account)
    elif named:
        require_card(account)
    # None is applied rather than skipped: clearing an expiry recorded by
    # mistake is a real edit, and callers only send the keys they mean.
    for field, value in values.items():
        setattr(account, field, value)


def expiring_cards(
    db: DbSession, *, today: date | None = None, within_days: int = EXPIRY_NOTICE_DAYS
) -> list[tuple[Account, dict]]:
    """Every active card at or past its notice window, oldest expiry first.

    Archived cards are skipped: an account you have already put away does not
    need chasing about a card you have presumably already replaced.
    """
    from sqlalchemy import select

    today = today or datetime.now().date()
    cards = db.scalars(
        select(Account).where(
            Account.account_type.in_(CARD_ACCOUNT_TYPES),
            Account.status == AccountStatus.ACTIVE,
            Account.expiry_month.is_not(None),
            Account.expiry_year.is_not(None),
        )
    ).all()

    found = []
    for card in cards:
        state = expiry_state(card, today=today)
        if state is None:
            continue
        if state["days_remaining"] <= within_days:
            found.append((card, state))
    found.sort(key=lambda pair: pair[1]["expires_on"])
    return found


def notify_expiring_cards(
    db: DbSession, *, today: date | None = None, within_days: int = EXPIRY_NOTICE_DAYS
) -> int:
    """Raise one notification per card, per expiry.

    The task runs daily, so it must not send daily. The guard is the notice
    window itself: a card is announced once after its window opens, and only
    announced again if the expiry date moves — which is exactly what happens
    when the card is replaced and the new date recorded.
    """
    from sqlalchemy import select

    from app.db.enums import NotificationType, ReminderEntity
    from app.models.planning import Notification
    from app.services.planning import notify

    today = today or datetime.now().date()
    sent = 0

    for card, state in expiring_cards(db, today=today, within_days=within_days):
        recipient = card.owner_user_id or card.created_by
        expires_on = date.fromisoformat(state["expires_on"])
        window_opened = datetime.combine(
            expires_on - timedelta(days=within_days), time.min, tzinfo=UTC
        )
        already = db.scalar(
            select(Notification.id).where(
                Notification.user_id == recipient,
                Notification.notification_type == NotificationType.CARD_EXPIRING,
                Notification.related_entity_id == card.id,
                Notification.created_at >= window_opened,
            )
        )
        if already is not None:
            continue

        days = state["days_remaining"]
        if days < 0:
            title = f"{card.name} has expired"
            body = f"It expired on {expires_on.day} {expires_on:%B %Y}."
        elif days == 0:
            title = f"{card.name} expires today"
            body = "Today is the last day it will work."
        else:
            title = f"{card.name} expires in {days} day{'s' if days != 1 else ''}"
            body = (
                f"It stops working after {expires_on.day} {expires_on:%B %Y}. "
                + _expiry_advice(card, expired=False)
            )

        notify(
            db,
            user_id=recipient,
            notification_type=NotificationType.CARD_EXPIRING,
            title=title,
            body=body,
            entity_type=ReminderEntity.CREDIT_CARD,
            entity_id=card.id,
        )
        sent += 1

    return sent
