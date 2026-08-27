"""Cash-flow forecast.

The forecast projects what is already known — today's balances plus planned
items and loan instalments that have not happened yet. It never extrapolates
from past spending, so every figure here can be checked by hand.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.db.enums import PlannedType, Visibility
from app.services import forecast, planning
from tests.conftest import make_account


def _at(days_ahead: int) -> datetime:
    return datetime.now(UTC).replace(hour=9, minute=0, second=0, microsecond=0) + timedelta(
        days=days_ahead
    )


def _plan(db, user, account, kind, amount, days_ahead, **kw):
    return planning.create_planned(
        db,
        user=user,
        account_id=account.id,
        planned_type=kind,
        amount=Decimal(amount),
        expected_at=_at(days_ahead),
        description=kw.pop("description", "Planned"),
        **kw,
    )


# ------------------------------------------------------------------- the basics


def test_forecast_starts_from_todays_balance(db, user):
    make_account(db, user, "Bank", Visibility.PRIVATE, opening="500000")
    result = forecast.cash_flow(db, user=user, context="personal")
    assert result["starting_balance"] == "500000.00"
    assert result["projected_ending_balance"] == "500000.00"


def test_planned_income_and_expense_move_the_projection(db, user):
    account = make_account(db, user, "Bank", Visibility.PRIVATE, opening="500000")
    _plan(db, user, account, PlannedType.INCOME, "300000", 3)
    _plan(db, user, account, PlannedType.EXPENSE, "120000", 5)
    db.commit()

    result = forecast.cash_flow(db, user=user, context="personal")
    assert result["upcoming_income"] == "300000.00"
    assert result["upcoming_expenses"] == "120000.00"
    assert result["projected_ending_balance"] == "680000.00"
    assert result["net_change"] == "180000.00"


def test_items_beyond_the_period_are_not_counted(db, user):
    account = make_account(db, user, "Bank", Visibility.PRIVATE, opening="500000")
    _plan(db, user, account, PlannedType.EXPENSE, "400000", 3)
    _plan(db, user, account, PlannedType.EXPENSE, "999999", 20)
    db.commit()

    week = forecast.cash_flow(db, user=user, context="personal", period="7d")
    assert week["upcoming_expenses"] == "400000.00"
    month = forecast.cash_flow(db, user=user, context="personal", period="30d")
    assert month["upcoming_expenses"] == "1399999.00"


def test_cancelled_items_are_excluded(db, user):
    """a cancelled item never happens."""
    account = make_account(db, user, "Bank", Visibility.PRIVATE, opening="500000")
    planned = _plan(db, user, account, PlannedType.EXPENSE, "100000", 3)
    db.commit()
    planning.cancel_planned(db, user=user, planned_id=planned.id)
    db.commit()

    assert forecast.cash_flow(db, user=user, context="personal")["upcoming_expenses"] == "0.00"


def test_completed_items_are_not_counted_twice(db, user):
    """They are already inside the balance we started from."""
    account = make_account(db, user, "Bank", Visibility.PRIVATE, opening="500000")
    planned = _plan(db, user, account, PlannedType.EXPENSE, "100000", 1)
    db.commit()
    planning.complete_planned(db, user=user, planned_id=planned.id)
    db.commit()

    result = forecast.cash_flow(db, user=user, context="personal")
    assert result["starting_balance"] == "400000.00"
    assert result["upcoming_expenses"] == "0.00"


# --------------------------------------------------------- transfers are not flow


def test_an_internal_transfer_does_not_change_the_total(db, user):
    """moving money between two accounts you already count is
    movement, not cash flow."""
    a = make_account(db, user, "Bank", Visibility.PRIVATE, opening="500000")
    b = make_account(db, user, "Savings", Visibility.PRIVATE, opening="100000")
    planning.create_planned(
        db,
        user=user,
        account_id=a.id,
        destination_account_id=b.id,
        planned_type=PlannedType.TRANSFER,
        amount=Decimal("200000"),
        expected_at=_at(3),
        description="Move to savings",
    )
    db.commit()

    result = forecast.cash_flow(db, user=user, context="personal")
    assert result["starting_balance"] == "600000.00"
    assert result["projected_ending_balance"] == "600000.00"
    # Counted as neither, rather than as both.
    assert result["upcoming_income"] == "0.00"
    assert result["upcoming_expenses"] == "0.00"


def test_an_internal_transfer_still_moves_a_single_account(db, user):
    """The total is unchanged, but the source can still run dry."""
    a = make_account(db, user, "Bank", Visibility.PRIVATE, opening="100000")
    b = make_account(db, user, "Savings", Visibility.PRIVATE, opening="500000")
    planning.create_planned(
        db,
        user=user,
        account_id=a.id,
        destination_account_id=b.id,
        planned_type=PlannedType.TRANSFER,
        amount=Decimal("150000"),
        expected_at=_at(3),
        description="Too much",
    )
    db.commit()

    result = forecast.cash_flow(db, user=user, context="personal")
    assert result["projected_ending_balance"] == "600000.00"
    assert len(result["warnings"]) == 1
    assert result["warnings"][0]["account_name"] == "Bank"


# ------------------------------------------------------------------- warnings


def test_a_projected_shortfall_is_warned_about(db, user):
    account = make_account(db, user, "Bank", Visibility.PRIVATE, opening="100000")
    _plan(db, user, account, PlannedType.EXPENSE, "150000", 4, description="Rent")
    db.commit()

    result = forecast.cash_flow(db, user=user, context="personal")
    assert len(result["warnings"]) == 1
    warning = result["warnings"][0]
    assert warning["account_name"] == "Bank"
    assert warning["projected_balance"] == "-50000.00"
    assert "below zero" in warning["message"]


def test_a_healthy_account_produces_no_warning(db, user):
    account = make_account(db, user, "Bank", Visibility.PRIVATE, opening="500000")
    _plan(db, user, account, PlannedType.EXPENSE, "100000", 4)
    db.commit()
    assert forecast.cash_flow(db, user=user, context="personal")["warnings"] == []


def test_only_the_first_dip_is_reported_per_account(db, user):
    """One warning per account, not one per day it stays negative."""
    account = make_account(db, user, "Bank", Visibility.PRIVATE, opening="50000")
    _plan(db, user, account, PlannedType.EXPENSE, "100000", 3)
    _plan(db, user, account, PlannedType.EXPENSE, "100000", 6)
    db.commit()
    assert len(forecast.cash_flow(db, user=user, context="personal")["warnings"]) == 1


# --------------------------------------------------------------------- points


def test_points_cover_every_day_of_the_period(db, user):
    make_account(db, user, "Bank", Visibility.PRIVATE, opening="500000")
    week = forecast.cash_flow(db, user=user, context="personal", period="7d")
    assert len(week["points"]) == 8  # today through day seven
    month = forecast.cash_flow(db, user=user, context="personal", period="30d")
    assert len(month["points"]) == 31


def test_the_last_point_matches_the_ending_balance(db, user):
    account = make_account(db, user, "Bank", Visibility.PRIVATE, opening="500000")
    _plan(db, user, account, PlannedType.EXPENSE, "120000", 5)
    db.commit()
    result = forecast.cash_flow(db, user=user, context="personal")
    assert result["points"][-1]["projected_balance"] == result["projected_ending_balance"]


# ---------------------------------------------------------------- family scope


def test_family_forecast_excludes_private_items(db, user, other_user, family):
    """private financial events are not household cash flow."""
    visible = make_account(db, user, "Salary", Visibility.FAMILY_VISIBLE, opening="300000")
    secret = make_account(db, other_user, "Secret", Visibility.PRIVATE, opening="900000")
    _plan(db, user, visible, PlannedType.EXPENSE, "50000", 3)
    _plan(db, other_user, secret, PlannedType.EXPENSE, "700000", 3)
    db.commit()

    result = forecast.cash_flow(db, user=user, context="family")
    assert result["starting_balance"] == "300000.00"
    assert result["upcoming_expenses"] == "50000.00"


def test_a_family_visible_to_shared_transfer_is_not_household_cash_flow(
    db, user, other_user, family
):
    """In household scope."""
    a = make_account(db, user, "Salary", Visibility.FAMILY_VISIBLE, opening="400000")
    b = make_account(db, user, "Household", Visibility.SHARED, opening="200000")
    planning.create_planned(
        db,
        user=user,
        account_id=a.id,
        destination_account_id=b.id,
        planned_type=PlannedType.TRANSFER,
        amount=Decimal("100000"),
        expected_at=_at(3),
        description="Housekeeping",
    )
    db.commit()

    result = forecast.cash_flow(db, user=user, context="family")
    assert result["starting_balance"] == "600000.00"
    assert result["projected_ending_balance"] == "600000.00"
    assert result["upcoming_expenses"] == "0.00"


def test_family_forecast_without_a_household_is_empty(db, user):
    make_account(db, user, "Bank", Visibility.PRIVATE, opening="500000")
    result = forecast.cash_flow(db, user=user, context="family")
    assert result["starting_balance"] == "0.00"


# ------------------------------------------------------------------- accounts


def test_a_credit_card_balance_is_not_cash(db, user):
    from app.db.enums import AccountType

    make_account(db, user, "Bank", Visibility.PRIVATE, opening="500000")
    make_account(
        db,
        user,
        "Card",
        Visibility.PRIVATE,
        opening="200000",
        account_type=AccountType.CREDIT_CARD,
    )
    # Debt is not spendable money, so it does not appear in the starting cash.
    assert forecast.cash_flow(db, user=user, context="personal")["starting_balance"] == (
        "500000.00"
    )


def test_a_single_account_can_be_forecast_on_its_own(db, user):
    a = make_account(db, user, "Bank", Visibility.PRIVATE, opening="500000")
    make_account(db, user, "Savings", Visibility.PRIVATE, opening="900000")
    result = forecast.cash_flow(db, user=user, context="personal", account_id=a.id)
    assert result["starting_balance"] == "500000.00"
