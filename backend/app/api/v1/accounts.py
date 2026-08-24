"""Account endpoints (API spec section 18)."""

import uuid

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session as DbSession

from app.api.deps import current_user, db_session, parse_uuid
from app.core.money import serialize
from app.core.responses import collection, single
from app.db.enums import AccountStatus, AccountType
from app.models.user import User
from app.schemas.accounts import AccountCreate, AccountUpdate, BalanceAdjustmentCreate
from app.services import accounts as account_service
from app.services.authz import get_editable_account, get_viewable_account
from app.services.posting import PostingService

router = APIRouter(tags=["accounts"], prefix="/accounts")


@router.get("")
def list_accounts(
    status_filter: AccountStatus | None = Query(default=None, alias="status"),
    type_filter: AccountType | None = Query(default=None, alias="type"),
    limit: int = Query(default=50, ge=1, le=100),
    db: DbSession = Depends(db_session),
    user: User = Depends(current_user),
) -> dict:
    accounts = account_service.list_accounts(
        db, user=user, status=status_filter, account_type=type_filter, limit=limit
    )
    db.commit()
    return collection(
        [account_service.serialize_account(db, a, user) for a in accounts], limit=limit
    )


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
        opening_balance_date=payload.opening_balance_date,
        ownership_type=payload.ownership_type,
        visibility=payload.visibility,
        institution_id=parse_uuid(payload.institution_id, "institution_id"),
        account_identifier=payload.account_identifier,
        description=payload.description,
        family_id=parse_uuid(payload.family_id, "family_id"),
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
    return single(account_service.serialize_account(db, account, user))


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
    )
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


@router.post("/{account_id}/balance-adjustments", status_code=status.HTTP_201_CREATED)
def create_balance_adjustment(
    account_id: uuid.UUID,
    payload: BalanceAdjustmentCreate,
    db: DbSession = Depends(db_session),
    user: User = Depends(current_user),
) -> dict:
    from app.services.authz import get_transactable_account
    from app.services.transactions import serialize_transaction

    account = get_transactable_account(db, account_id, user)
    txn = PostingService(db).adjust_balance(
        account=account,
        actual_balance=payload.actual_balance,
        adjustment_date=payload.adjustment_date,
        actor_id=user.id,
        reason=payload.reason,
    )
    db.commit()
    if txn is None:
        return single({"adjustment": None, "message": "Balance already matches; no adjustment."})
    db.refresh(txn)
    return single(serialize_transaction(txn, account))
