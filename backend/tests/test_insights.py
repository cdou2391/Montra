"""Deterministic insights.

Every figure is arithmetic over the caller's authorized scope, so each of these
can be checked by hand. The tests care as much about silence as about output:
an insight that fires on every account every month is furniture, not
information.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.db.enums import AccountType, Frequency, PlannedType, Visibility
from app.services import insights, planning
from app.services.posting import PostingService
from tests.conftest import make_account


def _now() -> datetime:
    return datetime.now(UTC).replace(hour=12, minute=0, second=0, microsecond=0)


def _last_month() -> datetime:
    now = _now()
    first = now.replace(day=1)
    return (first - timedelta(days=1)).replace(hour=12, minute=0, second=0, microsecond=0)


def _spend(db, user, account, amount, when, category=None):
    PostingService(db).record_expense(
        account=account,
        amount=Decimal(amount),
        currency="RWF",
        occurred_at=when,
        actor_id=user.id,
        category_id=category.id if category else None,
        description="Spending",
    )


def _category(db, user, name):
    from sqlalchemy import select

    from app.models.finance import Category

    return db.scalar(select(Category).where(Category.user_id == user.id, Category.name == name))


def _codes(rows):
    return [r["code"] for r in rows]


# ---------------------------------------------------------------- nothing to say


def test_no_accounts_means_no_insights(db, user):
    assert insights.generate(db, user=user) == []


def test_a_quiet_account_produces_nothing_alarming(db, user):
    make_account(db, user, "Bank", Visibility.PRIVATE, opening="500000")
    rows = insights.generate(db, user=user)
    assert "projected_shortfall" not in _codes(rows)
    assert "credit_utilization" not in _codes(rows)


# -------------------------------------------------------------- spending shift


def test_a_large_category_increase_is_reported(db, user):
    account = make_account(db, user, "Bank", Visibility.PRIVATE, opening="5000000")
    food = _category(db, user, "Food")
    _spend(db, user, account, "50000", _last_month(), food)
    _spend(db, user, account, "100000", _now(), food)
    db.commit()

    rows = insights.generate(db, user=user)
    shift = next(r for r in rows if r["code"] == "spending_shift")
    assert shift["category"] == "Food"
    assert shift["change_percent"] == "100.0"
    assert shift["tone"] == "warning"


def test_a_decrease_reads_as_good_news(db, user):
    account = make_account(db, user, "Bank", Visibility.PRIVATE, opening="5000000")
    food = _category(db, user, "Food")
    _spend(db, user, account, "100000", _last_month(), food)
    _spend(db, user, account, "50000", _now(), food)
    db.commit()

    shift = next(r for r in insights.generate(db, user=user) if r["code"] == "spending_shift")
    assert shift["tone"] == "positive"
    assert "less" in shift["title"]


def test_a_small_change_is_not_worth_saying(db, user):
    """Below the threshold it is noise, so nothing is said at all."""
    account = make_account(db, user, "Bank", Visibility.PRIVATE, opening="5000000")
    food = _category(db, user, "Food")
    _spend(db, user, account, "100000", _last_month(), food)
    _spend(db, user, account, "105000", _now(), food)
    db.commit()

    assert "spending_shift" not in _codes(insights.generate(db, user=user))


def test_a_brand_new_category_is_not_a_percentage_change(db, user):
    """Dividing by last month's zero would be meaningless, not infinite."""
    account = make_account(db, user, "Bank", Visibility.PRIVATE, opening="5000000")
    _spend(db, user, account, "100000", _now(), _category(db, user, "Food"))
    db.commit()
    assert "spending_shift" not in _codes(insights.generate(db, user=user))


# ---------------------------------------------------------------- savings rate


def test_savings_rate_is_reported(db, user):
    account = make_account(db, user, "Bank", Visibility.PRIVATE, opening="0")
    posting = PostingService(db)
    posting.record_income(
        account=account,
        amount=Decimal("1000000"),
        currency="RWF",
        occurred_at=_now(),
        actor_id=user.id,
    )
    posting.record_expense(
        account=account,
        amount=Decimal("250000"),
        currency="RWF",
        occurred_at=_now(),
        actor_id=user.id,
    )
    db.commit()

    rate = next(r for r in insights.generate(db, user=user) if r["code"] == "savings_rate")
    assert rate["value"] == "75.00"
    assert rate["tone"] == "positive"


def test_a_poor_savings_rate_reads_as_a_warning(db, user):
    account = make_account(db, user, "Bank", Visibility.PRIVATE, opening="0")
    posting = PostingService(db)
    posting.record_income(
        account=account,
        amount=Decimal("100000"),
        currency="RWF",
        occurred_at=_now(),
        actor_id=user.id,
    )
    posting.record_expense(
        account=account,
        amount=Decimal("98000"),
        currency="RWF",
        occurred_at=_now(),
        actor_id=user.id,
    )
    db.commit()

    rate = next(r for r in insights.generate(db, user=user) if r["code"] == "savings_rate")
    assert rate["tone"] == "warning"


def test_no_income_means_no_savings_rate(db, user):
    """A rate with nothing to divide by is not zero, it is undefined."""
    account = make_account(db, user, "Bank", Visibility.PRIVATE, opening="500000")
    _spend(db, user, account, "10000", _now())
    db.commit()
    assert "savings_rate" not in _codes(insights.generate(db, user=user))


# ------------------------------------------------------------------- recurring


def test_recurring_commitments_are_totalled_per_month(db, user):
    account = make_account(db, user, "Bank", Visibility.PRIVATE, opening="500000")
    for name, amount, freq in (
        ("Netflix", "15000", Frequency.MONTHLY),
        ("Rent", "300000", Frequency.MONTHLY),
        ("Insurance", "120000", Frequency.YEARLY),
    ):
        planning.create_rule(
            db,
            user=user,
            account_id=account.id,
            planned_type=PlannedType.EXPENSE,
            amount=Decimal(amount),
            name=name,
            frequency=freq,
            start_date=_now().date(),
        )
    db.commit()

    row = next(r for r in insights.generate(db, user=user) if r["code"] == "recurring_total")
    assert row["count"] == 3
    # Yearly is spread across the months rather than counted whole.
    assert Decimal(row["value"]) < Decimal("330000")
    assert Decimal(row["value"]) > Decimal("320000")


def test_income_rules_are_not_commitments(db, user):
    account = make_account(db, user, "Bank", Visibility.PRIVATE, opening="500000")
    planning.create_rule(
        db,
        user=user,
        account_id=account.id,
        planned_type=PlannedType.INCOME,
        amount=Decimal("2000000"),
        name="Salary",
        frequency=Frequency.MONTHLY,
        start_date=_now().date(),
    )
    db.commit()
    assert "recurring_total" not in _codes(insights.generate(db, user=user))


# ------------------------------------------------------------- card utilization


def test_high_card_utilization_is_reported(db, user):
    card = make_account(
        db,
        user,
        "Visa",
        Visibility.PRIVATE,
        opening="600000",
        account_type=AccountType.CREDIT_CARD,
    )
    card.credit_limit = Decimal("1000000")
    db.commit()

    row = next(r for r in insights.generate(db, user=user) if r["code"] == "credit_utilization")
    assert row["value"] == "60.0"
    assert row["tone"] == "warning"


def test_very_high_utilization_reads_as_worse(db, user):
    card = make_account(
        db,
        user,
        "Visa",
        Visibility.PRIVATE,
        opening="900000",
        account_type=AccountType.CREDIT_CARD,
    )
    card.credit_limit = Decimal("1000000")
    db.commit()
    row = next(r for r in insights.generate(db, user=user) if r["code"] == "credit_utilization")
    assert row["tone"] == "negative"


def test_comfortable_utilization_is_not_mentioned(db, user):
    card = make_account(
        db,
        user,
        "Visa",
        Visibility.PRIVATE,
        opening="100000",
        account_type=AccountType.CREDIT_CARD,
    )
    card.credit_limit = Decimal("1000000")
    db.commit()
    assert "credit_utilization" not in _codes(insights.generate(db, user=user))


def test_a_card_without_a_limit_cannot_have_a_utilization(db, user):
    make_account(
        db,
        user,
        "Visa",
        Visibility.PRIVATE,
        opening="900000",
        account_type=AccountType.CREDIT_CARD,
    )
    db.commit()
    assert "credit_utilization" not in _codes(insights.generate(db, user=user))


# --------------------------------------------------------------------- ordering


def test_problems_are_listed_before_pleasantries(db, user):
    """A projected shortfall matters more than a healthy savings rate."""
    account = make_account(db, user, "Bank", Visibility.PRIVATE, opening="100000")
    posting = PostingService(db)
    posting.record_income(
        account=account,
        amount=Decimal("500000"),
        currency="RWF",
        occurred_at=_now(),
        actor_id=user.id,
    )
    planning.create_planned(
        db,
        user=user,
        account_id=account.id,
        planned_type=PlannedType.EXPENSE,
        amount=Decimal("900000"),
        expected_at=_now() + timedelta(days=4),
        description="Rent",
    )
    db.commit()

    rows = insights.generate(db, user=user)
    tones = [r["tone"] for r in rows]
    assert tones == sorted(
        tones, key=lambda t: {"negative": 0, "warning": 1, "neutral": 2, "positive": 3}[t]
    )
    assert rows[0]["code"] == "projected_shortfall"


# ------------------------------------------------------------------ family scope


def test_family_insights_never_see_private_spending(db, user, other_user, family):
    visible = make_account(db, user, "Salary", Visibility.FAMILY_VISIBLE, opening="1000000")
    secret = make_account(db, other_user, "Secret", Visibility.PRIVATE, opening="1000000")
    food = _category(db, user, "Food")
    _spend(db, user, visible, "50000", _last_month(), food)
    _spend(db, user, visible, "60000", _now(), food)
    _spend(db, other_user, secret, "900000", _now())
    db.commit()

    rows = insights.generate(db, user=user, context="family")
    blob = str(rows)
    assert "900000" not in blob
