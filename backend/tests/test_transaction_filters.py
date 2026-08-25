"""Finding a transaction again (Implementation Plan Phase 26).

The filters are only useful if they compose: a household member narrowing by
person and by month at once should get the intersection, not the union. And no
filter may widen what the visibility scope already decided.
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.db.enums import TransactionType, Visibility
from app.services import transactions as txn_service


def _txn(db, user, account, *, amount, when, description="", merchant=None, kind=None):
    return txn_service.create_transaction(
        db,
        user=user,
        account_id=account.id,
        transaction_type=kind or TransactionType.EXPENSE,
        amount=Decimal(amount),
        occurred_at=when,
        description=description,
        merchant=merchant,
    )


@pytest.fixture
def history(db, user, bank_account, savings_account):
    _txn(db, user, bank_account, amount="5000", when=datetime(2026, 3, 2, 9, tzinfo=UTC),
         description="Simba Supermarket", merchant="Simba")
    _txn(db, user, bank_account, amount="120000", when=datetime(2026, 3, 20, 9, tzinfo=UTC),
         description="Rent")
    _txn(db, user, savings_account, amount="45000", when=datetime(2026, 4, 5, 9, tzinfo=UTC),
         description="Simba fuel", merchant="Simba")
    _txn(db, user, bank_account, amount="900000", when=datetime(2026, 4, 25, 9, tzinfo=UTC),
         description="Salary", kind=TransactionType.INCOME)
    db.commit()


def _find(db, user, **kw):
    rows, _ = txn_service.list_transactions(db, user=user, **kw)
    return [t.description for t in rows]


# --------------------------------------------------------------- one at a time


def test_search_matches_description_and_merchant(db, user, history):
    assert sorted(_find(db, user, search="simba")) == ["Simba Supermarket", "Simba fuel"]


def test_search_ignores_surrounding_space(db, user, history):
    assert _find(db, user, search="  Rent  ") == ["Rent"]


def test_filtering_by_account_excludes_the_others(db, user, savings_account, history):
    assert _find(db, user, account_id=savings_account.id) == ["Simba fuel"]


def test_filtering_by_type_excludes_the_others(db, user, history):
    assert _find(db, user, transaction_type=TransactionType.INCOME) == ["Salary"]


def test_a_date_range_includes_both_ends(db, user, history):
    from datetime import date

    found = _find(db, user, date_from=date(2026, 3, 2), date_to=date(2026, 3, 20))
    assert sorted(found) == ["Rent", "Simba Supermarket"]


def test_an_amount_range_is_inclusive(db, user, history):
    # Both bounds land exactly on a transaction, and both are kept.
    found = _find(db, user, min_amount=Decimal("5000"), max_amount=Decimal("45000"))
    assert sorted(found) == ["Simba Supermarket", "Simba fuel"]


# ------------------------------------------------------------------ composition


def test_filters_intersect_rather_than_accumulate(db, user, bank_account, history):
    """Account and search together, not either one."""
    found = _find(db, user, account_id=bank_account.id, search="simba")
    assert found == ["Simba Supermarket"]


def test_a_filter_that_matches_nothing_returns_nothing(db, user, history):
    assert _find(db, user, search="nothing like this") == []


# ----------------------------------------------------------------------- owner


def test_owner_narrows_a_household_to_one_person(db, user, other_user, family, history):
    """A shared ledger is only readable if you can ask whose spending it was."""
    from app.services import accounts as account_service

    other_account = account_service.create_account(
        db,
        user=other_user,
        name="Her Current",
        account_type=bank_account_type(),
        currency="RWF",
        opening_balance=Decimal("100000"),
        opening_balance_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    account_service.set_visibility(
        db, account=other_account, user=other_user, visibility=Visibility.SHARED
    )
    _txn(db, other_user, other_account, amount="7000",
         when=datetime(2026, 4, 7, 9, tzinfo=UTC), description="Her groceries")
    db.commit()

    everyone = _find(db, user, context="family")
    assert "Her groceries" in everyone

    hers = _find(db, user, owner_id=other_user.id, context="family")
    assert hers == ["Her groceries"]


def test_owner_cannot_reach_what_is_private(db, user, other_user, family):
    """Asking for another member's transactions returns only what they shared."""
    from app.services import accounts as account_service

    private = account_service.create_account(
        db,
        user=other_user,
        name="Her Private",
        account_type=bank_account_type(),
        currency="RWF",
        opening_balance=Decimal("50000"),
        opening_balance_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    _txn(db, other_user, private, amount="3000",
         when=datetime(2026, 4, 8, 9, tzinfo=UTC), description="Her secret")
    db.commit()

    assert _find(db, user, owner_id=other_user.id, context="family") == []


def bank_account_type():
    from app.db.enums import AccountType

    return AccountType.CHECKING
