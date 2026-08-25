"""Account domain service (Implementation Plan Phase 4)."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import case, exists, literal, select
from sqlalchemy.orm import Session as DbSession

from app.core.errors import Conflict, NotFound, ValidationFailed
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
from app.services import audit
from app.services.authz import visible_accounts
from app.services.credit_cards import apply_card_fields, card_fields_payload, expiry_state
from app.services.posting import PostingService


def _resolve_sharing(
    db: DbSession,
    *,
    user: User,
    visibility: Visibility,
    family_id: uuid.UUID | None,
) -> uuid.UUID | None:
    """Work out which household a record belongs to, if any.

    Sharing is derived from the caller's active membership rather than trusted
    from the request: a client must not be able to attach a record to a
    household by naming its id.
    """
    from app.services.families import active_membership

    if visibility is Visibility.PRIVATE:
        return None  # A private record belongs to no household, whatever was sent.

    membership = active_membership(db, user)
    if membership is None:
        raise ValidationFailed(
            "You are not in a household yet.",
            code="NO_ACTIVE_FAMILY",
            details=[{"field": "visibility", "message": "Join or create a household first."}],
        )
    if family_id is not None and family_id != membership.family_id:
        raise ValidationFailed(
            "That is not your household.",
            code="NO_ACTIVE_FAMILY",
            details=[{"field": "family_id", "message": "You belong to a different household."}],
        )
    return membership.family_id


def create_account(
    db: DbSession,
    *,
    user: User,
    name: str,
    account_type: AccountType,
    currency: str,
    opening_balance: Decimal,
    opening_balance_at: datetime,
    ownership_type: OwnershipType = OwnershipType.PERSONAL,
    visibility: Visibility = Visibility.PRIVATE,
    institution_id: uuid.UUID | None = None,
    account_identifier: str | None = None,
    description: str | None = None,
    family_id: uuid.UUID | None = None,
    card_fields: dict | None = None,
) -> Account:
    family_id = _resolve_sharing(db, user=user, visibility=visibility, family_id=family_id)

    account = Account(
        owner_user_id=user.id,
        family_id=family_id,
        name=name.strip(),
        account_type=account_type,
        ownership_type=ownership_type,
        visibility=visibility,
        currency=currency.upper(),
        opening_balance=opening_balance,
        opening_balance_at=opening_balance_at,
        institution_id=institution_id,
        account_identifier=account_identifier,
        description=description,
        status=AccountStatus.ACTIVE,
        created_by=user.id,
    )
    if card_fields:
        apply_card_fields(account, card_fields)

    db.add(account)
    db.flush()
    audit.record(
        db,
        actor=user,
        event_type=audit.ACCOUNT_CREATED,
        entity_type=audit.ACCOUNT,
        entity_id=account.id,
        family_id=account.family_id,
        metadata={"account_type": account.account_type.value, "currency": account.currency},
    )
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
    card_fields: dict | None = None,
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
    if card_fields:
        apply_card_fields(account, card_fields)
    db.flush()
    return account


def archive_account(db: DbSession, account: Account) -> Account:
    if account.status is AccountStatus.ARCHIVED:
        raise Conflict("Account is already archived.", code="ACCOUNT_ALREADY_ARCHIVED")
    account.status = AccountStatus.ARCHIVED
    account.archived_at = utcnow()
    db.flush()
    audit.record(
        db,
        actor=None,
        event_type=audit.ACCOUNT_ARCHIVED,
        entity_type=audit.ACCOUNT,
        entity_id=account.id,
        family_id=account.family_id,
    )
    return account


def restore_account(db: DbSession, account: Account) -> Account:
    if account.status is AccountStatus.ACTIVE:
        raise Conflict("Account is already active.", code="ACCOUNT_ALREADY_ACTIVE")
    account.status = AccountStatus.ACTIVE
    account.archived_at = None
    db.flush()
    return account


def favorite_account_id(db: DbSession, user: User) -> uuid.UUID | None:
    from app.models.user import UserPreference

    return db.scalar(
        select(UserPreference.favorite_account_id).where(UserPreference.user_id == user.id)
    )


def set_favorite_account(
    db: DbSession, *, user: User, account_id: uuid.UUID | None
) -> uuid.UUID | None:
    """Choose the account that leads every list, or clear the choice.

    Setting a new favourite replaces the old one: there is exactly one, because
    "first" only means something for one account.
    """
    from app.models.user import UserPreference

    if account_id is not None:
        # Only an account the user can actually see may be favourited.
        from app.services.authz import get_viewable_account

        account_id = get_viewable_account(db, account_id, user).id

    preferences = db.scalar(select(UserPreference).where(UserPreference.user_id == user.id))
    if preferences is None:
        raise NotFound("Preferences not found.", code="PREFERENCES_NOT_FOUND")
    preferences.favorite_account_id = account_id
    db.flush()
    return account_id


def list_accounts(
    db: DbSession,
    *,
    user: User,
    status: AccountStatus | None = None,
    account_type: AccountType | None = None,
    limit: int = 50,
    context: str = "personal",
) -> list[Account]:
    stmt = visible_accounts(db, user, include_archived=True, context=context)
    if status is not None:
        stmt = stmt.where(Account.status == status)
    else:
        stmt = stmt.where(Account.status == AccountStatus.ACTIVE)
    if account_type is not None:
        stmt = stmt.where(Account.account_type == account_type)

    # Sorted here rather than in the client, so the accounts screen, every
    # account dropdown and the API all agree on what comes first.
    favorite = favorite_account_id(db, user)
    ordering = case((Account.id == favorite, 0), else_=1) if favorite else literal(1)
    return list(db.scalars(stmt.order_by(ordering, Account.name).limit(limit)))


def masked_identifier(account: Account) -> str | None:
    if not account.account_identifier:
        return None
    tail = account.account_identifier[-4:]
    return f"**** {tail}"


def serialize_account(
    db: DbSession,
    account: Account,
    user: User,
    *,
    favorite: uuid.UUID | None = None,
    access=None,
) -> dict:
    from app.core.money import serialize
    from app.services.authz import can_edit, can_transact, resolve

    # Callers serializing a list pass this in, to avoid one membership lookup
    # per account.
    if access is None:
        access = resolve(db, user)

    # Callers serializing a list pass the favourite in, to avoid one query per
    # account.
    if favorite is None:
        favorite = favorite_account_id(db, user)
    posting = PostingService(db)
    balance = posting.balance_of(account)
    return {
        "id": str(account.id),
        "name": account.name,
        "account_type": account.account_type.value,
        "account_nature": nature_for(account.account_type).value,
        "currency": account.currency,
        "balance": serialize(balance),
        "opening_balance": serialize(Decimal(account.opening_balance)),
        "opening_balance_at": account.opening_balance_at.isoformat(),
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
        "can_edit": can_edit(account, access),
        "can_transact": can_transact(account, access),
        # The balance is already computed above; a card gets its headroom from
        # it rather than the client subtracting one from the other.
        "credit_card": card_fields_payload(account, outstanding=balance),
        # Any card can expire, so this sits beside the account rather than
        # inside the credit-card block.
        "expiry": expiry_state(account),
        "is_favorite": favorite == account.id,
    }


def set_visibility(
    db: DbSession, *, account: Account, user: User, visibility: Visibility
) -> Account:
    """Move an account between private, family-visible and shared.

    Visibility is inherited by everything the account holds, so this one field
    decides what the household can see of its history too (API spec section 18).
    """
    previous = account.visibility
    # Un-sharing clears family_id, and an event recorded against the cleared
    # value would vanish from the household's own trail — which is precisely
    # the change members most need to see. Attribute it to the household the
    # account is leaving.
    previous_family_id = account.family_id
    account.family_id = _resolve_sharing(
        db, user=user, visibility=visibility, family_id=account.family_id
    )
    account.visibility = visibility
    if visibility is not Visibility.SHARED and account.ownership_type is OwnershipType.JOINT:
        # A joint account that is no longer shared has nobody to be joint with.
        account.ownership_type = OwnershipType.PERSONAL
    db.flush()
    # Who can see this account is exactly the kind of change a household needs
    # a record of, so the direction of travel is named rather than inferred.
    if visibility is Visibility.PRIVATE:
        event = audit.ACCOUNT_MADE_PRIVATE
    elif visibility is Visibility.SHARED:
        event = audit.ACCOUNT_SHARED
    else:
        event = audit.ACCOUNT_VISIBILITY_CHANGED
    audit.record(
        db,
        actor=user,
        event_type=event,
        entity_type=audit.ACCOUNT,
        entity_id=account.id,
        family_id=account.family_id or previous_family_id,
        metadata={"from": previous.value, "to": visibility.value},
    )
    return account
