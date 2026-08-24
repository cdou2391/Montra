"""Credit-card and prepaid-card endpoints (API spec sections 36-37).

Both are convenience layers over Account and the posting engine, not separate
financial machinery.
"""

import uuid

from fastapi import APIRouter, Depends, Header, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.api.deps import current_user, db_session, parse_uuid
from app.core.responses import single
from app.core.timezone import ensure_aware, to_local
from app.db.base import utcnow
from app.models.finance import Transfer
from app.models.user import User
from app.schemas.accounts import CreditCardPayment, PrepaidTopUp
from app.services import credit_cards as card_service
from app.services.authz import get_transactable_account, get_viewable_account

router = APIRouter(tags=["cards"])


def _replay(db: DbSession, user: User, key: str | None) -> Transfer | None:
    if not key:
        return None
    return db.scalar(
        select(Transfer).where(Transfer.created_by == user.id, Transfer.idempotency_key == key)
    )


def _transfer_payload(db: DbSession, transfer: Transfer) -> dict:
    from decimal import Decimal

    from app.core.money import serialize
    from app.models.finance import Account

    src = db.get(Account, transfer.source_account_id)
    dst = db.get(Account, transfer.destination_account_id)
    return {
        "id": str(transfer.id),
        "source_account": {"id": str(src.id), "name": src.name},
        "destination_account": {"id": str(dst.id), "name": dst.name},
        "amount": serialize(Decimal(transfer.source_amount)),
        "currency": transfer.source_currency,
        "occurred_at": transfer.occurred_at.isoformat(),
        "status": transfer.status.value,
    }


@router.get("/credit-cards/{account_id}/summary")
def credit_card_summary(
    account_id: uuid.UUID,
    db: DbSession = Depends(db_session),
    user: User = Depends(current_user),
) -> dict:
    account = get_viewable_account(db, account_id, user)
    # "Today" is the user's today, so a due date does not flip a day early or
    # late for anyone away from UTC.
    today = to_local(utcnow(), user.timezone).date()
    payload = card_service.summary(db, account, today=today)
    db.commit()
    return single(payload)


@router.post("/credit-cards/{account_id}/payments", status_code=status.HTTP_201_CREATED)
def pay_credit_card(
    account_id: uuid.UUID,
    payload: CreditCardPayment,
    db: DbSession = Depends(db_session),
    user: User = Depends(current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    existing = _replay(db, user, idempotency_key)
    if existing is not None:
        db.commit()
        return single(_transfer_payload(db, existing))

    card = get_transactable_account(db, account_id, user)
    source = get_transactable_account(
        db, parse_uuid(payload.source_account_id, "source_account_id"), user
    )
    transfer = card_service.pay_card(
        db,
        user=user,
        card=card,
        source=source,
        amount=payload.amount,
        occurred_at=ensure_aware(payload.occurred_at, user.timezone),
        idempotency_key=idempotency_key,
    )
    db.commit()
    db.refresh(transfer)
    return single(_transfer_payload(db, transfer))


@router.post("/prepaid-cards/{account_id}/top-ups", status_code=status.HTTP_201_CREATED)
def top_up_prepaid_card(
    account_id: uuid.UUID,
    payload: PrepaidTopUp,
    db: DbSession = Depends(db_session),
    user: User = Depends(current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    existing = _replay(db, user, idempotency_key)
    if existing is not None:
        db.commit()
        return single(_transfer_payload(db, existing))

    card = get_transactable_account(db, account_id, user)
    source = get_transactable_account(
        db, parse_uuid(payload.source_account_id, "source_account_id"), user
    )
    transfer = card_service.top_up_prepaid(
        db,
        user=user,
        card=card,
        source=source,
        amount=payload.amount,
        occurred_at=ensure_aware(payload.occurred_at, user.timezone),
        idempotency_key=idempotency_key,
    )
    db.commit()
    db.refresh(transfer)
    return single(_transfer_payload(db, transfer))
