"""Editing an account's details.

Everything here is metadata rather than money: it moves no balance and writes
no transaction. The exception is currency, which cannot change once the
account has history — every amount already recorded is denominated in the old
one, and reinterpreting them silently would rewrite the past.
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.core.errors import Conflict
from app.db.enums import AccountType, TransactionType
from app.services import accounts as account_service
from app.services import transactions as txn_service

NOW = datetime(2026, 8, 25, 12, 0, tzinfo=UTC)


@pytest.fixture
def fresh_account(db, user):
    """An account nothing has been recorded against yet."""
    account = account_service.create_account(
        db,
        user=user,
        name="New Wallet",
        account_type=AccountType.MOBILE_MONEY,
        currency="RWF",
        opening_balance=Decimal("0"),
        opening_balance_at=NOW,
    )
    db.commit()
    return account


# ------------------------------------------------------------------- metadata


def test_the_name_can_change(db, user, bank_account):
    account_service.update_account(db, account=bank_account, name="Main Current")
    db.commit()
    assert bank_account.name == "Main Current"


def test_a_name_is_trimmed(db, user, bank_account):
    account_service.update_account(db, account=bank_account, name="  Padded  ")
    db.commit()
    assert bank_account.name == "Padded"


def test_a_description_can_be_added(db, user, bank_account):
    account_service.update_account(db, account=bank_account, description="Salary lands here")
    db.commit()
    assert bank_account.description == "Salary lands here"


def test_the_identifier_can_change(db, user, bank_account):
    account_service.update_account(db, account=bank_account, account_identifier="99887766")
    db.commit()
    payload = account_service.serialize_account(db, bank_account, user)
    # Only the tail is ever shown, whatever was stored.
    assert payload["masked_identifier"].endswith("7766")


def test_editing_details_moves_no_money(db, user, bank_account):
    """The whole point: this form never touches the ledger."""
    from app.services.posting import PostingService

    before = PostingService(db).balance_of(bank_account)
    account_service.update_account(
        db, account=bank_account, name="Renamed", description="Note"
    )
    db.commit()
    assert PostingService(db).balance_of(bank_account) == before


# ------------------------------------------------------------------- currency


def test_currency_can_change_before_anything_is_recorded(db, user, fresh_account):
    account_service.update_account(db, account=fresh_account, currency="USD")
    db.commit()
    assert fresh_account.currency == "USD"


def test_a_lowercase_currency_is_stored_uppercase(db, user, fresh_account):
    account_service.update_account(db, account=fresh_account, currency="eur")
    db.commit()
    assert fresh_account.currency == "EUR"


def test_currency_is_fixed_once_there_is_history(db, user, fresh_account):
    """Every amount recorded is already in the old currency; changing it would
    reinterpret the past rather than describe the present."""
    txn_service.create_transaction(
        db,
        user=user,
        account_id=fresh_account.id,
        transaction_type=TransactionType.EXPENSE,
        amount=Decimal("5000"),
        occurred_at=NOW,
        description="Something",
    )
    db.commit()

    with pytest.raises(Conflict) as exc:
        account_service.update_account(db, account=fresh_account, currency="USD")
    assert exc.value.code == "ACCOUNT_CURRENCY_IMMUTABLE"
    assert fresh_account.currency == "RWF"


def test_resubmitting_the_same_currency_is_not_a_change(db, user, bank_account):
    """The form sends every field, so saving a name must not trip the guard."""
    account_service.update_account(
        db, account=bank_account, name="Still Fine", currency=bank_account.currency
    )
    db.commit()
    assert bank_account.name == "Still Fine"


# --------------------------------------------------------------- the payload


def test_the_detail_view_says_whether_there_is_history(db, user, fresh_account):
    """So the form can explain why currency is locked instead of failing."""
    payload = account_service.serialize_account(db, fresh_account, user, include_activity=True)
    assert payload["has_activity"] is False

    txn_service.create_transaction(
        db,
        user=user,
        account_id=fresh_account.id,
        transaction_type=TransactionType.EXPENSE,
        amount=Decimal("100"),
        occurred_at=NOW,
    )
    db.commit()
    payload = account_service.serialize_account(db, fresh_account, user, include_activity=True)
    assert payload["has_activity"] is True


def test_a_listing_does_not_pay_for_that_query(db, user, bank_account):
    """It is one query per account, and a list of twenty has no use for it."""
    payload = account_service.serialize_account(db, bank_account, user)
    assert "has_activity" not in payload
