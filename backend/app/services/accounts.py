"""Account domain service (Implementation Plan Phase 4)."""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import exists, select
from sqlalchemy.orm import Session as DbSession

from app.core.errors import Conflict, ValidationFailed
from app.db.base import utcnow
from app.db.enums import (
    AccountStatus,
    AccountType,
    OwnershipType,
    Visibility,
    nature_for,
)
from app.models.finance import Account, Transaction
from app.models.user import User
from app.services.authz import visible_accounts
from app.services.posting import PostingService


def create_account(
    db: DbSession,
    *,
    user: User,
    name: str,
    account_type: AccountType,
    currency: str,
    opening_balance: Decimal,
    opening_balance_date: date,
    ownership_type: OwnershipType = OwnershipType.PERSONAL,
    visibility: Visibility = Visibility.PRIVATE,
    institution_id: uuid.UUID | None = None,
    account_identifier: str | None = None,
    description: str | None = None,
    family_id: uuid.UUID | None = None,
) -> Account:
    if visibility is not Visibility.PRIVATE or family_id is not None:
        # Family sharing lands in Phase 16-19; refuse rather than silently
        # storing a visibility the backend cannot yet enforce.
        raise ValidationFailed(
            "Family sharing is not available yet.",
            code="NO_ACTIVE_FAMILY",
            details=[{"field": "visibility", "message": "Only PRIVATE accounts are supported."}],
        )

    account = Account(
        owner_user_id=user.id,
        name=name.strip(),
        account_type=account_type,
        ownership_type=ownership_type,
        visibility=visibility,
        currency=currency.upper(),
        opening_balance=opening_balance,
        opening_balance_date=opening_balance_date,
        institution_id=institution_id,
        account_identifier=account_identifier,
        description=description,
        status=AccountStatus.ACTIVE,
        created_by=user.id,
    )
    db.add(account)
    db.flush()
    return account


def has_financial_activity(db: DbSession, account: Account) -> bool:
    return bool(db.scalar(select(exists().where(Transaction.account_id == account.id))))


def update_account(
    db: DbSession,
    *,
    account: Account,
    name: str | None = None,
    description: str | None = None,
    institution_id: uuid.UUID | None = None,
    account_identifier: str | None = None,
    currency: str | None = None,
) -> Account:
    if currency is not None and currency.upper() != account.currency:
        if has_financial_activity(db, account):
            raise Conflict(
                "Account currency cannot change once transactions exist.",
                code="ACCOUNT_CURRENCY_IMMUTABLE",
            )
        account.currency = currency.upper()
    if name is not None:
        account.name = name.strip()
    if description is not None:
        account.description = description
    if institution_id is not None:
        account.institution_id = institution_id
    if account_identifier is not None:
        account.account_identifier = account_identifier
    db.flush()
    return account


def archive_account(db: DbSession, account: Account) -> Account:
    if account.status is AccountStatus.ARCHIVED:
        raise Conflict("Account is already archived.", code="ACCOUNT_ALREADY_ARCHIVED")
    account.status = AccountStatus.ARCHIVED
    account.archived_at = utcnow()
    db.flush()
    return account


def restore_account(db: DbSession, account: Account) -> Account:
    if account.status is AccountStatus.ACTIVE:
        raise Conflict("Account is already active.", code="ACCOUNT_ALREADY_ACTIVE")
    account.status = AccountStatus.ACTIVE
    account.archived_at = None
    db.flush()
    return account


def list_accounts(
    db: DbSession,
    *,
    user: User,
    status: AccountStatus | None = None,
    account_type: AccountType | None = None,
    limit: int = 50,
) -> list[Account]:
    stmt = visible_accounts(user, include_archived=True)
    if status is not None:
        stmt = stmt.where(Account.status == status)
    else:
        stmt = stmt.where(Account.status == AccountStatus.ACTIVE)
    if account_type is not None:
        stmt = stmt.where(Account.account_type == account_type)
    return list(db.scalars(stmt.order_by(Account.name).limit(limit)))


def masked_identifier(account: Account) -> str | None:
    if not account.account_identifier:
        return None
    tail = account.account_identifier[-4:]
    return f"**** {tail}"


def serialize_account(db: DbSession, account: Account, user: User) -> dict:
    from app.core.money import serialize
    from app.services.authz import can_edit, can_transact

    posting = PostingService(db)
    return {
        "id": str(account.id),
        "name": account.name,
        "account_type": account.account_type.value,
        "account_nature": nature_for(account.account_type).value,
        "currency": account.currency,
        "balance": serialize(posting.balance_of(account)),
        "opening_balance": serialize(Decimal(account.opening_balance)),
        "opening_balance_date": account.opening_balance_date.isoformat(),
        "masked_identifier": masked_identifier(account),
        "visibility": account.visibility.value,
        "ownership_type": account.ownership_type.value,
        "status": account.status.value,
        "description": account.description,
        "institution": (
            {"id": str(account.institution.id), "name": account.institution.name}
            if account.institution
            else None
        ),
        "owner": {
            "id": str(user.id),
            "display_name": user.display_name,
        },
        "can_edit": can_edit(account, user),
        "can_transact": can_transact(account, user),
    }
