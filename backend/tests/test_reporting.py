"""Dashboard and net worth (Implementation Plan Phases 22-23).

Two properties matter more than the arithmetic:

    Private data is excluded before aggregation, not filtered afterwards.
    A shared account counts once, not once per member.
"""

from datetime import UTC, date, datetime
from decimal import Decimal

from app.db.enums import AccountType, LoanDirection, Visibility
from app.services import reporting
from app.services.posting import PostingService
from tests.conftest import make_account

NOW = datetime(2026, 8, 24, 12, 0, tzinfo=UTC)


# -------------------------------------------------------------- personal view


def test_personal_net_worth_is_assets_minus_liabilities(db, user):
    make_account(db, user, "Bank", Visibility.PRIVATE, opening="1000000")
    make_account(
        db,
        user,
        "Card",
        Visibility.PRIVATE,
        opening="200000",
        account_type=AccountType.CREDIT_CARD,
    )
    payload = reporting.net_worth(db, user=user, context="personal")
    assert payload["assets"] == "1000000.00"
    assert payload["liabilities"] == "200000.00"
    assert payload["net_worth"] == "800000.00"


def test_personal_net_worth_includes_loans_both_ways(db, user):
    from app.services.loans import create_loan

    make_account(db, user, "Bank", Visibility.PRIVATE, opening="500000")
    create_loan(
        db,
        user=user,
        name="Car Loan",
        direction=LoanDirection.PAYABLE,
        currency="RWF",
        original_principal=Decimal("300000"),
        opening_outstanding_principal=Decimal("300000"),
        start_date=date(2026, 1, 1),
    )
    create_loan(
        db,
        user=user,
        name="To Jean",
        direction=LoanDirection.RECEIVABLE,
        currency="RWF",
        original_principal=Decimal("100000"),
        opening_outstanding_principal=Decimal("100000"),
        start_date=date(2026, 1, 1),
    )
    db.commit()

    payload = reporting.net_worth(db, user=user, context="personal")
    # Owed to you is an asset; owed by you is a liability.
    assert payload["assets"] == "600000.00"
    assert payload["liabilities"] == "300000.00"


def test_personal_shows_shared_separately_rather_than_splitting_it(db, user, other_user, family):
    """Data Model section 49: never attribute half a household balance to each
    member — that is a guess presented as a number."""
    make_account(db, user, "Mine", Visibility.PRIVATE, opening="1000000")
    make_account(db, user, "Household", Visibility.SHARED, opening="600000")

    payload = reporting.net_worth(db, user=user, context="personal")
    assert payload["net_worth"] == "1000000.00"
    assert payload["shared"]["assets"] == "600000.00"
    # Not 300,000.
    assert "300000" not in payload["shared"]["assets"]


def test_personal_has_no_shared_block_without_a_household(db, user):
    make_account(db, user, "Mine", Visibility.PRIVATE, opening="1000")
    assert reporting.net_worth(db, user=user, context="personal")["shared"] is None


# ---------------------------------------------------------------- family view


def test_family_net_worth_includes_visible_and_shared(db, user, other_user, family):
    make_account(db, user, "My Salary", Visibility.FAMILY_VISIBLE, opening="800000")
    make_account(db, other_user, "Their Salary", Visibility.FAMILY_VISIBLE, opening="500000")
    make_account(db, user, "Household", Visibility.SHARED, opening="200000")

    payload = reporting.net_worth(db, user=user, context="family")
    assert payload["assets"] == "1500000.00"


def test_family_net_worth_excludes_private_accounts(db, user, other_user, family):
    """Phase 22: private data excluded before aggregation."""
    make_account(db, user, "My Salary", Visibility.FAMILY_VISIBLE, opening="800000")
    make_account(db, other_user, "Their Secret", Visibility.PRIVATE, opening="9000000")

    payload = reporting.net_worth(db, user=user, context="family")
    assert payload["assets"] == "800000.00"
    assert payload["account_count"] == 1


def test_a_shared_account_counts_once_not_once_per_member(db, user, other_user, family):
    """Data Model section 51."""
    make_account(db, user, "Household", Visibility.SHARED, opening="600000")

    for viewer in (user, other_user):
        payload = reporting.net_worth(db, user=viewer, context="family")
        assert payload["assets"] == "600000.00"
        assert payload["account_count"] == 1


def test_family_view_without_a_household_is_empty_not_an_error(db, user):
    payload = reporting.net_worth(db, user=user, context="family")
    assert payload["assets"] == "0.00"
    assert payload["account_count"] == 0


# ---------------------------------------------------------------- month flows


def test_month_flows_exclude_transfers_and_adjustments(db, user):
    """Data Model section 52: moving your own money is neither earning nor
    spending."""
    a = make_account(db, user, "Bank", Visibility.PRIVATE, opening="1000000")
    b = make_account(db, user, "Savings", Visibility.PRIVATE, opening="0")
    posting = PostingService(db)
    posting.record_income(
        account=a, amount=Decimal("500000"), currency="RWF", occurred_at=NOW, actor_id=user.id
    )
    posting.record_expense(
        account=a, amount=Decimal("120000"), currency="RWF", occurred_at=NOW, actor_id=user.id
    )
    posting.transfer_funds(
        source=a,
        destination=b,
        source_amount=Decimal("300000"),
        destination_amount=Decimal("300000"),
        occurred_at=NOW,
        actor_id=user.id,
    )
    posting.adjust_balance(
        account=a, actual_balance=Decimal("999999"), occurred_at=NOW, actor_id=user.id
    )
    db.commit()

    from app.services import authz

    flows = reporting.month_flows(
        db,
        user=user,
        access=authz.resolve(db, user),
        context="personal",
        today=date(2026, 8, 24),
    )
    assert flows["income"] == "500000.00"
    assert flows["expense"] == "120000.00"
    assert flows["saved"] == "380000.00"
    assert flows["savings_rate"] == "76.00"


def test_family_month_flows_exclude_private_activity(db, user, other_user, family):
    visible = make_account(db, user, "Salary", Visibility.FAMILY_VISIBLE, opening="0")
    secret = make_account(db, other_user, "Secret", Visibility.PRIVATE, opening="0")
    posting = PostingService(db)
    posting.record_income(
        account=visible,
        amount=Decimal("100000"),
        currency="RWF",
        occurred_at=NOW,
        actor_id=user.id,
    )
    posting.record_income(
        account=secret,
        amount=Decimal("900000"),
        currency="RWF",
        occurred_at=NOW,
        actor_id=other_user.id,
    )
    db.commit()

    from app.services import authz

    flows = reporting.month_flows(
        db,
        user=user,
        access=authz.resolve(db, user),
        context="family",
        today=date(2026, 8, 24),
    )
    assert flows["income"] == "100000.00"


# ----------------------------------------------------------------- dashboard


def test_dashboard_carries_the_whole_picture(db, user):
    make_account(db, user, "Bank", Visibility.PRIVATE, opening="1000000")
    payload = reporting.dashboard(db, user=user, context="personal")
    for key in ("net_worth", "month", "upcoming", "recent", "loans"):
        assert key in payload
    assert payload["context"] == "personal"


def test_family_dashboard_without_a_household_says_so(db, user):
    payload = reporting.dashboard(db, user=user, context="family")
    assert payload["in_family"] is False
    assert payload["net_worth"] is None


def test_family_dashboard_recent_activity_excludes_private(db, user, other_user, family):
    visible = make_account(db, user, "Salary", Visibility.FAMILY_VISIBLE, opening="0")
    secret = make_account(db, other_user, "Secret", Visibility.PRIVATE, opening="0")
    posting = PostingService(db)
    posting.record_expense(
        account=visible,
        amount=Decimal("1000"),
        currency="RWF",
        occurred_at=NOW,
        actor_id=user.id,
        description="Shared groceries",
    )
    posting.record_expense(
        account=secret,
        amount=Decimal("5000"),
        currency="RWF",
        occurred_at=NOW,
        actor_id=other_user.id,
        description="Secret purchase",
    )
    db.commit()

    payload = reporting.dashboard(db, user=user, context="family")
    descriptions = [t["description"] for t in payload["recent"]]
    assert "Shared groceries" in descriptions
    assert "Secret purchase" not in descriptions
