"""Deterministic insights.

Every figure is arithmetic over the caller's authorized scope, so each of these
can be checked by hand. The tests care as much about silence as about output:
an insight that fires on every account every month is furniture, not
information.
"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from app.db.enums import AccountType, Frequency, PlannedType, Visibility
from app.services import budgets as budget_service
from app.services import goals as goal_service
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


# ------------------------------------------------- what a commitment includes


def _recurring_insight(db, user):
    from app.services.insights import generate

    return next(
        (i for i in generate(db, user=user) if i["code"] == "recurring_total"), None
    )


def test_a_loan_instalment_is_a_recurring_payment(db, user, bank_account):
    """The figure claims to be what leaves "before anything else", and a loan
    instalment is exactly that. It does not appear as a recurring rule, so
    counting only the rules left it out."""
    from datetime import date
    from decimal import Decimal

    from app.db.enums import Frequency, LoanDirection
    from app.services.loans import create_loan

    create_loan(
        db,
        user=user,
        direction=LoanDirection.PAYABLE,
        name="Car",
        currency="RWF",
        original_principal=Decimal("2000000"),
        opening_outstanding_principal=Decimal("2000000"),
        start_date=date(2026, 8, 1),
        expected_payment_amount=Decimal("187344"),
        payment_frequency=Frequency.MONTHLY,
    )
    db.commit()

    insight = _recurring_insight(db, user)
    assert insight is not None
    assert insight["value"] == "187344.00"
    assert "1 loan instalment" in insight["detail"]


def test_money_owed_to_you_is_not_a_payment_you_make(db, user, bank_account):
    from datetime import date
    from decimal import Decimal

    from app.db.enums import Frequency, LoanDirection
    from app.services.loans import create_loan

    create_loan(
        db,
        user=user,
        direction=LoanDirection.RECEIVABLE,
        name="Lent to a friend",
        currency="RWF",
        original_principal=Decimal("500000"),
        opening_outstanding_principal=Decimal("500000"),
        start_date=date(2026, 8, 1),
        expected_payment_amount=Decimal("100000"),
        payment_frequency=Frequency.MONTHLY,
    )
    db.commit()

    assert _recurring_insight(db, user) is None


def test_rules_and_instalments_are_added_together(db, user, bank_account):
    from datetime import date
    from decimal import Decimal

    from app.db.enums import Frequency, LoanDirection, PlannedType
    from app.services import planning as planning_service
    from app.services.loans import create_loan

    planning_service.create_rule(
        db,
        user=user,
        name="Streaming",
        planned_type=PlannedType.EXPENSE,
        account_id=bank_account.id,
        amount=Decimal("15500"),
        frequency=Frequency.MONTHLY,
        start_date=date(2026, 8, 1),
    )
    create_loan(
        db,
        user=user,
        direction=LoanDirection.PAYABLE,
        name="Personal",
        currency="RWF",
        original_principal=Decimal("5000000"),
        opening_outstanding_principal=Decimal("5000000"),
        start_date=date(2026, 8, 1),
        expected_payment_amount=Decimal("569669"),
        payment_frequency=Frequency.MONTHLY,
    )
    db.commit()

    insight = _recurring_insight(db, user)
    assert insight["value"] == "585169.00"   # 15,500 + 569,669
    assert insight["count"] == 2


def test_a_foreign_subscription_is_converted_first(db, user, bank_account):
    """It used to add the raw number, so a ten dollar subscription counted as
    ten francs."""
    from datetime import UTC, date, datetime
    from decimal import Decimal

    from app.db.enums import AccountType, Frequency, PlannedType, Visibility
    from app.services import planning as planning_service
    from app.services.accounts import create_account
    from app.services.currency import set_rate

    set_rate(db, user=user, base_currency="USD", quote_currency="RWF", rate=Decimal("1400"))
    usd = create_account(
        db,
        user=user,
        name="Dollars",
        account_type=AccountType.CHECKING,
        currency="USD",
        opening_balance=Decimal("500"),
        opening_balance_at=datetime(2026, 8, 1, 9, 0, tzinfo=UTC),
        visibility=Visibility.PRIVATE,
    )
    planning_service.create_rule(
        db,
        user=user,
        name="A dollar subscription",
        planned_type=PlannedType.EXPENSE,
        account_id=usd.id,
        amount=Decimal("10"),
        frequency=Frequency.MONTHLY,
        start_date=date(2026, 8, 1),
    )
    db.commit()

    assert _recurring_insight(db, user)["value"] == "14000.00"


def test_a_settled_loan_stops_counting(db, user, bank_account):
    from datetime import date
    from decimal import Decimal

    from app.db.enums import Frequency, LoanDirection, LoanStatus
    from app.services.loans import create_loan

    loan = create_loan(
        db,
        user=user,
        direction=LoanDirection.PAYABLE,
        name="Nearly done",
        currency="RWF",
        original_principal=Decimal("100000"),
        opening_outstanding_principal=Decimal("100000"),
        start_date=date(2026, 8, 1),
        expected_payment_amount=Decimal("50000"),
        payment_frequency=Frequency.MONTHLY,
    )
    db.commit()
    assert _recurring_insight(db, user) is not None

    loan.status = LoanStatus.SETTLED
    db.commit()
    assert _recurring_insight(db, user) is None


# ------------------------------------------------- budgets and goals
#
# These pin a date instead of using today's. Both the budget projection and the
# goal pace turn on how much of the month has gone, so a suite run on the 3rd
# and one run on the 28th would otherwise disagree with each other.

PINNED = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)
PINNED_TODAY = PINNED.date()


def _budget(db, user, category, amount):
    return budget_service.create_budget(
        db, user=user, category_id=category.id, amount=Decimal(amount)
    )


def _income(db, user, account, amount, when):
    PostingService(db).record_income(
        account=account,
        amount=Decimal(amount),
        currency="RWF",
        occurred_at=when,
        actor_id=user.id,
    )


def test_a_budget_that_is_over_is_reported(db, user):
    account = make_account(db, user, "Bank", Visibility.PRIVATE, opening="5000000")
    food = _category(db, user, "Food")
    _budget(db, user, food, "100000")
    _spend(db, user, account, "150000", PINNED, food)
    db.commit()

    rows = insights.generate(db, user=user, today=PINNED_TODAY)
    row = next(r for r in rows if r["code"] == "budget_pressure")
    assert row["tone"] == "negative"
    assert row["category"] == "Food"
    assert "over budget" in row["title"]


def test_a_budget_with_room_left_says_nothing(db, user):
    """Under the limit and not heading past it, a budget is furniture."""
    account = make_account(db, user, "Bank", Visibility.PRIVATE, opening="5000000")
    food = _category(db, user, "Food")
    _budget(db, user, food, "100000")
    _spend(db, user, account, "20000", PINNED, food)
    db.commit()

    assert "budget_pressure" not in _codes(insights.generate(db, user=user, today=PINNED_TODAY))


def test_only_the_worst_budget_is_named(db, user):
    """One row, however many are over. The rest are counted, not listed."""
    account = make_account(db, user, "Bank", Visibility.PRIVATE, opening="5000000")
    food = _category(db, user, "Food")
    transport = _category(db, user, "Transport")
    _budget(db, user, food, "100000")
    _budget(db, user, transport, "50000")
    _spend(db, user, account, "150000", PINNED, food)
    _spend(db, user, account, "120000", PINNED, transport)
    db.commit()

    rows = [
        r
        for r in insights.generate(db, user=user, today=PINNED_TODAY)
        if r["code"] == "budget_pressure"
    ]
    assert len(rows) == 1
    assert rows[0]["category"] == "Transport"  # 70,000 over beats 50,000 over
    assert "1 other budget is over too" in rows[0]["detail"]


def test_a_budget_on_pace_to_go_over_is_a_warning(db, user):
    """Still inside the limit, but not for long: the version you can act on."""
    account = make_account(db, user, "Bank", Visibility.PRIVATE, opening="5000000")
    food = _category(db, user, "Food")
    _budget(db, user, food, "100000")
    _spend(db, user, account, "60000", PINNED, food)
    db.commit()

    row = next(
        r
        for r in insights.generate(db, user=user, today=PINNED_TODAY)
        if r["code"] == "budget_pressure"
    )
    assert row["tone"] == "warning"
    assert "on pace" in row["title"]


def test_a_pace_is_not_guessed_at_in_the_first_days(db, user):
    """Two days in, one large shop is not a trend worth announcing."""
    account = make_account(db, user, "Bank", Visibility.PRIVATE, opening="5000000")
    food = _category(db, user, "Food")
    _budget(db, user, food, "100000")
    _spend(db, user, account, "60000", datetime(2026, 8, 2, 12, 0, tzinfo=UTC), food)
    db.commit()

    early = insights.generate(db, user=user, today=date(2026, 8, 3))
    assert "budget_pressure" not in _codes(early)


def test_a_goal_past_its_date_is_reported(db, user):
    pot = make_account(
        db, user, "Savings", Visibility.PRIVATE, opening="0", account_type=AccountType.SAVINGS
    )
    goal_service.create_goal(
        db,
        user=user,
        name="Laptop",
        account=pot,
        target_amount=Decimal("500000"),
        target_date=date(2026, 7, 31),
    )
    db.commit()

    row = next(
        r for r in insights.generate(db, user=user, today=PINNED_TODAY) if r["code"] == "goal_pace"
    )
    assert row["tone"] == "negative"
    assert "passed its date" in row["title"]


def test_a_goal_you_are_keeping_up_with_says_nothing(db, user):
    account = make_account(db, user, "Bank", Visibility.PRIVATE, opening="0")
    pot = make_account(
        db, user, "Savings", Visibility.PRIVATE, opening="0", account_type=AccountType.SAVINGS
    )
    _income(db, user, account, "1000000", PINNED)
    goal_service.create_goal(
        db,
        user=user,
        name="Laptop",
        account=pot,
        target_amount=Decimal("500000"),
        target_date=date(2026, 12, 31),
    )
    db.commit()

    # 125,000 a month against 1,000,000 saved: nothing to say.
    assert "goal_pace" not in _codes(insights.generate(db, user=user, today=PINNED_TODAY))


def test_a_goal_needing_more_than_you_save_is_a_warning(db, user):
    account = make_account(db, user, "Bank", Visibility.PRIVATE, opening="0")
    pot = make_account(
        db, user, "Savings", Visibility.PRIVATE, opening="0", account_type=AccountType.SAVINGS
    )
    _income(db, user, account, "1000000", PINNED)
    _spend(db, user, account, "900000", PINNED)
    goal_service.create_goal(
        db,
        user=user,
        name="Deposit",
        account=pot,
        target_amount=Decimal("5000000"),
        target_date=date(2026, 12, 31),
    )
    db.commit()

    row = next(
        r for r in insights.generate(db, user=user, today=PINNED_TODAY) if r["code"] == "goal_pace"
    )
    assert row["tone"] == "warning"
    assert "Deposit" in row["title"]


def test_a_goal_without_a_date_cannot_be_behind(db, user):
    """No date, no pace: there is nothing to be late for."""
    account = make_account(db, user, "Bank", Visibility.PRIVATE, opening="0")
    pot = make_account(
        db, user, "Savings", Visibility.PRIVATE, opening="0", account_type=AccountType.SAVINGS
    )
    _income(db, user, account, "1000000", PINNED)
    _spend(db, user, account, "900000", PINNED)
    goal_service.create_goal(
        db, user=user, name="Someday", account=pot, target_amount=Decimal("5000000")
    )
    db.commit()

    assert "goal_pace" not in _codes(insights.generate(db, user=user, today=PINNED_TODAY))


def test_a_budget_row_replaces_the_shift_for_that_category(db, user):
    """Two rows about Food would be one of news and one of noise.

    The budget row is the sharper of the two, so the shift steps over that
    category and reports the next largest instead of repeating it.
    """
    account = make_account(db, user, "Bank", Visibility.PRIVATE, opening="2000000")
    food = _category(db, user, "Food")
    transport = _category(db, user, "Transport")
    _budget(db, user, food, "120000")
    _spend(db, user, account, "60000", datetime(2026, 7, 20, 12, 0, tzinfo=UTC), food)
    _spend(db, user, account, "175400", PINNED, food)
    _spend(db, user, account, "40000", datetime(2026, 7, 20, 12, 0, tzinfo=UTC), transport)
    _spend(db, user, account, "84000", PINNED, transport)
    db.commit()

    rows = insights.generate(db, user=user, today=PINNED_TODAY)
    assert next(r for r in rows if r["code"] == "budget_pressure")["category"] == "Food"
    assert next(r for r in rows if r["code"] == "spending_shift")["category"] == "Transport"


def test_a_budgeted_category_is_the_only_one_that_moved(db, user):
    """Nothing left to fall through to, so the shift says nothing at all."""
    account = make_account(db, user, "Bank", Visibility.PRIVATE, opening="2000000")
    food = _category(db, user, "Food")
    _budget(db, user, food, "120000")
    _spend(db, user, account, "60000", datetime(2026, 7, 20, 12, 0, tzinfo=UTC), food)
    _spend(db, user, account, "175400", PINNED, food)
    db.commit()

    assert "spending_shift" not in _codes(insights.generate(db, user=user, today=PINNED_TODAY))
