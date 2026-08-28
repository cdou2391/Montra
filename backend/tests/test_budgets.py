"""Budgets.

A budget holds no money. Everything it reports is derived from the ledger, so
these tests are mostly about what counts as spending against one — and what
deliberately does not.
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.core.errors import Conflict, NotFound, ValidationFailed
from app.db.enums import AccountType, CategoryType, TransactionType, Visibility
from app.models.finance import Category
from app.services import budgets as budget_service
from app.services import transactions as txn_service
from tests.conftest import make_account

NOW = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)
TODAY = NOW.date()


def _category(db, user, name: str) -> Category:
    """One of the categories every account starts with.

    Created rather than fetched would collide: registration already gives a
    user the default set, and (user, name, type) is unique.
    """
    from sqlalchemy import select

    return db.scalar(
        select(Category).where(
            Category.user_id == user.id,
            Category.name == name,
            Category.category_type == CategoryType.EXPENSE,
        )
    )


@pytest.fixture
def food(db, user) -> Category:
    return _category(db, user, "Food")


@pytest.fixture
def travel(db, user) -> Category:
    return _category(db, user, "Transport")


def _spend(db, user, account, category, amount, when=NOW):
    txn_service.create_transaction(
        db,
        user=user,
        account_id=account.id,
        transaction_type=TransactionType.EXPENSE,
        amount=Decimal(amount),
        occurred_at=when,
        category_id=category.id if category else None,
    )
    db.commit()


def _foreign_account(db, user, name: str, code: str):
    """make_account is RWF-only; a budget in francs needs a non-franc charge."""
    from app.services.accounts import create_account

    account = create_account(
        db,
        user=user,
        name=name,
        account_type=AccountType.CHECKING,
        currency=code,
        opening_balance=Decimal("1000"),
        opening_balance_at=datetime(2026, 8, 1, 9, 0, tzinfo=UTC),
    )
    db.commit()
    return account


def _status(db, user):
    return budget_service.status(db, user=user, today=TODAY)


def _row(payload, name="Food"):
    return next(b for b in payload["budgets"] if b["category"]["name"] == name)


# ------------------------------------------------------------------ counting


def test_spending_in_the_category_counts(db, user, food):
    account = make_account(db, user, "Bank", Visibility.PRIVATE, opening="1000000")
    budget_service.create_budget(db, user=user, category_id=food.id, amount=Decimal("100000"))
    db.commit()
    _spend(db, user, account, food, "30000")

    row = _row(_status(db, user))
    assert row["spent"] == "30000.00"
    assert row["remaining"] == "70000.00"
    assert row["state"] == "UNDER"


def test_another_category_does_not(db, user, food, travel):
    account = make_account(db, user, "Bank", Visibility.PRIVATE, opening="1000000")
    budget_service.create_budget(db, user=user, category_id=food.id, amount=Decimal("100000"))
    db.commit()
    _spend(db, user, account, travel, "80000")

    assert _row(_status(db, user))["spent"] == "0.00"


def test_income_is_not_spending(db, user, food):
    account = make_account(db, user, "Bank", Visibility.PRIVATE, opening="1000000")
    budget_service.create_budget(db, user=user, category_id=food.id, amount=Decimal("100000"))
    db.commit()
    txn_service.create_transaction(
        db,
        user=user,
        account_id=account.id,
        transaction_type=TransactionType.INCOME,
        amount=Decimal("50000"),
        occurred_at=NOW,
        category_id=food.id,
    )
    db.commit()

    assert _row(_status(db, user))["spent"] == "0.00"


def test_a_transfer_is_not_spending(db, user, food):
    """Moving your own money is neither earning nor spending — the same rule
    the month's totals use."""
    source = make_account(db, user, "Bank", Visibility.PRIVATE, opening="1000000")
    destination = make_account(db, user, "Savings", Visibility.PRIVATE, opening="0")
    budget_service.create_budget(db, user=user, category_id=food.id, amount=Decimal("100000"))
    db.commit()

    from app.services.posting import PostingService

    PostingService(db).transfer_funds(
        source=source,
        destination=destination,
        source_amount=Decimal("90000"),
        destination_amount=Decimal("90000"),
        occurred_at=NOW,
        actor_id=user.id,
    )
    db.commit()

    assert _row(_status(db, user))["spent"] == "0.00"


def test_last_month_does_not_count_against_this_one(db, user, food):
    """Each period stands alone; nothing carries."""
    account = make_account(db, user, "Bank", Visibility.PRIVATE, opening="1000000")
    budget_service.create_budget(db, user=user, category_id=food.id, amount=Decimal("100000"))
    db.commit()
    _spend(db, user, account, food, "70000", when=datetime(2026, 7, 20, 12, 0, tzinfo=UTC))
    _spend(db, user, account, food, "10000")

    assert _row(_status(db, user))["spent"] == "10000.00"


def test_an_excluded_account_still_spends(db, user, food):
    """The exclusion flag is about the balance sheet. The money still left."""
    account = make_account(
        db, user, "Float", Visibility.PRIVATE, opening="500000", excluded_from_totals=True
    )
    budget_service.create_budget(db, user=user, category_id=food.id, amount=Decimal("100000"))
    db.commit()
    _spend(db, user, account, food, "40000")

    assert _row(_status(db, user))["spent"] == "40000.00"


def test_a_cancelled_transaction_stops_counting(db, user, food):
    account = make_account(db, user, "Bank", Visibility.PRIVATE, opening="1000000")
    budget_service.create_budget(db, user=user, category_id=food.id, amount=Decimal("100000"))
    db.commit()
    txn = txn_service.create_transaction(
        db,
        user=user,
        account_id=account.id,
        transaction_type=TransactionType.EXPENSE,
        amount=Decimal("30000"),
        occurred_at=NOW,
        category_id=food.id,
    )
    db.commit()
    assert _row(_status(db, user))["spent"] == "30000.00"

    txn_service.delete_transaction(db, user=user, transaction_id=txn.id)
    db.commit()
    assert _row(_status(db, user))["spent"] == "0.00"


# --------------------------------------------------------------------- state


def test_over_the_limit_says_so_and_goes_negative(db, user, food):
    """"How far past" is the number people want, not "zero left"."""
    account = make_account(db, user, "Bank", Visibility.PRIVATE, opening="1000000")
    budget_service.create_budget(db, user=user, category_id=food.id, amount=Decimal("100000"))
    db.commit()
    _spend(db, user, account, food, "130000")

    row = _row(_status(db, user))
    assert row["state"] == "OVER"
    assert row["remaining"] == "-30000.00"
    assert row["used_percent"] == "130.0"


def test_near_the_limit_is_its_own_state(db, user, food):
    account = make_account(db, user, "Bank", Visibility.PRIVATE, opening="1000000")
    budget_service.create_budget(db, user=user, category_id=food.id, amount=Decimal("100000"))
    db.commit()
    _spend(db, user, account, food, "85000")

    assert _row(_status(db, user))["state"] == "NEAR"


def test_the_projection_reads_the_pace(db, user, food):
    """Half way through a 31-day month, 50,000 spent projects to about 100,000.

    A budget that only reports after the fact is a receipt; this is the part
    that can still be acted on.
    """
    account = make_account(db, user, "Bank", Visibility.PRIVATE, opening="1000000")
    budget_service.create_budget(db, user=user, category_id=food.id, amount=Decimal("200000"))
    db.commit()
    _spend(db, user, account, food, "50000")

    # 14 days elapsed of 31: 50000 / 14 * 31.
    assert _row(_status(db, user))["projected"] == "110714.29"


# ------------------------------------------------------------------ currency


def test_a_foreign_charge_is_converted_before_it_is_compared(db, user, food):
    """A dollar charge against a franc budget is not one franc."""
    from app.services.currency import set_rate

    set_rate(db, user=user, base_currency="USD", quote_currency="RWF", rate=Decimal("1400"))
    account = _foreign_account(db, user, "USD", "USD")
    budget_service.create_budget(db, user=user, category_id=food.id, amount=Decimal("100000"))
    db.commit()
    _spend(db, user, account, food, "50")

    assert _row(_status(db, user))["spent"] == "70000.00"


def test_an_unconvertible_charge_is_named_not_guessed(db, user, food):
    account = _foreign_account(db, user, "Yen", "JPY")
    budget_service.create_budget(db, user=user, category_id=food.id, amount=Decimal("100000"))
    db.commit()
    _spend(db, user, account, food, "500")

    payload = _status(db, user)
    assert payload["unconverted_currencies"] == ["JPY"]
    assert _row(payload)["spent"] == "0.00"


# ------------------------------------------------------------------ lifecycle


def test_one_live_budget_per_category(db, user, food):
    budget_service.create_budget(db, user=user, category_id=food.id, amount=Decimal("100000"))
    db.commit()
    with pytest.raises(Conflict):
        budget_service.create_budget(db, user=user, category_id=food.id, amount=Decimal("50000"))


def test_archiving_frees_the_category(db, user, food):
    first = budget_service.create_budget(
        db, user=user, category_id=food.id, amount=Decimal("100000")
    )
    db.commit()
    budget_service.archive_budget(db, first)
    db.commit()

    second = budget_service.create_budget(
        db, user=user, category_id=food.id, amount=Decimal("50000")
    )
    db.commit()
    assert second.id != first.id
    assert len(_status(db, user)["budgets"]) == 1


def test_an_income_category_cannot_have_a_budget(db, user):
    from sqlalchemy import select

    salary = db.scalar(
        select(Category).where(
            Category.user_id == user.id, Category.category_type == CategoryType.INCOME
        )
    )
    with pytest.raises(ValidationFailed):
        budget_service.create_budget(db, user=user, category_id=salary.id, amount=Decimal("1"))


def test_a_budget_must_be_more_than_zero(db, user, food):
    with pytest.raises(ValidationFailed):
        budget_service.create_budget(db, user=user, category_id=food.id, amount=Decimal("0"))


def test_someone_elses_budget_is_not_found(db, user, other_user, food):
    budget = budget_service.create_budget(
        db, user=user, category_id=food.id, amount=Decimal("100000")
    )
    db.commit()
    # 404 rather than 403: the API never confirms it exists.
    with pytest.raises(NotFound):
        budget_service.get_budget(db, budget.id, other_user)


def test_budgets_are_private_to_their_owner(db, user, other_user, food):
    budget_service.create_budget(db, user=user, category_id=food.id, amount=Decimal("100000"))
    db.commit()
    assert _status(db, other_user)["budgets"] == []


def test_no_budgets_is_an_empty_answer_not_an_error(db, user):
    payload = _status(db, user)
    assert payload["budgets"] == []
    assert payload["totals"] is None


def test_the_over_ones_come_first(db, user, food, travel):
    account = make_account(db, user, "Bank", Visibility.PRIVATE, opening="1000000")
    budget_service.create_budget(db, user=user, category_id=food.id, amount=Decimal("100000"))
    budget_service.create_budget(db, user=user, category_id=travel.id, amount=Decimal("100000"))
    db.commit()
    _spend(db, user, account, travel, "150000")

    names = [b["category"]["name"] for b in _status(db, user)["budgets"]]
    assert names[0] == "Transport"


# ------------------------------------------------------------------ household


def test_a_shared_budget_is_visible_to_the_household(db, user, other_user, family, food):
    budget_service.create_budget(
        db,
        user=user,
        category_id=food.id,
        amount=Decimal("100000"),
        visibility=Visibility.SHARED,
    )
    db.commit()

    seen = budget_service.status(db, user=other_user, context="family", today=TODAY)
    assert [b["category"]["name"] for b in seen["budgets"]] == ["Food"]


def test_a_family_visible_budget_is_visible_to_the_household(db, user, other_user, family, food):
    budget_service.create_budget(
        db,
        user=user,
        category_id=food.id,
        amount=Decimal("100000"),
        visibility=Visibility.FAMILY_VISIBLE,
    )
    db.commit()

    seen = budget_service.status(db, user=other_user, context="family", today=TODAY)
    assert len(seen["budgets"]) == 1


def test_a_private_budget_stays_out_of_the_household_view(db, user, other_user, family, food):
    """The rule the accounts follow: private is excluded before the total is
    built, not filtered out of it afterwards."""
    budget_service.create_budget(db, user=user, category_id=food.id, amount=Decimal("100000"))
    db.commit()

    seen = budget_service.status(db, user=other_user, context="family", today=TODAY)
    assert seen["budgets"] == []


def test_someone_outside_the_household_sees_nothing(db, user, third_user, family, food):
    budget_service.create_budget(
        db,
        user=user,
        category_id=food.id,
        amount=Decimal("100000"),
        visibility=Visibility.SHARED,
    )
    db.commit()

    seen = budget_service.status(db, user=third_user, context="family", today=TODAY)
    assert seen["budgets"] == []


def test_sharing_without_a_household_is_refused(db, user, food):
    """Sharing is derived from the caller's own membership, so there is nothing
    to share into until they have one."""
    with pytest.raises(ValidationFailed):
        budget_service.create_budget(
            db,
            user=user,
            category_id=food.id,
            amount=Decimal("100000"),
            visibility=Visibility.SHARED,
        )


def test_the_household_view_is_empty_without_a_household(db, user, food):
    budget_service.create_budget(db, user=user, category_id=food.id, amount=Decimal("100000"))
    db.commit()
    # Not an error, simply empty.
    assert budget_service.status(db, user=user, context="family", today=TODAY)["budgets"] == []
