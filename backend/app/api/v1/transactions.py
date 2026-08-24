"""Transaction, transfer and category endpoints (API spec sections 19-21)."""

import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Header, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.api.deps import current_user, db_session, parse_uuid
from app.core.errors import Conflict, NotFound
from app.core.money import serialize, to_decimal
from app.core.responses import collection, single
from app.db.enums import CategoryType, TransactionStatus, TransactionType
from app.models.finance import Category, Transfer
from app.models.user import User
from app.schemas.transactions import (
    CategoryCreate,
    TransactionCreate,
    TransactionUpdate,
    TransferCreate,
)
from app.services import categories as category_service
from app.services import transactions as txn_service
from app.services.authz import get_transactable_account, get_viewable_account
from app.services.posting import PostingService

router = APIRouter(tags=["transactions"])


# ------------------------------------------------------------------ transactions


@router.get("/transactions")
def list_transactions(
    account_id: str | None = None,
    category_id: str | None = None,
    type: TransactionType | None = None,  # noqa: A002
    status_filter: TransactionStatus | None = Query(default=None, alias="status"),
    date_from: date | None = None,
    date_to: date | None = None,
    min_amount: str | None = None,
    max_amount: str | None = None,
    search: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = None,
    db: DbSession = Depends(db_session),
    user: User = Depends(current_user),
) -> dict:
    rows, next_cursor = txn_service.list_transactions(
        db,
        user=user,
        account_id=parse_uuid(account_id, "account_id"),
        category_id=parse_uuid(category_id, "category_id"),
        transaction_type=type,
        status=status_filter,
        date_from=date_from,
        date_to=date_to,
        min_amount=to_decimal(min_amount, "min_amount") if min_amount else None,
        max_amount=to_decimal(max_amount, "max_amount") if max_amount else None,
        search=search,
        limit=limit,
        cursor=cursor,
    )
    db.commit()
    return collection(
        [txn_service.serialize_transaction(t) for t in rows], limit=limit, next_cursor=next_cursor
    )


@router.post("/transactions", status_code=status.HTTP_201_CREATED)
def create_transaction(
    payload: TransactionCreate,
    db: DbSession = Depends(db_session),
    user: User = Depends(current_user),
) -> dict:
    txn = txn_service.create_transaction(
        db,
        user=user,
        account_id=parse_uuid(payload.account_id, "account_id"),
        transaction_type=payload.transaction_type,
        amount=payload.amount,
        transaction_date=payload.transaction_date,
        category_id=parse_uuid(payload.category_id, "category_id"),
        description=payload.description,
        merchant=payload.merchant,
        notes=payload.notes,
        reference=payload.reference,
    )
    db.commit()
    db.refresh(txn)
    return single(txn_service.serialize_transaction(txn))


@router.get("/transactions/{transaction_id}")
def get_transaction(
    transaction_id: uuid.UUID,
    db: DbSession = Depends(db_session),
    user: User = Depends(current_user),
) -> dict:
    txn = txn_service.get_transaction(db, transaction_id, user)
    db.commit()
    return single(txn_service.serialize_transaction(txn))


@router.patch("/transactions/{transaction_id}")
def update_transaction(
    transaction_id: uuid.UUID,
    payload: TransactionUpdate,
    db: DbSession = Depends(db_session),
    user: User = Depends(current_user),
) -> dict:
    txn = txn_service.update_transaction(
        db,
        user=user,
        transaction_id=transaction_id,
        amount=payload.amount,
        transaction_date=payload.transaction_date,
        category_id=parse_uuid(payload.category_id, "category_id"),
        description=payload.description,
        merchant=payload.merchant,
        notes=payload.notes,
        reference=payload.reference,
    )
    db.commit()
    db.refresh(txn)
    return single(txn_service.serialize_transaction(txn))


@router.delete("/transactions/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_transaction(
    transaction_id: uuid.UUID,
    db: DbSession = Depends(db_session),
    user: User = Depends(current_user),
) -> Response:
    txn_service.delete_transaction(db, user=user, transaction_id=transaction_id)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------------- transfers


def _serialize_transfer(db: DbSession, transfer: Transfer, user: User) -> dict:
    from app.models.finance import Account

    src = db.get(Account, transfer.source_account_id)
    dst = db.get(Account, transfer.destination_account_id)
    return {
        "id": str(transfer.id),
        "source_account": {"id": str(src.id), "name": src.name},
        "destination_account": {"id": str(dst.id), "name": dst.name},
        "amount": serialize(Decimal(transfer.source_amount)),
        "currency": transfer.source_currency,
        "transfer_date": transfer.transfer_date.isoformat(),
        "notes": transfer.notes,
        "status": transfer.status.value,
    }


@router.post("/transfers", status_code=status.HTTP_201_CREATED)
def create_transfer(
    payload: TransferCreate,
    db: DbSession = Depends(db_session),
    user: User = Depends(current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    # Replaying the same key returns the original transfer rather than
    # posting a second one (API spec section 44).
    if idempotency_key:
        existing = db.scalar(
            select(Transfer).where(
                Transfer.created_by == user.id, Transfer.idempotency_key == idempotency_key
            )
        )
        if existing is not None:
            db.commit()
            return single(_serialize_transfer(db, existing, user))

    source = get_transactable_account(
        db, parse_uuid(payload.source_account_id, "source_account_id"), user
    )
    destination = get_transactable_account(
        db, parse_uuid(payload.destination_account_id, "destination_account_id"), user
    )
    amount = payload.source_amount
    dest_amount = payload.destination_amount if payload.destination_amount is not None else amount

    transfer = PostingService(db).transfer_funds(
        source=source,
        destination=destination,
        source_amount=amount,
        destination_amount=dest_amount,
        transfer_date=payload.transfer_date,
        actor_id=user.id,
        notes=payload.notes,
        idempotency_key=idempotency_key,
    )
    # One commit for the transfer and both ledger entries (Architecture section 23).
    db.commit()
    db.refresh(transfer)
    return single(_serialize_transfer(db, transfer, user))


@router.get("/transfers/{transfer_id}")
def get_transfer(
    transfer_id: uuid.UUID,
    db: DbSession = Depends(db_session),
    user: User = Depends(current_user),
) -> dict:
    transfer = db.get(Transfer, transfer_id)
    if transfer is None:
        raise NotFound("Transfer not found.", code="TRANSFER_NOT_FOUND")
    # Viewing requires access to at least one side.
    get_viewable_account(db, transfer.source_account_id, user)
    db.commit()
    return single(_serialize_transfer(db, transfer, user))


@router.post("/transfers/{transfer_id}/cancel")
def cancel_transfer(
    transfer_id: uuid.UUID,
    db: DbSession = Depends(db_session),
    user: User = Depends(current_user),
) -> dict:
    transfer = db.get(Transfer, transfer_id)
    if transfer is None:
        raise NotFound("Transfer not found.", code="TRANSFER_NOT_FOUND")
    get_transactable_account(db, transfer.source_account_id, user)
    get_transactable_account(db, transfer.destination_account_id, user)
    PostingService(db).cancel_transfer(transfer, actor_id=user.id)
    db.commit()
    db.refresh(transfer)
    return single(_serialize_transfer(db, transfer, user))


# -------------------------------------------------------------------- categories


@router.get("/categories")
def list_categories(
    type: CategoryType | None = None,  # noqa: A002
    db: DbSession = Depends(db_session),
    user: User = Depends(current_user),
) -> dict:
    rows = category_service.list_categories(db, user_id=user.id, category_type=type)
    db.commit()
    return collection(
        [
            {
                "id": str(c.id),
                "name": c.name,
                "category_type": c.category_type.value,
                "is_system": c.is_system,
                "status": c.status.value,
            }
            for c in rows
        ],
        limit=len(rows),
    )


@router.post("/categories", status_code=status.HTTP_201_CREATED)
def create_category(
    payload: CategoryCreate,
    db: DbSession = Depends(db_session),
    user: User = Depends(current_user),
) -> dict:
    from sqlalchemy.exc import IntegrityError

    category = Category(
        user_id=user.id,
        name=payload.name,
        category_type=CategoryType(payload.category_type),
        parent_category_id=parse_uuid(payload.parent_category_id, "parent_category_id"),
        is_system=False,
    )
    db.add(category)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise Conflict(
            "A category with that name already exists.", code="CATEGORY_ALREADY_EXISTS"
        ) from exc
    db.refresh(category)
    return single(
        {
            "id": str(category.id),
            "name": category.name,
            "category_type": category.category_type.value,
            "is_system": category.is_system,
            "status": category.status.value,
        }
    )
