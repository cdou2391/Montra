"""Transaction query and mutation service (Implementation Plan Phase 6).

All balance-moving writes delegate to PostingService; nothing here decides a
ledger direction on its own.
"""

import base64
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import or_, select, tuple_
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import selectinload

from app.core.errors import Conflict, NotFound, ValidationFailed
from app.db.base import utcnow
from app.db.enums import TransactionStatus, TransactionType
from app.models.finance import Account, Category, Transaction
from app.models.user import User
from app.services.authz import get_transactable_account, get_viewable_account, visible_accounts
from app.services.posting import PostingService

MAX_LIMIT = 100
DEFAULT_LIMIT = 50


def _encode_cursor(txn: Transaction) -> str:
    raw = f"{txn.transaction_date.isoformat()}|{txn.created_at.isoformat()}|{txn.id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[date, datetime, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        d, created, ident = raw.split("|")
        return date.fromisoformat(d), datetime.fromisoformat(created), uuid.UUID(ident)
    except Exception as exc:
        raise ValidationFailed(
            details=[{"field": "cursor", "message": "Invalid pagination cursor."}]
        ) from exc


def create_transaction(
    db: DbSession,
    *,
    user: User,
    account_id: uuid.UUID,
    transaction_type: TransactionType,
    amount: Decimal,
    transaction_date: date,
    category_id: uuid.UUID | None = None,
    description: str | None = None,
    merchant: str | None = None,
    notes: str | None = None,
    reference: str | None = None,
) -> Transaction:
    if transaction_type is TransactionType.TRANSFER:
        raise ValidationFailed(
            "Use the transfers endpoint to move money between accounts.",
            code="USE_TRANSFER_ENDPOINT",
        )

    account = get_transactable_account(db, account_id, user)
    if category_id is not None:
        _require_own_category(db, category_id, user)

    posting = PostingService(db)
    fields = {
        "category_id": category_id,
        "description": description,
        "merchant": merchant,
        "notes": notes,
        "reference": reference,
    }
    if transaction_type is TransactionType.INCOME:
        return posting.record_income(
            account=account,
            amount=amount,
            currency=account.currency,
            transaction_date=transaction_date,
            actor_id=user.id,
            **fields,
        )
    if transaction_type is TransactionType.EXPENSE:
        return posting.record_expense(
            account=account,
            amount=amount,
            currency=account.currency,
            transaction_date=transaction_date,
            actor_id=user.id,
            **fields,
        )
    raise ValidationFailed(
        "Adjustments are created through the balance-adjustments endpoint.",
        code="USE_ADJUSTMENT_ENDPOINT",
    )


def _require_own_category(db: DbSession, category_id: uuid.UUID, user: User) -> Category:
    category = db.get(Category, category_id)
    if category is None or category.user_id != user.id:
        raise NotFound("Category not found.", code="CATEGORY_NOT_FOUND")
    return category


def get_transaction(db: DbSession, transaction_id: uuid.UUID, user: User) -> Transaction:
    txn = db.get(Transaction, transaction_id)
    if txn is None or txn.deleted_at is not None:
        raise NotFound("Transaction not found.", code="TRANSACTION_NOT_FOUND")
    get_viewable_account(db, txn.account_id, user)
    return txn


def update_transaction(
    db: DbSession,
    *,
    user: User,
    transaction_id: uuid.UUID,
    amount: Decimal | None = None,
    transaction_date: date | None = None,
    category_id: uuid.UUID | None = None,
    description: str | None = None,
    merchant: str | None = None,
    notes: str | None = None,
    reference: str | None = None,
) -> Transaction:
    txn = get_transaction(db, transaction_id, user)
    if txn.transfer_id is not None:
        raise Conflict(
            "A transfer side cannot be edited directly. Cancel the transfer instead.",
            code="TRANSFER_SIDE_NOT_EDITABLE",
        )
    get_transactable_account(db, txn.account_id, user)

    if amount is not None:
        if amount <= 0:
            raise ValidationFailed(
                details=[{"field": "amount", "message": "Amount must be greater than zero."}]
            )
        # Direction is a function of type and account nature, both unchanged
        # here, so re-deriving it is unnecessary: only the magnitude moves.
        txn.amount = amount
    if transaction_date is not None:
        txn.transaction_date = transaction_date
    if category_id is not None:
        _require_own_category(db, category_id, user)
        txn.category_id = category_id
    if description is not None:
        txn.description = description
    if merchant is not None:
        txn.merchant = merchant
    if notes is not None:
        txn.notes = notes
    if reference is not None:
        txn.reference = reference
    db.flush()
    return txn


def delete_transaction(db: DbSession, *, user: User, transaction_id: uuid.UUID) -> None:
    txn = get_transaction(db, transaction_id, user)
    if txn.transfer_id is not None:
        raise Conflict(
            "A transfer side cannot be deleted independently. Cancel the transfer instead.",
            code="TRANSFER_SIDE_NOT_DELETABLE",
        )
    get_transactable_account(db, txn.account_id, user)
    txn.deleted_at = utcnow()
    db.flush()


def list_transactions(
    db: DbSession,
    *,
    user: User,
    account_id: uuid.UUID | None = None,
    category_id: uuid.UUID | None = None,
    transaction_type: TransactionType | None = None,
    status: TransactionStatus | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    min_amount: Decimal | None = None,
    max_amount: Decimal | None = None,
    search: str | None = None,
    limit: int = DEFAULT_LIMIT,
    cursor: str | None = None,
) -> tuple[list[Transaction], str | None]:
    limit = max(1, min(limit, MAX_LIMIT))

    # Scope first: only transactions on accounts this user may view.
    account_ids = select(visible_accounts(user, include_archived=True).subquery().c.id)

    stmt = (
        select(Transaction)
        .options(selectinload(Transaction.account), selectinload(Transaction.category))
        .where(Transaction.account_id.in_(account_ids), Transaction.deleted_at.is_(None))
    )

    if account_id is not None:
        get_viewable_account(db, account_id, user)
        stmt = stmt.where(Transaction.account_id == account_id)
    if category_id is not None:
        stmt = stmt.where(Transaction.category_id == category_id)
    if transaction_type is not None:
        stmt = stmt.where(Transaction.transaction_type == transaction_type)
    if status is not None:
        stmt = stmt.where(Transaction.status == status)
    if date_from is not None:
        stmt = stmt.where(Transaction.transaction_date >= date_from)
    if date_to is not None:
        stmt = stmt.where(Transaction.transaction_date <= date_to)
    if min_amount is not None:
        stmt = stmt.where(Transaction.amount >= min_amount)
    if max_amount is not None:
        stmt = stmt.where(Transaction.amount <= max_amount)
    if search:
        pattern = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                Transaction.description.ilike(pattern),
                Transaction.merchant.ilike(pattern),
                Transaction.notes.ilike(pattern),
                Transaction.reference.ilike(pattern),
            )
        )
    if cursor:
        # Keyset pagination on the same tuple the ORDER BY uses, so rows that
        # tie on date are neither skipped nor returned twice.
        c_date, c_created, c_id = _decode_cursor(cursor)
        stmt = stmt.where(
            tuple_(Transaction.transaction_date, Transaction.created_at, Transaction.id)
            < (c_date, c_created, c_id)
        )

    stmt = stmt.order_by(
        Transaction.transaction_date.desc(), Transaction.created_at.desc(), Transaction.id.desc()
    ).limit(limit + 1)

    rows = list(db.scalars(stmt))
    next_cursor = None
    if len(rows) > limit:
        rows = rows[:limit]
        next_cursor = _encode_cursor(rows[-1])
    return rows, next_cursor


def serialize_transaction(txn: Transaction, account: Account | None = None) -> dict:
    from app.core.money import serialize

    account = account or txn.account
    return {
        "id": str(txn.id),
        "account": {"id": str(account.id), "name": account.name} if account else None,
        "transaction_type": txn.transaction_type.value,
        "amount": serialize(Decimal(txn.amount)),
        "currency": txn.currency,
        "direction": txn.direction.value,
        "transaction_date": txn.transaction_date.isoformat(),
        "status": txn.status.value,
        "description": txn.description,
        "merchant": txn.merchant,
        "notes": txn.notes,
        "reference": txn.reference,
        "category": (
            {"id": str(txn.category.id), "name": txn.category.name} if txn.category else None
        ),
        "transfer_id": str(txn.transfer_id) if txn.transfer_id else None,
        "created_at": txn.created_at.isoformat(),
    }
