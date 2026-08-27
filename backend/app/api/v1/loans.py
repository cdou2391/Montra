"""Loan endpoints."""

import uuid
from datetime import datetime, time

from fastapi import APIRouter, Depends, Header, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.api.deps import current_user, db_session, parse_uuid
from app.core.errors import Conflict
from app.core.responses import collection, single
from app.core.timezone import ensure_aware
from app.db.enums import LoanDirection, LoanStatus
from app.models.finance import Account
from app.models.loans import LoanPayment
from app.models.user import User
from app.schemas.loans import LoanCreate, LoanPaymentCreate, LoanUpdate
from app.services import loans as loan_service

router = APIRouter(tags=["loans"], prefix="/loans")


@router.get("")
def list_loans(
    direction: LoanDirection | None = None,
    status_filter: LoanStatus | None = Query(default=None, alias="status"),
    include_archived: bool = False,
    db: DbSession = Depends(db_session),
    user: User = Depends(current_user),
) -> dict:
    rows = loan_service.list_loans(
        db,
        user=user,
        direction=direction,
        status=status_filter,
        include_archived=include_archived,
    )
    payload = [loan_service.serialize_loan(db, loan) for loan in rows]
    db.commit()
    return collection(payload, limit=len(payload))


@router.post("", status_code=status.HTTP_201_CREATED)
def create_loan(
    payload: LoanCreate,
    db: DbSession = Depends(db_session),
    user: User = Depends(current_user),
) -> dict:
    loan = loan_service.create_loan(
        db,
        user=user,
        name=payload.name,
        direction=payload.direction,
        currency=payload.currency,
        original_principal=payload.original_principal,
        opening_outstanding_principal=payload.opening_outstanding_principal,
        start_date=payload.start_date,
        counterparty=payload.counterparty,
        interest_rate=payload.interest_rate,
        end_date=payload.end_date,
        expected_payment_amount=payload.expected_payment_amount,
        payment_frequency=payload.payment_frequency,
        next_payment_date=payload.next_payment_date,
        visibility=payload.visibility,
        ownership_type=payload.ownership_type,
        family_id=parse_uuid(payload.family_id, "family_id"),
        notes=payload.notes,
    )
    db.commit()
    db.refresh(loan)
    return single(loan_service.serialize_loan(db, loan))


@router.get("/upcoming")
def upcoming_loan_payments(
    horizon_days: int = Query(default=90, ge=1, le=365),
    db: DbSession = Depends(db_session),
    user: User = Depends(current_user),
) -> dict:
    """Loan payments falling due, for the planning screens.

    Declared before /{loan_id} so "upcoming" is not read as a loan id.
    """
    from app.core.timezone import to_local
    from app.db.base import utcnow

    today = to_local(utcnow(), user.timezone).date()
    payload = loan_service.upcoming_payments(db, user=user, today=today, horizon_days=horizon_days)
    db.commit()
    return collection(payload, limit=len(payload))


@router.get("/{loan_id}")
def get_loan(
    loan_id: uuid.UUID,
    db: DbSession = Depends(db_session),
    user: User = Depends(current_user),
) -> dict:
    loan = loan_service.get_loan(db, loan_id, user)
    payload = loan_service.serialize_loan(db, loan)
    db.commit()
    return single(payload)


@router.patch("/{loan_id}")
def update_loan(
    loan_id: uuid.UUID,
    payload: LoanUpdate,
    db: DbSession = Depends(db_session),
    user: User = Depends(current_user),
) -> dict:
    loan = loan_service.get_loan(db, loan_id, user)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(loan, field, value)
    db.commit()
    db.refresh(loan)
    return single(loan_service.serialize_loan(db, loan))


@router.post("/{loan_id}/archive")
def archive_loan(
    loan_id: uuid.UUID,
    db: DbSession = Depends(db_session),
    user: User = Depends(current_user),
) -> dict:
    loan = loan_service.get_loan(db, loan_id, user)
    loan_service.archive_loan(db, loan)
    db.commit()
    db.refresh(loan)
    return single(loan_service.serialize_loan(db, loan))


@router.get("/{loan_id}/payments")
def list_payments(
    loan_id: uuid.UUID,
    db: DbSession = Depends(db_session),
    user: User = Depends(current_user),
) -> dict:
    loan = loan_service.get_loan(db, loan_id, user)
    rows = list(
        db.scalars(
            select(LoanPayment)
            .where(LoanPayment.loan_id == loan.id)
            .order_by(LoanPayment.payment_date.desc(), LoanPayment.created_at.desc())
        )
    )
    accounts = {
        a.id: a for a in db.scalars(select(Account).where(Account.owner_user_id == user.id))
    }
    payload = [loan_service.serialize_payment(p, accounts.get(p.account_id)) for p in rows]
    db.commit()
    return collection(payload, limit=len(payload))


@router.post("/{loan_id}/payments", status_code=status.HTTP_201_CREATED)
def create_payment(
    loan_id: uuid.UUID,
    payload: LoanPaymentCreate,
    db: DbSession = Depends(db_session),
    user: User = Depends(current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    loan = loan_service.get_loan(db, loan_id, user)

    # A replayed key returns the original payment rather than posting again.
    if idempotency_key:
        existing = db.scalar(
            select(LoanPayment).where(
                LoanPayment.created_by == user.id,
                LoanPayment.idempotency_key == idempotency_key,
            )
        )
        if existing is not None:
            if existing.loan_id != loan.id:
                raise Conflict(
                    "That idempotency key was used for a different loan.",
                    code="IDEMPOTENCY_CONFLICT",
                )
            account = db.get(Account, existing.account_id)
            db.commit()
            return single(loan_service.serialize_payment(existing, account))

    # Payments carry a date; the ledger wants an instant. Midday local avoids
    # a midnight stamp landing on the previous day for anyone west of UTC.
    occurred_at = (
        ensure_aware(payload.occurred_at, user.timezone)
        if payload.occurred_at is not None
        else ensure_aware(datetime.combine(payload.payment_date, time(12, 0)), user.timezone)
    )

    payment = loan_service.record_payment(
        db,
        user=user,
        loan=loan,
        account_id=parse_uuid(payload.account_id, "account_id"),
        total_amount=payload.total_amount,
        principal_amount=payload.principal_amount,
        interest_amount=payload.interest_amount,
        fee_amount=payload.fee_amount,
        payment_date=payload.payment_date,
        occurred_at=occurred_at,
        notes=payload.notes,
        idempotency_key=idempotency_key,
    )
    db.commit()
    db.refresh(payment)
    account = db.get(Account, payment.account_id)
    return single(
        {
            **loan_service.serialize_payment(payment, account),
            "loan": loan_service.serialize_loan(db, loan),
        }
    )
