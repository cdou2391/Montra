"""The 30-day spending trend.

What the chart claims has to be true of the ledger: expenses only, bucketed by
the user's own days, with the quiet days present rather than collapsed away.
"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from app.db.enums import TransactionType, Visibility
from app.services import reporting
from app.services import transactions as txn_service
from app.services.posting import PostingService

TODAY = date(2026, 8, 25)


def _spend(db, user, account, *, amount, on: date, hour=12, description="Something"):
    return txn_service.create_transaction(
        db,
        user=user,
        account_id=account.id,
        transaction_type=TransactionType.EXPENSE,
        amount=Decimal(amount),
        occurred_at=datetime(on.year, on.month, on.day, hour, tzinfo=UTC),
        description=description,
    )


def _trend(db, user, **kw):
    return reporting.spending_trend(db, user=user, today=kw.pop("today", TODAY), **kw)


# ------------------------------------------------------------------- the window


def test_every_day_in_the_window_gets_a_point(db, user, bank_account):
    """A chart drawn only from the days with spending would space them evenly
    and misrepresent when the money went."""
    _spend(db, user, bank_account, amount="5000", on=TODAY)
    db.commit()
    trend = _trend(db, user)
    assert len(trend["points"]) == 30
    assert trend["points"][0]["date"] == "2026-07-27"
    assert trend["points"][-1]["date"] == TODAY.isoformat()


def test_a_quiet_day_reads_as_zero_not_as_missing(db, user, bank_account):
    _spend(db, user, bank_account, amount="5000", on=TODAY)
    db.commit()
    trend = _trend(db, user)
    assert trend["points"][0]["amount"] == "0.00"


def test_today_is_inside_the_window(db, user, bank_account):
    _spend(db, user, bank_account, amount="7000", on=TODAY)
    db.commit()
    trend = _trend(db, user)
    assert trend["points"][-1]["amount"] == "7000.00"


def test_spending_before_the_window_is_left_out(db, user, bank_account):
    _spend(db, user, bank_account, amount="999999", on=TODAY - timedelta(days=45))
    db.commit()
    assert _trend(db, user)["total"] == "0.00"


# ------------------------------------------------------------ what counts as spending


def test_a_transfer_is_not_spending(db, user, bank_account, savings_account):
    """Moving your own money is neither earning nor spending."""
    PostingService(db).transfer_funds(
        source=bank_account,
        destination=savings_account,
        source_amount=Decimal("80000"),
        destination_amount=Decimal("80000"),
        occurred_at=datetime(2026, 8, 20, 12, tzinfo=UTC),
        actor_id=user.id,
    )
    db.commit()
    assert _trend(db, user)["total"] == "0.00"


def test_income_is_not_spending(db, user, bank_account):
    txn_service.create_transaction(
        db,
        user=user,
        account_id=bank_account.id,
        transaction_type=TransactionType.INCOME,
        amount=Decimal("500000"),
        occurred_at=datetime(2026, 8, 20, 12, tzinfo=UTC),
    )
    db.commit()
    assert _trend(db, user)["total"] == "0.00"


def test_a_fee_counts_as_spending(db, user, bank_account):
    """It is money that left; it belongs in the total like any other expense."""
    txn_service.create_transaction(
        db,
        user=user,
        account_id=bank_account.id,
        transaction_type=TransactionType.EXPENSE,
        amount=Decimal("10000"),
        occurred_at=datetime(2026, 8, 20, 12, tzinfo=UTC),
        description="ATM withdrawal",
        fee_amount=Decimal("500"),
    )
    db.commit()
    assert _trend(db, user)["total"] == "10500.00"


def test_a_deleted_expense_stops_counting(db, user, bank_account):
    txn = _spend(db, user, bank_account, amount="6000", on=TODAY)
    db.commit()
    txn_service.delete_transaction(db, user=user, transaction_id=txn.id)
    db.commit()
    assert _trend(db, user)["total"] == "0.00"


def test_a_card_purchase_counts(db, user, credit_card):
    """Spending on credit is still spending, whatever it did to the balance."""
    _spend(db, user, credit_card, amount="45000", on=TODAY)
    db.commit()
    assert _trend(db, user)["total"] == "45000.00"


# ----------------------------------------------------------------- the summary


def test_the_total_is_the_sum_of_the_days(db, user, bank_account):
    for offset, amount in ((0, "5000"), (3, "12000"), (10, "8000")):
        _spend(db, user, bank_account, amount=amount, on=TODAY - timedelta(days=offset))
    db.commit()
    trend = _trend(db, user)
    assert trend["total"] == "25000.00"
    assert sum(Decimal(p["amount"]) for p in trend["points"]) == Decimal("25000.00")


def test_the_average_is_over_the_whole_window(db, user, bank_account):
    """"What does a day cost me" — the quiet days are part of the answer."""
    _spend(db, user, bank_account, amount="30000", on=TODAY)
    db.commit()
    assert _trend(db, user)["daily_average"] == "1000.00"


def test_the_busiest_day_is_reported(db, user, bank_account):
    _spend(db, user, bank_account, amount="5000", on=TODAY)
    _spend(db, user, bank_account, amount="40000", on=TODAY - timedelta(days=4))
    db.commit()
    busiest = _trend(db, user)["busiest_day"]
    assert busiest["date"] == (TODAY - timedelta(days=4)).isoformat()
    assert busiest["amount"] == "40000.00"


def test_a_window_with_no_spending_claims_no_busiest_day(db, user, bank_account):
    assert _trend(db, user)["busiest_day"] is None


def test_the_change_compares_with_the_window_before(db, user, bank_account):
    _spend(db, user, bank_account, amount="10000", on=TODAY - timedelta(days=40))
    _spend(db, user, bank_account, amount="15000", on=TODAY)
    db.commit()
    trend = _trend(db, user)
    assert trend["previous_total"] == "10000.00"
    assert trend["change_percentage"] == "50"


def test_no_comparison_when_there_is_nothing_to_compare_with(db, user, bank_account):
    """Dividing by an empty previous window would be an invented percentage."""
    _spend(db, user, bank_account, amount="15000", on=TODAY)
    db.commit()
    assert _trend(db, user)["change_percentage"] is None


# ------------------------------------------------------------------ visibility


def test_another_persons_private_spending_is_not_in_your_trend(
    db, user, other_user, family, bank_account
):
    from app.db.enums import AccountType
    from app.services import accounts as account_service

    private = account_service.create_account(
        db,
        user=other_user,
        name="Her Private",
        account_type=AccountType.CHECKING,
        currency="RWF",
        opening_balance=Decimal("100000"),
        opening_balance_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    _spend(db, other_user, private, amount="70000", on=TODAY)
    db.commit()
    assert _trend(db, user, context="family")["total"] == "0.00"


def test_shared_spending_shows_in_the_household_view(
    db, user, other_user, family, bank_account
):
    from app.db.enums import AccountType
    from app.services import accounts as account_service

    shared = account_service.create_account(
        db,
        user=other_user,
        name="Her Shared",
        account_type=AccountType.CHECKING,
        currency="RWF",
        opening_balance=Decimal("100000"),
        opening_balance_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    account_service.set_visibility(
        db, account=shared, user=other_user, visibility=Visibility.SHARED
    )
    _spend(db, other_user, shared, amount="70000", on=TODAY)
    db.commit()
    assert _trend(db, user, context="family")["total"] == "70000.00"
    # And in the personal view too: a shared account is genuinely theirs to
    # spend from, so its spending is theirs to see (Data Model sections 49-50).
    assert _trend(db, user, context="personal")["total"] == "70000.00"
