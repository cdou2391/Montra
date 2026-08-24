"""Favourite account.

Purely a user preference: it is stored against the user, and nothing is written
to the account row. Marking an account as the household's account is a separate
idea that will arrive with the Family phases.
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.errors import NotFound
from app.db.enums import AccountType
from app.models.user import UserPreference
from app.services import accounts as account_service
from app.services.accounts import create_account

NOW = datetime(2026, 8, 24, 12, 0, tzinfo=UTC)


def _account(db, user, name):
    a = create_account(
        db,
        user=user,
        name=name,
        account_type=AccountType.CHECKING,
        currency="RWF",
        opening_balance=Decimal("1000"),
        opening_balance_at=NOW,
    )
    db.commit()
    return a


def test_accounts_are_alphabetical_without_a_favorite(db, user):
    _account(db, user, "Zebra")
    _account(db, user, "Alpha")
    _account(db, user, "Middle")
    assert [a.name for a in account_service.list_accounts(db, user=user)] == [
        "Alpha",
        "Middle",
        "Zebra",
    ]


def test_favorite_leads_the_list(db, user):
    _account(db, user, "Alpha")
    _account(db, user, "Middle")
    zebra = _account(db, user, "Zebra")

    account_service.set_favorite_account(db, user=user, account_id=zebra.id)
    db.commit()

    # Last alphabetically, first in the list.
    assert [a.name for a in account_service.list_accounts(db, user=user)] == [
        "Zebra",
        "Alpha",
        "Middle",
    ]


def test_the_rest_stay_alphabetical_behind_the_favorite(db, user):
    _account(db, user, "Charlie")
    _account(db, user, "Alpha")
    bravo = _account(db, user, "Bravo")
    account_service.set_favorite_account(db, user=user, account_id=bravo.id)
    db.commit()
    assert [a.name for a in account_service.list_accounts(db, user=user)] == [
        "Bravo",
        "Alpha",
        "Charlie",
    ]


def test_there_is_only_ever_one_favorite(db, user):
    first = _account(db, user, "Alpha")
    second = _account(db, user, "Bravo")

    account_service.set_favorite_account(db, user=user, account_id=first.id)
    db.commit()
    account_service.set_favorite_account(db, user=user, account_id=second.id)
    db.commit()

    # "First" only means something for one account.
    assert account_service.favorite_account_id(db, user) == second.id


def test_favorite_can_be_cleared(db, user):
    account = _account(db, user, "Alpha")
    account_service.set_favorite_account(db, user=user, account_id=account.id)
    db.commit()
    account_service.set_favorite_account(db, user=user, account_id=None)
    db.commit()
    assert account_service.favorite_account_id(db, user) is None


def test_cannot_favorite_an_account_you_cannot_see(db, user, other_user):
    theirs = _account(db, other_user, "Theirs")
    with pytest.raises(NotFound):
        account_service.set_favorite_account(db, user=user, account_id=theirs.id)


def test_each_user_has_their_own_favorite(db, user, other_user):
    """It is the user's choice, not a property of the account."""
    mine = _account(db, user, "Mine")
    theirs = _account(db, other_user, "Theirs")

    account_service.set_favorite_account(db, user=user, account_id=mine.id)
    account_service.set_favorite_account(db, user=other_user, account_id=theirs.id)
    db.commit()

    assert account_service.favorite_account_id(db, user) == mine.id
    assert account_service.favorite_account_id(db, other_user) == theirs.id


def test_deleting_the_account_clears_the_favorite(db, user):
    from app.models.finance import Account

    account = _account(db, user, "Alpha")
    account_service.set_favorite_account(db, user=user, account_id=account.id)
    db.commit()

    db.execute(Account.__table__.delete().where(Account.id == account.id))
    db.commit()

    prefs = db.scalar(select(UserPreference).where(UserPreference.user_id == user.id))
    # ON DELETE SET NULL, so no dangling reference is left behind.
    assert prefs.favorite_account_id is None


def test_serialized_account_reports_whether_it_is_the_favorite(db, user):
    alpha = _account(db, user, "Alpha")
    _account(db, user, "Bravo")
    account_service.set_favorite_account(db, user=user, account_id=alpha.id)
    db.commit()

    rows = account_service.list_accounts(db, user=user)
    payload = [account_service.serialize_account(db, a, user) for a in rows]
    assert payload[0]["is_favorite"] is True
    assert payload[1]["is_favorite"] is False


def test_backup_round_trip_keeps_the_favorite(db, user):
    """The exported id no longer exists after a restore, so it must be
    remapped rather than written back."""
    from app.services import backup

    _account(db, user, "Alpha")
    zebra = _account(db, user, "Zebra")
    account_service.set_favorite_account(db, user=user, account_id=zebra.id)
    db.commit()

    payload = backup.export_backup(db, user)
    db.commit()
    backup.restore_backup(db, user=user, payload=payload, password="correct horse battery")
    db.commit()

    restored = account_service.list_accounts(db, user=user)
    assert restored[0].name == "Zebra"
    assert account_service.favorite_account_id(db, user) == restored[0].id


def test_reset_clears_the_favorite(db, user):
    from app.services import profile

    account = _account(db, user, "Alpha")
    account_service.set_favorite_account(db, user=user, account_id=account.id)
    db.commit()

    profile.reset_profile(db, user=user, password="correct horse battery")
    db.commit()
    assert account_service.favorite_account_id(db, user) is None
