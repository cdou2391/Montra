"""Server-side authorization for account-scoped resources.

Architecture ADR-009 and section 35: authorization is enforced in the backend
service layer, never in the client, and never by filtering after serialization.

Family visibility (FAMILY_VISIBLE / SHARED) arrives in Phase 16-19. Until then
every account resolves through the owner check below, but callers already go
through this seam so that adding family rules does not mean revisiting routes.
"""

import uuid

from sqlalchemy import Select, select
from sqlalchemy.orm import Session as DbSession

from app.core.errors import NotFound, PermissionDenied
from app.db.enums import AccountStatus
from app.models.finance import Account
from app.models.user import User


def visible_accounts(user: User, *, include_archived: bool = False) -> Select:
    """Base statement for accounts the user may see in personal context."""
    stmt = select(Account).where(Account.owner_user_id == user.id)
    if not include_archived:
        stmt = stmt.where(Account.status == AccountStatus.ACTIVE)
    return stmt


def can_view(account: Account, user: User) -> bool:
    return account.owner_user_id == user.id


def can_edit(account: Account, user: User) -> bool:
    return account.owner_user_id == user.id


def can_transact(account: Account, user: User) -> bool:
    return account.owner_user_id == user.id and account.status is AccountStatus.ACTIVE


def get_viewable_account(db: DbSession, account_id: uuid.UUID, user: User) -> Account:
    """Fetch an account the user may view.

    Returns 404 rather than 403 when the user cannot view it, so the API never
    confirms that another user's private account exists (API spec section 7).
    """
    account = db.get(Account, account_id)
    if account is None or not can_view(account, user):
        raise NotFound("Account not found.", code="ACCOUNT_NOT_FOUND")
    return account


def get_editable_account(db: DbSession, account_id: uuid.UUID, user: User) -> Account:
    account = get_viewable_account(db, account_id, user)
    if not can_edit(account, user):
        raise PermissionDenied(
            "You do not have permission to modify this account.", code="ACCOUNT_NOT_EDITABLE"
        )
    return account


def get_transactable_account(db: DbSession, account_id: uuid.UUID, user: User) -> Account:
    account = get_viewable_account(db, account_id, user)
    if not can_transact(account, user):
        raise PermissionDenied(
            "You cannot record transactions on this account.", code="ACCOUNT_NOT_TRANSACTABLE"
        )
    return account
