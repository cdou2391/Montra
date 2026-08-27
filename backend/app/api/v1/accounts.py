"""Account endpoints (API spec section 18)."""

import uuid

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session as DbSession

from app.api.deps import current_user, db_session, parse_uuid
from app.core.money import serialize
from app.core.responses import collection, single
from app.core.timezone import ensure_aware
from app.db.enums import AccountStatus, AccountType
from app.models.user import User
from app.schemas.accounts import (
    AccountCreate,
    AccountUpdate,
    BalanceAdjustmentCreate,
    VisibilityUpdate,
)
from app.services import accounts as account_service
from app.services import currency
from app.services.authz import get_editable_account, get_viewable_account
from app.services.posting import PostingService

router = APIRouter(tags=["accounts"], prefix="/accounts")

CARD_FIELD_NAMES = (
    "credit_limit",
    "statement_balance",
    "statement_closing_day",
    "payment_due_day",
    "minimum_payment",
    "interest_rate",
    "expiry_month",
    "expiry_year",
)


def _card_fields(payload) -> dict:
    """Card metadata the caller actually supplied, so an omitted field is left
    alone rather than being nulled out."""
    supplied = payload.model_dump(exclude_unset=True)
    return {name: supplied[name] for name in CARD_FIELD_NAMES if name in supplied}


@router.get("")
def list_accounts(
    status_filter: AccountStatus | None = Query(default=None, alias="status"),
    type_filter: AccountType | None = Query(default=None, alias="type"),
    limit: int = Query(default=50, ge=1, le=100),
    context: str = Query(default="personal", pattern="^(personal|family)$"),
    db: DbSession = Depends(db_session),
    user: User = Depends(current_user),
) -> dict:
    accounts = account_service.list_accounts(
        db,
        user=user,
        status=status_filter,
        account_type=type_filter,
        limit=limit,
        context=context,
    )
    favorite = account_service.favorite_account_id(db, user)
    # One converter for the list: one lookup, and every row at the same rate.
    converter = currency.converter_for(db, user=user)
    payload = [
        account_service.serialize_account(db, a, user, favorite=favorite, converter=converter)
        for a in accounts
    ]
    db.commit()
    return collection(payload, limit=limit)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_account(
    payload: AccountCreate,
    db: DbSession = Depends(db_session),
    user: User = Depends(current_user),
) -> dict:
    account = account_service.create_account(
        db,
        user=user,
        name=payload.name,
        account_type=payload.account_type,
        currency=payload.currency,
        opening_balance=payload.opening_balance,
        opening_balance_at=ensure_aware(payload.opening_balance_at, user.timezone),
        ownership_type=payload.ownership_type,
        visibility=payload.visibility,
        institution_id=parse_uuid(payload.institution_id, "institution_id"),
        account_identifier=payload.account_identifier,
        description=payload.description,
        family_id=parse_uuid(payload.family_id, "family_id"),
        excluded_from_totals=payload.excluded_from_totals,
        card_fields=_card_fields(payload),
    )
    db.commit()
    db.refresh(account)
    return single(account_service.serialize_account(db, account, user))


@router.get("/{account_id}")
def get_account(
    account_id: uuid.UUID,
    db: DbSession = Depends(db_session),
    user: User = Depends(current_user),
) -> dict:
    account = get_viewable_account(db, account_id, user)
    db.commit()
    return single(
        account_service.serialize_account(db, account, user, include_activity=True)
    )


@router.patch("/{account_id}")
def update_account(
    account_id: uuid.UUID,
    payload: AccountUpdate,
    db: DbSession = Depends(db_session),
    user: User = Depends(current_user),
) -> dict:
    account = get_editable_account(db, account_id, user)
    account_service.update_account(
        db,
        account=account,
        name=payload.name,
        description=payload.description,
        institution_id=parse_uuid(payload.institution_id, "institution_id"),
        account_identifier=payload.account_identifier,
        currency=payload.currency,
        excluded_from_totals=payload.excluded_from_totals,
        card_fields=_card_fields(payload),
    )
    db.commit()
    db.refresh(account)
    return single(account_service.serialize_account(db, account, user))


@router.patch("/{account_id}/visibility")
def change_visibility(
    account_id: uuid.UUID,
    payload: VisibilityUpdate,
    db: DbSession = Depends(db_session),
    user: User = Depends(current_user),
) -> dict:
    """Share an account with the household, or take it back.

    Child records inherit account visibility, so this decides what the
    household sees of its history too.
    """
    account = get_editable_account(db, account_id, user)
    account_service.set_visibility(db, account=account, user=user, visibility=payload.visibility)
    db.commit()
    db.refresh(account)
    return single(account_service.serialize_account(db, account, user))


@router.post("/{account_id}/archive", status_code=status.HTTP_204_NO_CONTENT)
def archive_account(
    account_id: uuid.UUID,
    db: DbSession = Depends(db_session),
    user: User = Depends(current_user),
) -> Response:
    account = get_editable_account(db, account_id, user)
    account_service.archive_account(db, account)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{account_id}/restore")
def restore_account(
    account_id: uuid.UUID,
    db: DbSession = Depends(db_session),
    user: User = Depends(current_user),
) -> dict:
    account = get_editable_account(db, account_id, user)
    account_service.restore_account(db, account)
    db.commit()
    db.refresh(account)
    return single(account_service.serialize_account(db, account, user))


@router.post("/{account_id}/favorite")
def set_favorite(
    account_id: uuid.UUID,
    db: DbSession = Depends(db_session),
    user: User = Depends(current_user),
) -> dict:
    """Make this the account that leads every list."""
    account = get_viewable_account(db, account_id, user)
    account_service.set_favorite_account(db, user=user, account_id=account.id)
    db.commit()
    db.refresh(account)
    return single(account_service.serialize_account(db, account, user))


@router.delete("/{account_id}/favorite")
def clear_favorite(
    account_id: uuid.UUID,
    db: DbSession = Depends(db_session),
    user: User = Depends(current_user),
) -> dict:
    account = get_viewable_account(db, account_id, user)
    # Only if it is still the favourite, so a stale request cannot unset a
    # newer choice.
    if account_service.favorite_account_id(db, user) == account.id:
        account_service.set_favorite_account(db, user=user, account_id=None)
    db.commit()
    db.refresh(account)
    return single(account_service.serialize_account(db, account, user))


@router.get("/{account_id}/balance")
def account_balance(
    account_id: uuid.UUID,
    db: DbSession = Depends(db_session),
    user: User = Depends(current_user),
) -> dict:
    account = get_viewable_account(db, account_id, user)
    balance = PostingService(db).balance_of(account)
    db.commit()
    return single({"amount": serialize(balance), "currency": account.currency})


@router.post("/{account_id}/balance-adjustments")
def create_balance_adjustment(
    account_id: uuid.UUID,
    payload: BalanceAdjustmentCreate,
    response: Response,
    db: DbSession = Depends(db_session),
    user: User = Depends(current_user),
) -> dict:
    """Reconcile an account to an observed balance.

    The difference is recorded as its own financial event; history is never
    rewritten and the opening balance is never edited.
    """
    from app.services.authz import get_transactable_account
    from app.services.transactions import serialize_transaction

    account = get_transactable_account(db, account_id, user)
    txn = PostingService(db).adjust_balance(
        account=account,
        actual_balance=payload.actual_balance,
        occurred_at=ensure_aware(payload.occurred_at, user.timezone),
        actor_id=user.id,
        reason=payload.reason,
    )
    db.commit()

    if txn is None:
        # Nothing was created, so this is not a 201.
        response.status_code = status.HTTP_200_OK
        return single({"adjustment": None, "message": "Balance already matches; no adjustment."})

    db.refresh(txn)
    response.status_code = status.HTTP_201_CREATED
    return single(serialize_transaction(txn, account))


@router.get("/{account_id}/reconciliation-preview")
def reconciliation_preview(
    account_id: uuid.UUID,
    actual_balance: str,
    db: DbSession = Depends(db_session),
    user: User = Depends(current_user),
) -> dict:
    """What an adjustment would do, without doing it."""
    from app.core.money import to_decimal

    account = get_viewable_account(db, account_id, user)
    current = PostingService(db).balance_of(account)
    target = to_decimal(actual_balance, "actual_balance")
    delta = target - current
    db.commit()
    return single(
        {
            "current_balance": serialize(current),
            "actual_balance": serialize(target),
            "difference": serialize(abs(delta)),
            "direction": "INCREASE" if delta > 0 else "DECREASE" if delta < 0 else None,
            "currency": account.currency,
        }
    )
