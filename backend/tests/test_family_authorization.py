"""Family authorization — the visibility matrix, tested exhaustively.

The rules under test:

    PRIVATE         owner only. Everyone else gets 404, never 403 — a 403
                    would confirm the account exists.
    FAMILY_VISIBLE  the household may read. Only the owner may write:
                    showing someone your salary account is not handing them
                    a pen.
    SHARED          the household may read; OWNER and ADULT may write.
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.core.errors import NotFound, PermissionDenied
from app.db.enums import FamilyRole, Visibility
from app.services import authz
from app.services.families import set_member_role
from tests.conftest import make_account

NOW = datetime(2026, 8, 24, 12, 0, tzinfo=UTC)


# --------------------------------------------------------------------- PRIVATE


def test_private_account_is_invisible_to_a_household_member(db, user, other_user, family):
    account = make_account(db, user, "My Private", Visibility.PRIVATE)
    theirs = authz.resolve(db, other_user)

    assert authz.can_view(account, theirs) is False
    # 404, not 403: the API must not confirm it exists.
    with pytest.raises(NotFound):
        authz.get_viewable_account(db, account.id, theirs)


def test_private_account_is_invisible_to_an_outsider(db, user, family, third_user):
    account = make_account(db, user, "My Private", Visibility.PRIVATE)
    with pytest.raises(NotFound):
        authz.get_viewable_account(db, account.id, authz.resolve(db, third_user))


def test_owner_keeps_full_rights_over_their_private_account(db, user, family):
    account = make_account(db, user, "My Private", Visibility.PRIVATE)
    mine = authz.resolve(db, user)
    assert authz.can_view(account, mine)
    assert authz.can_edit(account, mine)
    assert authz.can_transact(account, mine)


def test_private_accounts_never_appear_in_family_scope(db, user, other_user, family):
    make_account(db, user, "My Private", Visibility.PRIVATE)
    stmt = authz.visible_accounts(db, other_user, context="family")
    assert db.scalars(stmt).all() == []


# -------------------------------------------------------------- FAMILY_VISIBLE


def test_family_visible_can_be_read_by_a_member(db, user, other_user, family):
    account = make_account(db, user, "Salary", Visibility.FAMILY_VISIBLE)
    theirs = authz.resolve(db, other_user)
    assert authz.can_view(account, theirs) is True
    assert authz.get_viewable_account(db, account.id, theirs).id == account.id


def test_family_visible_cannot_be_written_by_a_member(db, user, other_user, family):
    """Visible is not writable. This is the distinction the whole model turns on."""
    account = make_account(db, user, "Salary", Visibility.FAMILY_VISIBLE)
    theirs = authz.resolve(db, other_user)

    assert authz.can_transact(account, theirs) is False
    assert authz.can_edit(account, theirs) is False
    with pytest.raises(PermissionDenied):
        authz.get_transactable_account(db, account.id, theirs)
    with pytest.raises(PermissionDenied):
        authz.get_editable_account(db, account.id, theirs)


def test_family_visible_is_invisible_to_an_outsider(db, user, family, third_user):
    account = make_account(db, user, "Salary", Visibility.FAMILY_VISIBLE)
    with pytest.raises(NotFound):
        authz.get_viewable_account(db, account.id, authz.resolve(db, third_user))


def test_owner_still_writes_to_their_family_visible_account(db, user, family):
    account = make_account(db, user, "Salary", Visibility.FAMILY_VISIBLE)
    assert authz.can_transact(account, authz.resolve(db, user)) is True


# ---------------------------------------------------------------------- SHARED


def test_shared_account_can_be_read_and_written_by_an_adult(db, user, other_user, family):
    account = make_account(db, user, "Household", Visibility.SHARED)
    theirs = authz.resolve(db, other_user)
    assert theirs.role is FamilyRole.ADULT
    assert authz.can_view(account, theirs) is True
    assert authz.can_transact(account, theirs) is True


def test_shared_account_is_read_only_for_a_member_role(db, user, other_user, family):
    """MEMBER is reserved for reduced-permission household members and is
    read-only for MVP."""
    account = make_account(db, user, "Household", Visibility.SHARED)
    set_member_role(
        db, user=user, family_id=family.id, member_user_id=other_user.id, role=FamilyRole.MEMBER
    )
    db.commit()

    theirs = authz.resolve(db, other_user)
    assert authz.can_view(account, theirs) is True
    assert authz.can_transact(account, theirs) is False


def test_shared_account_is_invisible_to_an_outsider(db, user, family, third_user):
    account = make_account(db, user, "Household", Visibility.SHARED)
    with pytest.raises(NotFound):
        authz.get_viewable_account(db, account.id, authz.resolve(db, third_user))


# ------------------------------------------------------------ leaving a family


def test_leaving_returns_shared_accounts_to_private(db, user, other_user, family):
    """Leaving must not leave your finances visible to the household."""
    from app.services.families import leave_family

    account = make_account(db, other_user, "Their Salary", Visibility.FAMILY_VISIBLE)
    assert authz.can_view(account, authz.resolve(db, user)) is True

    leave_family(db, user=other_user)
    db.commit()
    db.refresh(account)

    assert account.visibility is Visibility.PRIVATE
    assert account.family_id is None
    assert authz.can_view(account, authz.resolve(db, user)) is False


def test_removing_a_member_unshares_their_accounts(db, user, other_user, family):
    from app.services.families import remove_member

    account = make_account(db, other_user, "Their Salary", Visibility.SHARED)
    remove_member(db, user=user, family_id=family.id, member_user_id=other_user.id)
    db.commit()
    db.refresh(account)

    assert account.visibility is Visibility.PRIVATE
    assert authz.can_view(account, authz.resolve(db, user)) is False


# ------------------------------------------------------- child authorization


def test_transactions_resolve_through_their_account_not_their_author(db, user, other_user, family):
    """never authorize a transaction on created_by."""
    from app.services.posting import PostingService
    from app.services.transactions import get_transaction

    account = make_account(db, user, "My Private", Visibility.PRIVATE)
    txn = PostingService(db).record_expense(
        account=account,
        amount=Decimal("1000"),
        currency="RWF",
        occurred_at=NOW,
        actor_id=user.id,
    )
    db.commit()

    # The account is private, so the entry is too — regardless of who wrote it.
    with pytest.raises(NotFound):
        get_transaction(db, txn.id, other_user)


def test_family_visible_transactions_are_readable_by_a_member(db, user, other_user, family):
    from app.services.posting import PostingService
    from app.services.transactions import get_transaction

    account = make_account(db, user, "Salary", Visibility.FAMILY_VISIBLE)
    txn = PostingService(db).record_expense(
        account=account,
        amount=Decimal("1000"),
        currency="RWF",
        occurred_at=NOW,
        actor_id=user.id,
    )
    db.commit()
    assert get_transaction(db, txn.id, other_user).id == txn.id


# ------------------------------------------------------------------- scoping


def test_personal_scope_includes_own_accounts_and_shared_ones(db, user, other_user, family):
    """personal includes what you own whatever its
    visibility, plus the household's shared accounts, which are genuinely
    yours to use."""
    make_account(db, user, "Mine Private", Visibility.PRIVATE)
    make_account(db, user, "Mine Visible", Visibility.FAMILY_VISIBLE)
    make_account(db, other_user, "Theirs Private", Visibility.PRIVATE)
    make_account(db, other_user, "Theirs Visible", Visibility.FAMILY_VISIBLE)
    make_account(db, other_user, "Household", Visibility.SHARED)

    names = sorted(a.name for a in db.scalars(authz.visible_accounts(db, user)))
    assert names == ["Household", "Mine Private", "Mine Visible"]


def test_family_scope_excludes_private_whoever_owns_it(db, user, other_user, family):
    make_account(db, user, "Mine Private", Visibility.PRIVATE)
    make_account(db, user, "Mine Visible", Visibility.FAMILY_VISIBLE)
    make_account(db, other_user, "Theirs Private", Visibility.PRIVATE)
    make_account(db, other_user, "Household", Visibility.SHARED)

    names = sorted(a.name for a in db.scalars(authz.visible_accounts(db, user, context="family")))
    assert names == ["Household", "Mine Visible"]


def test_family_scope_is_empty_without_a_household(db, user):
    make_account(db, user, "Mine", Visibility.PRIVATE)
    assert db.scalars(authz.visible_accounts(db, user, context="family")).all() == []


def test_a_shared_account_appears_once_not_once_per_member(db, user, other_user, family):
    """aggregation must not double count."""
    make_account(db, user, "Household", Visibility.SHARED)
    rows = db.scalars(authz.visible_accounts(db, user, context="family")).all()
    assert len(rows) == 1
    rows = db.scalars(authz.visible_accounts(db, other_user, context="family")).all()
    assert len(rows) == 1


# ------------------------------------------------------------------ creation


def test_cannot_share_without_a_household(db, user):
    from app.core.errors import ValidationFailed

    with pytest.raises(ValidationFailed) as exc:
        make_account(db, user, "Nope", Visibility.FAMILY_VISIBLE)
    assert exc.value.code == "NO_ACTIVE_FAMILY"


def test_sharing_uses_your_own_household_not_one_you_name(db, user, family):
    """A client must not be able to attach a record to a household by naming
    its id; sharing is derived from the caller's own membership."""
    import uuid

    from app.core.errors import ValidationFailed

    with pytest.raises(ValidationFailed) as exc:
        make_account(db, user, "Nope", Visibility.SHARED, family_id=uuid.uuid4())
    assert exc.value.code == "NO_ACTIVE_FAMILY"


def test_private_creation_ignores_any_family_id_sent(db, user, family):
    """A private record belongs to no household, whatever the request said."""
    import uuid

    account = make_account(db, user, "Mine", Visibility.PRIVATE, family_id=uuid.uuid4())
    assert account.family_id is None
