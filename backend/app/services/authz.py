"""Server-side authorization for account-scoped resources.

Every rule about who may see or touch a financial record lives here. Three
visibilities, and reading is not writing:

    PRIVATE         owner only. Everyone else gets 404, not 403, so the API
                    never confirms the record exists.
    FAMILY_VISIBLE  the household may read; only the owner may write. Showing
                    someone a salary account is not handing them a pen.
    SHARED          the household may read, OWNER/ADULT may write.

Child records resolve through their account, never their own `created_by`:
the account is what carries the visibility.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import Select, or_, select
from sqlalchemy.orm import Session as DbSession

from app.core.errors import NotFound, PermissionDenied
from app.db.enums import (
    TRANSACTING_ROLES,
    AccountStatus,
    FamilyRole,
    MembershipStatus,
    Visibility,
)
from app.models.finance import Account
from app.models.user import User


@dataclass(frozen=True)
class Access:
    """A caller plus the household they are acting in.

    Resolved once per request rather than per account in a list.
    """

    user: User
    family_id: uuid.UUID | None = None
    role: FamilyRole | None = None

    @property
    def in_family(self) -> bool:
        return self.family_id is not None

    @property
    def may_transact_on_shared(self) -> bool:
        return self.role in TRANSACTING_ROLES


def resolve(db: DbSession, user: User) -> Access:
    """The FamilyContextResolver of Implementation Plan Phase 17."""
    from app.models.family import FamilyMembership

    membership = db.scalar(
        select(FamilyMembership).where(
            FamilyMembership.user_id == user.id,
            FamilyMembership.status == MembershipStatus.ACTIVE,
        )
    )
    if membership is None:
        return Access(user=user)
    return Access(user=user, family_id=membership.family_id, role=membership.role)


# ------------------------------------------------------------------- decisions


def can_view(account: Account, access: Access) -> bool:
    if account.owner_user_id == access.user.id:
        return True
    if not access.in_family or account.family_id != access.family_id:
        return False
    return account.visibility in (Visibility.FAMILY_VISIBLE, Visibility.SHARED)


def can_edit(account: Account, access: Access) -> bool:
    """Editing means the account's own settings — name, visibility, archiving."""
    if account.owner_user_id == access.user.id:
        return True
    # A shared account with no single owner is the household's to manage.
    if (
        account.visibility is Visibility.SHARED
        and access.in_family
        and account.family_id == access.family_id
    ):
        return access.may_transact_on_shared
    return False


def can_transact(account: Account, access: Access) -> bool:
    """Writing money to it, which is a narrower right than seeing it."""
    if account.status is not AccountStatus.ACTIVE:
        return False
    if account.owner_user_id == access.user.id:
        return True
    if (
        account.visibility is Visibility.SHARED
        and access.in_family
        and account.family_id == access.family_id
    ):
        return access.may_transact_on_shared
    # FAMILY_VISIBLE is deliberately absent: visible is not writable.
    return False


def _access(db: DbSession, who: "User | Access") -> Access:
    """Accept a caller either way.

    One account can pass the user; anything iterating resolves once and passes
    the Access, so a list runs no membership query per row.
    """
    return who if isinstance(who, Access) else resolve(db, who)


# --------------------------------------------------------------------- scoping


def visible_accounts(
    db: DbSession,
    who: "User | Access",
    *,
    include_archived: bool = False,
    context: str = "personal",
) -> Select:
    """Accounts the caller may see, in the requested context.

    Personal is what they own plus the household's shared accounts, which are
    genuinely theirs to use. Family is FAMILY_VISIBLE and SHARED, never
    PRIVATE, whoever owns it.
    """
    access = _access(db, who)
    owned = Account.owner_user_id == access.user.id

    if context == "family":
        if not access.in_family:
            # An impossible predicate, not a silent fallback to personal data.
            return select(Account).where(Account.id.is_(None))
        stmt = select(Account).where(
            Account.family_id == access.family_id,
            Account.visibility.in_((Visibility.FAMILY_VISIBLE, Visibility.SHARED)),
        )
    elif access.in_family:
        stmt = select(Account).where(
            or_(
                owned,
                (Account.family_id == access.family_id) & (Account.visibility == Visibility.SHARED),
            )
        )
    else:
        stmt = select(Account).where(owned)

    if not include_archived:
        stmt = stmt.where(Account.status == AccountStatus.ACTIVE)
    return stmt


# ------------------------------------------------------------------- fetching


def get_viewable_account(db: DbSession, account_id: uuid.UUID, who: "User | Access") -> Account:
    access = _access(db, who)
    account = db.get(Account, account_id)
    if account is None or not can_view(account, access):
        raise NotFound("Account not found.", code="ACCOUNT_NOT_FOUND")
    return account


def get_editable_account(db: DbSession, account_id: uuid.UUID, who: "User | Access") -> Account:
    access = _access(db, who)
    account = get_viewable_account(db, account_id, access)
    if not can_edit(account, access):
        raise PermissionDenied(
            "You do not have permission to modify this account.", code="ACCOUNT_NOT_EDITABLE"
        )
    return account


def get_transactable_account(db: DbSession, account_id: uuid.UUID, who: "User | Access") -> Account:
    access = _access(db, who)
    account = get_viewable_account(db, account_id, access)
    if not can_transact(account, access):
        raise PermissionDenied(
            "You cannot record transactions on this account.",
            code="ACCOUNT_NOT_TRANSACTABLE",
        )
    return account
