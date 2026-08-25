"""Loan domain service (Implementation Plan Phase 15).

A loan payment is not one financial event but up to three, and conflating them
is the mistake this module exists to prevent:

    principal  -> settles debt already carried, or returns money already lent.
                  Moves the loan balance. Never income or expense.
    interest    -> a real cost (PAYABLE) or a real earning (RECEIVABLE).
    fees        -> likewise.

Cash moves by the total; analytics move by interest and fees only.
"""

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from app.core.errors import Conflict, NotFound, ValidationFailed
from app.db.enums import (
    AccountNature,
    Frequency,
    LoanDirection,
    LoanStatus,
    OwnershipType,
    Visibility,
    nature_for,
)
from app.models.finance import Account
from app.models.loans import Loan, LoanPayment
from app.models.user import User
from app.services import audit
from app.services.authz import get_transactable_account
from app.services.posting import PostingService
from app.services.recurrence import occurrence_after

ZERO = Decimal("0")


# --------------------------------------------------------------------- access


def get_loan(db: DbSession, loan_id: uuid.UUID, user: User) -> Loan:
    """Fetch a loan the user may see.

    404 rather than 403 when they may not, so the API never confirms that
    someone else's private loan exists.
    """
    loan = db.get(Loan, loan_id)
    if loan is None or loan.owner_user_id != user.id:
        raise NotFound("Loan not found.", code="LOAN_NOT_FOUND")
    return loan


# --------------------------------------------------------------------- create


def create_loan(
    db: DbSession,
    *,
    user: User,
    name: str,
    direction: LoanDirection,
    currency: str,
    original_principal: Decimal,
    opening_outstanding_principal: Decimal,
    start_date: date,
    counterparty: str | None = None,
    interest_rate: Decimal | None = None,
    end_date: date | None = None,
    expected_payment_amount: Decimal | None = None,
    payment_frequency: Frequency | None = None,
    next_payment_date: date | None = None,
    visibility: Visibility = Visibility.PRIVATE,
    ownership_type: OwnershipType = OwnershipType.PERSONAL,
    family_id: uuid.UUID | None = None,
    notes: str | None = None,
) -> Loan:
    from app.services.accounts import _resolve_sharing

    family_id = _resolve_sharing(db, user=user, visibility=visibility, family_id=family_id)
    if original_principal < 0 or opening_outstanding_principal < 0:
        raise ValidationFailed(
            details=[{"field": "original_principal", "message": "Amounts cannot be negative."}]
        )
    if opening_outstanding_principal > original_principal:
        raise ValidationFailed(
            details=[
                {
                    "field": "opening_outstanding_principal",
                    "message": "Outstanding cannot exceed the original principal.",
                }
            ]
        )
    if end_date is not None and end_date < start_date:
        raise ValidationFailed(
            details=[{"field": "end_date", "message": "End date cannot precede the start date."}]
        )

    loan = Loan(
        owner_user_id=user.id,
        family_id=family_id,
        direction=direction,
        visibility=visibility,
        ownership_type=ownership_type,
        name=name.strip(),
        counterparty=counterparty,
        currency=currency.upper(),
        original_principal=original_principal,
        opening_outstanding_principal=opening_outstanding_principal,
        interest_rate=interest_rate,
        start_date=start_date,
        end_date=end_date,
        expected_payment_amount=expected_payment_amount,
        payment_frequency=payment_frequency,
        next_payment_date=next_payment_date,
        status=LoanStatus.ACTIVE,
        notes=notes,
        created_by=user.id,
    )
    db.add(loan)
    db.flush()
    return loan


# -------------------------------------------------------------------- balance


def principal_paid(db: DbSession, loan: Loan) -> Decimal:
    total = db.scalar(
        select(func.coalesce(func.sum(LoanPayment.principal_amount), 0)).where(
            LoanPayment.loan_id == loan.id
        )
    )
    return Decimal(total or 0)


def outstanding_principal(db: DbSession, loan: Loan) -> Decimal:
    """Data Model section 33: derived, never an overwritten column."""
    return Decimal(loan.opening_outstanding_principal) - principal_paid(db, loan)


def net_worth_contribution(db: DbSession, loan: Loan) -> Decimal:
    """Signed contribution: a receivable is an asset, a payable is a debt."""
    outstanding = outstanding_principal(db, loan)
    if loan.direction is LoanDirection.PAYABLE:
        return -outstanding
    return outstanding


# -------------------------------------------------------------------- payment


def record_payment(
    db: DbSession,
    *,
    user: User,
    loan: Loan,
    account_id: uuid.UUID,
    total_amount: Decimal,
    principal_amount: Decimal,
    interest_amount: Decimal = ZERO,
    fee_amount: Decimal = ZERO,
    payment_date: date,
    occurred_at: datetime,
    notes: str | None = None,
    idempotency_key: str | None = None,
) -> LoanPayment:
    """Record a payment and post its parts to the ledger.

    Caller owns the surrounding database transaction.
    """
    if loan.status is LoanStatus.ARCHIVED:
        raise Conflict("This loan is archived.", code="LOAN_ARCHIVED")

    for label, value in (
        ("total_amount", total_amount),
        ("principal_amount", principal_amount),
        ("interest_amount", interest_amount),
        ("fee_amount", fee_amount),
    ):
        if value < 0:
            raise ValidationFailed(
                details=[{"field": label, "message": "Amount cannot be negative."}]
            )
    if total_amount <= 0:
        raise ValidationFailed(
            details=[{"field": "total_amount", "message": "Amount must be greater than zero."}]
        )

    # The allocation must account for every unit of the payment, or the ledger
    # and the loan balance disagree by the difference.
    if principal_amount + interest_amount + fee_amount != total_amount:
        raise ValidationFailed(
            "Principal, interest and fees must add up to the total.",
            code="ALLOCATION_MISMATCH",
            details=[
                {
                    "field": "principal_amount",
                    "message": (
                        f"{principal_amount} + {interest_amount} + {fee_amount} "
                        f"does not equal {total_amount}."
                    ),
                }
            ],
        )

    remaining = outstanding_principal(db, loan)
    if principal_amount > remaining:
        raise ValidationFailed(
            "That is more principal than the loan has left.",
            code="PRINCIPAL_EXCEEDS_OUTSTANDING",
            details=[
                {
                    "field": "principal_amount",
                    "message": f"At most {remaining} of principal remains.",
                }
            ],
        )

    account = get_transactable_account(db, account_id, user)
    if nature_for(account.account_type) is not AccountNature.ASSET:
        raise ValidationFailed(
            "Loan payments must use an asset account.",
            code="INVALID_PAYMENT_ACCOUNT",
            details=[
                {"field": "account_id", "message": "Choose a bank, cash or mobile money account."}
            ],
        )
    if account.currency.upper() != loan.currency.upper():
        raise ValidationFailed(
            details=[
                {
                    "field": "account_id",
                    "message": f"Account currency must match the loan ({loan.currency}).",
                }
            ]
        )

    payment = LoanPayment(
        loan_id=loan.id,
        account_id=account.id,
        payment_date=payment_date,
        total_amount=total_amount,
        principal_amount=principal_amount,
        interest_amount=interest_amount,
        fee_amount=fee_amount,
        notes=notes,
        idempotency_key=idempotency_key,
        created_by=user.id,
    )
    db.add(payment)
    db.flush()

    posting = PostingService(db)
    payable = loan.direction is LoanDirection.PAYABLE
    shared = {
        "occurred_at": occurred_at,
        "actor_id": user.id,
        "loan_payment_id": payment.id,
    }

    if principal_amount > 0:
        posting.record_loan_principal(
            account=account,
            amount=principal_amount,
            outgoing=payable,
            description=f"{loan.name} — principal",
            **shared,
        )

    # Interest and fees are the parts that are genuinely earned or spent.
    for label, amount in (("interest", interest_amount), ("fees", fee_amount)):
        if amount <= 0:
            continue
        record = posting.record_expense if payable else posting.record_income
        record(
            account=account,
            amount=amount,
            currency=account.currency,
            description=f"{loan.name} — {label}",
            **shared,
        )

    if outstanding_principal(db, loan) == 0 and loan.status is LoanStatus.ACTIVE:
        loan.status = LoanStatus.SETTLED
    else:
        # Move the schedule on, or the loan stays permanently due on the same
        # date and the upcoming list never changes.
        advance_schedule(db, loan, paid_on=payment_date)

    db.flush()
    audit.record(
        db,
        actor=user,
        event_type=audit.LOAN_PAYMENT_RECORDED,
        entity_type=audit.LOAN,
        entity_id=loan.id,
        # No amounts: the payment row holds those, behind the loan's own
        # permissions.
        metadata={"payment_id": str(payment.id), "account_id": str(account.id)},
    )
    return payment


def advance_schedule(db: DbSession, loan: Loan, *, paid_on: date) -> date | None:
    """Move next_payment_date on by exactly one instalment.

    One payment settles one scheduled instalment, whether it arrives early or
    late. Advancing past the payment date instead would silently forgive missed
    instalments on a late payment, and paying a few days early would leave the
    loan still showing as due.
    """
    if loan.payment_frequency is None or loan.next_payment_date is None:
        return loan.next_payment_date

    nxt = occurrence_after(
        previous=loan.next_payment_date,
        frequency=loan.payment_frequency,
        interval=1,
        anchor=loan.next_payment_date,
    )
    if loan.end_date is not None and nxt > loan.end_date:
        loan.next_payment_date = None
    else:
        loan.next_payment_date = nxt
    db.flush()
    return loan.next_payment_date


def upcoming_payments(
    db: DbSession,
    *,
    user: User,
    today: date,
    horizon_days: int = 90,
) -> list[dict]:
    """Loan payments falling due, shaped like the planning screen's entries.

    Derived rather than materialised: a loan already carries its own schedule,
    so generating PlannedTransaction rows from it would mean two places to keep
    in step and a way for them to disagree.
    """
    from app.core.money import serialize
    from app.services.planning import bucket_for_day

    horizon = today + timedelta(days=horizon_days)
    entries: list[dict] = []

    for loan in list_loans(db, user=user, status=LoanStatus.ACTIVE):
        if loan.next_payment_date is None or loan.expected_payment_amount is None:
            continue

        # Only occurrences up to the horizon, so a weekly loan does not flood
        # the list with a year of rows.
        due = loan.next_payment_date
        guard = 0
        while due <= horizon:
            outstanding = outstanding_principal(db, loan)
            amount = min(Decimal(loan.expected_payment_amount), outstanding)
            entries.append(
                {
                    "id": f"loan:{loan.id}:{due.isoformat()}",
                    "kind": "LOAN_PAYMENT",
                    "loan_id": str(loan.id),
                    "direction": loan.direction.value,
                    "description": loan.name,
                    "counterparty": loan.counterparty,
                    "amount": serialize(amount),
                    "currency": loan.currency,
                    "due_date": due.isoformat(),
                    "bucket": bucket_for_day(due, today=today),
                    "outstanding_principal": serialize(outstanding),
                }
            )
            if loan.payment_frequency is None:
                break  # A one-off payment date, not a series.
            guard += 1
            if guard > 200:
                break
            due = occurrence_after(
                previous=due,
                frequency=loan.payment_frequency,
                interval=1,
                anchor=loan.next_payment_date,
            )

    entries.sort(key=lambda e: e["due_date"])
    return entries


# --------------------------------------------------------------------- listing


def list_loans(
    db: DbSession,
    *,
    user: User,
    direction: LoanDirection | None = None,
    status: LoanStatus | None = None,
    include_archived: bool = False,
) -> list[Loan]:
    stmt = select(Loan).where(Loan.owner_user_id == user.id)
    if direction is not None:
        stmt = stmt.where(Loan.direction == direction)
    if status is not None:
        stmt = stmt.where(Loan.status == status)
    elif not include_archived:
        stmt = stmt.where(Loan.status != LoanStatus.ARCHIVED)
    return list(db.scalars(stmt.order_by(Loan.status, Loan.name)))


def archive_loan(db: DbSession, loan: Loan) -> Loan:
    if loan.status is LoanStatus.ARCHIVED:
        raise Conflict("Loan is already archived.", code="LOAN_ALREADY_ARCHIVED")
    loan.status = LoanStatus.ARCHIVED
    db.flush()
    return loan


# ----------------------------------------------------------------- serializing


def serialize_loan(db: DbSession, loan: Loan) -> dict:
    from app.core.money import serialize, serialize_rate

    outstanding = outstanding_principal(db, loan)
    original = Decimal(loan.original_principal)
    # Progress is measured against the original principal, so a loan taken on
    # part-way through its life still shows what has actually been cleared.
    paid = original - outstanding
    percent = (paid / original * 100).quantize(Decimal("0.01")) if original > 0 else None

    return {
        "id": str(loan.id),
        "name": loan.name,
        "direction": loan.direction.value,
        "counterparty": loan.counterparty,
        "currency": loan.currency,
        "original_principal": serialize(original),
        "opening_outstanding_principal": serialize(Decimal(loan.opening_outstanding_principal)),
        "outstanding_principal": serialize(outstanding),
        "principal_paid": serialize(paid),
        "percent_paid": str(percent) if percent is not None else None,
        "interest_rate": (
            serialize_rate(loan.interest_rate) if loan.interest_rate is not None else None
        ),
        "start_date": loan.start_date.isoformat(),
        "end_date": loan.end_date.isoformat() if loan.end_date else None,
        "expected_payment_amount": (
            serialize(Decimal(loan.expected_payment_amount))
            if loan.expected_payment_amount is not None
            else None
        ),
        "payment_frequency": loan.payment_frequency.value if loan.payment_frequency else None,
        "next_payment_date": (
            loan.next_payment_date.isoformat() if loan.next_payment_date else None
        ),
        "status": loan.status.value,
        "visibility": loan.visibility.value,
        "notes": loan.notes,
    }


def serialize_payment(payment: LoanPayment, account: Account | None = None) -> dict:
    from app.core.money import serialize

    return {
        "id": str(payment.id),
        "loan_id": str(payment.loan_id),
        "account": {"id": str(account.id), "name": account.name} if account else None,
        "payment_date": payment.payment_date.isoformat(),
        "total_amount": serialize(Decimal(payment.total_amount)),
        "principal_amount": serialize(Decimal(payment.principal_amount)),
        "interest_amount": serialize(Decimal(payment.interest_amount)),
        "fee_amount": serialize(Decimal(payment.fee_amount)),
        "notes": payment.notes,
        "created_at": payment.created_at.isoformat(),
    }
