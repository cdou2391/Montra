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
from app.core.timezone import day_end, day_start, ensure_aware
from app.db.base import utcnow
from app.db.enums import TransactionStatus, TransactionType
from app.models.finance import Account, Category, Transaction
from app.models.user import User
from app.services.authz import get_transactable_account, get_viewable_account, visible_accounts
from app.services.posting import PostingService

MAX_LIMIT = 100
DEFAULT_LIMIT = 50


def _encode_cursor(txn: Transaction) -> str:
    raw = f"{txn.occurred_at.isoformat()}|{txn.id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        occurred, ident = raw.split("|")
        return datetime.fromisoformat(occurred), uuid.UUID(ident)
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
    occurred_at: datetime,
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

    # A client may post a naive local datetime; anchor it to the user's zone
    # before it reaches the ledger, where everything is UTC.
    occurred_at = ensure_aware(occurred_at, user.timezone)

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
            occurred_at=occurred_at,
            actor_id=user.id,
            **fields,
        )
    if transaction_type is TransactionType.EXPENSE:
        return posting.record_expense(
            account=account,
            amount=amount,
            currency=account.currency,
            occurred_at=occurred_at,
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
    occurred_at: datetime | None = None,
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
    if occurred_at is not None:
        txn.occurred_at = ensure_aware(occurred_at, user.timezone)
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
    owner_id: uuid.UUID | None = None,
    transaction_type: TransactionType | None = None,
    status: TransactionStatus | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    min_amount: Decimal | None = None,
    max_amount: Decimal | None = None,
    search: str | None = None,
    limit: int = DEFAULT_LIMIT,
    cursor: str | None = None,
    context: str = "personal",
) -> tuple[list[Transaction], str | None]:
    limit = max(1, min(limit, MAX_LIMIT))

    # Scope first: only transactions on accounts this user may view, in the
    # requested context. Private data is excluded here rather than filtered
    # out of the results afterwards.
    account_ids = select(
        visible_accounts(db, user, include_archived=True, context=context).subquery().c.id
    )

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
    if owner_id is not None:
        # Whose money moved, in a household where several people's accounts are
        # in view. Narrowing to accounts they own is enough: the visibility
        # scope above has already excluded anything private to them.
        stmt = stmt.where(
            Transaction.account_id.in_(
                select(Account.id).where(Account.owner_user_id == owner_id)
            )
        )
    if transaction_type is not None:
        stmt = stmt.where(Transaction.transaction_type == transaction_type)
    if status is not None:
        stmt = stmt.where(Transaction.status == status)
    if date_from is not None:
        stmt = stmt.where(Transaction.occurred_at >= day_start(date_from, user.timezone))
    if date_to is not None:
        # Exclusive upper bound on the next local day, so 23:59 still counts.
        stmt = stmt.where(Transaction.occurred_at < day_end(date_to, user.timezone))
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
        # tie on the exact instant are neither skipped nor returned twice.
        c_occurred, c_id = _decode_cursor(cursor)
        stmt = stmt.where(tuple_(Transaction.occurred_at, Transaction.id) < (c_occurred, c_id))

    stmt = stmt.order_by(Transaction.occurred_at.desc(), Transaction.id.desc()).limit(limit + 1)

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
        "occurred_at": txn.occurred_at.isoformat(),
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


def redacted_account_ref(account, access) -> dict:
    """One side of a transfer, as this viewer is allowed to see it.

    Implementation Plan Phase 20 and Data Model section 48: a household member
    watching money leave a shared account may see that it went somewhere
    private, and nothing more. Not the id, not the name, not the balance.

    The linkage stays intact in the database; only the projection is reduced.
    """
    from app.services.authz import can_view

    if account is None:
        return None
    if can_view(account, access):
        return {"id": str(account.id), "name": account.name}
    return {"visibility": "PRIVATE", "display_name": "Private account"}


def serialize_transfer(db, transfer, access) -> dict:
    from decimal import Decimal

    from app.core.money import serialize
    from app.models.finance import Account

    source = db.get(Account, transfer.source_account_id)
    destination = db.get(Account, transfer.destination_account_id)
    return {
        "id": str(transfer.id),
        "source_account": redacted_account_ref(source, access),
        "destination_account": redacted_account_ref(destination, access),
        "amount": serialize(Decimal(transfer.source_amount)),
        "currency": transfer.source_currency,
        "occurred_at": transfer.occurred_at.isoformat(),
        "notes": transfer.notes,
        "status": transfer.status.value,
    }
