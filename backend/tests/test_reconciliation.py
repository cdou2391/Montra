"""Reconciliation: whole scenarios against numbers worked out by hand.

Every other suite asserts one behaviour in isolation. These play a realistic
sequence of events through the real services and then check every figure the
app reports — balances, assets, liabilities, income, expense, net worth —
against arithmetic written out in the test.

That distinction is not academic. The bugs this file exists to catch are the
ones that only appear when features meet: a backup that dropped a recurring
transfer's destination, a reset that a goal blocked. Both passed 717 isolated
tests and failed the first time anything exercised them together.

Each scenario shows its own arithmetic, so a reader can check the expected
numbers without running anything.
"""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.db.enums import AccountType, CategoryType, TransactionType, Visibility
from app.models.finance import Category
from app.services import reporting
from app.services import transactions as txn_service
from app.services.posting import PostingService
from tests.conftest import make_account

# Mid-month, so a month's totals include everything below and the opening
# balances (1 August) sit before the window rather than inside it.
NOW = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)
TODAY = NOW.date()


def _category(db, user, name):
    return db.scalar(
        select(Category).where(
            Category.user_id == user.id,
            Category.name == name,
            Category.category_type == CategoryType.EXPENSE,
        )
    )


def _spend(db, user, account, amount, category=None, when=NOW, fee=None):
    return txn_service.create_transaction(
        db,
        user=user,
        account_id=account.id,
        transaction_type=TransactionType.EXPENSE,
        amount=Decimal(amount),
        occurred_at=when,
        category_id=category.id if category else None,
        description="Expense",
        fee_amount=Decimal(fee) if fee else None,
    )


def _earn(db, user, account, amount, when=NOW):
    return txn_service.create_transaction(
        db,
        user=user,
        account_id=account.id,
        transaction_type=TransactionType.INCOME,
        amount=Decimal(amount),
        occurred_at=when,
        description="Income",
    )


def _move(db, user, source, destination, amount, when=NOW):
    return PostingService(db).transfer_funds(
        source=source,
        destination=destination,
        source_amount=Decimal(amount),
        destination_amount=Decimal(amount),
        occurred_at=when,
        actor_id=user.id,
    )


def _figures(db, user):
    """Every number the app reports, in one place."""
    from app.services import authz

    access = authz.resolve(db, user)
    position = reporting.net_worth(db, user=user, context="personal")
    month = reporting.month_flows(
        db, user=user, access=access, context="personal", today=TODAY
    )
    return {
        "assets": position["assets"],
        "liabilities": position["liabilities"],
        "net_worth": position["net_worth"],
        "income": month["income"],
        "expense": month["expense"],
    }


def _balance(db, account) -> Decimal:
    return PostingService(db).balance_of(account)


# --------------------------------------------------------------- the plan's


@pytest.fixture
def books(db, user):
    """The three accounts the scenario below opens with."""
    checking = make_account(db, user, "Cash", Visibility.PRIVATE, opening="5000000")
    savings = make_account(
        db, user, "Savings", Visibility.PRIVATE, opening="0", account_type=AccountType.SAVINGS
    )
    card = make_account(
        db, user, "Card", Visibility.PRIVATE, opening="0", account_type=AccountType.CREDIT_CARD
    )
    return checking, savings, card


def test_the_reference_scenario(db, user, books):
    """The sequence the plan sets out, with its numbers.

        Opening cash          5,000,000
        Salary               +2,500,000
        Groceries              -100,000
        Transfer to savings    -500,000
        Credit purchase         200,000 debt
        Credit repayment        100,000

    Cash      5,000,000 + 2,500,000 - 100,000 - 500,000 - 100,000 = 6,800,000
    Savings                                          0 + 500,000 =   500,000
    Card                              200,000 debt - 100,000 paid =   100,000

    Assets            6,800,000 + 500,000 = 7,300,000
    Liabilities                               100,000
    Net worth       7,300,000 - 100,000   = 7,200,000

    Income                                  2,500,000
    Expense       groceries 100,000 + card purchase 200,000 = 300,000
                  — the two transfers are neither.
    """
    from app.services import credit_cards

    checking, savings, card = books

    _earn(db, user, checking, "2500000")
    _spend(db, user, checking, "100000", _category(db, user, "Groceries"))
    _move(db, user, checking, savings, "500000")
    _spend(db, user, card, "200000", _category(db, user, "Shopping"))
    credit_cards.pay_card(
        db, user=user, card=card, source=checking, amount=Decimal("100000"), occurred_at=NOW
    )
    db.commit()

    assert _balance(db, checking) == Decimal("6800000")
    assert _balance(db, savings) == Decimal("500000")
    assert _balance(db, card) == Decimal("100000")

    assert _figures(db, user) == {
        "assets": "7300000.00",
        "liabilities": "100000.00",
        "net_worth": "7200000.00",
        "income": "2500000.00",
        "expense": "300000.00",
    }


def test_a_card_repayment_moves_no_net_worth(db, user, books):
    """The property the posting engine exists to guarantee: paying a card
    decreases both sides, so the difference between them does not move."""
    from app.services import credit_cards

    checking, _, card = books
    _spend(db, user, card, "200000")
    db.commit()
    before = _figures(db, user)["net_worth"]

    credit_cards.pay_card(
        db, user=user, card=card, source=checking, amount=Decimal("150000"), occurred_at=NOW
    )
    db.commit()

    after = _figures(db, user)
    assert after["net_worth"] == before
    # Both fell by the payment, rather than one of them.
    assert after["assets"] == "4850000.00"
    assert after["liabilities"] == "50000.00"


def test_a_transfer_moves_no_net_worth_and_is_not_spending(db, user, books):
    checking, savings, _ = books
    before = _figures(db, user)

    _move(db, user, checking, savings, "1200000")
    db.commit()

    after = _figures(db, user)
    assert after["net_worth"] == before["net_worth"] == "5000000.00"
    assert after["income"] == "0.00"
    assert after["expense"] == "0.00"


# ------------------------------------------------------------------- fees


def test_a_fee_is_its_own_line_and_its_own_money(db, user, books):
    """A 50,000 purchase with a 1,000 charge costs 51,000 and shows as two
    entries, so a reconciliation against a statement matches line for line.

    Cash      5,000,000 - 50,000 - 1,000 = 4,949,000
    Expense                50,000 + 1,000 =    51,000
    """
    checking, _, _ = books
    _spend(db, user, checking, "50000", _category(db, user, "Shopping"), fee="1000")
    db.commit()

    assert _balance(db, checking) == Decimal("4949000")
    figures = _figures(db, user)
    assert figures["expense"] == "51000.00"
    assert figures["assets"] == "4949000.00"

    rows, _ = txn_service.list_transactions(db, user=user, limit=20)
    assert len(rows) == 2, "the fee is a line of its own, not folded into the purchase"


# ------------------------------------------------------------------- loans


def test_a_loan_payment_splits_three_ways(db, user, books):
    """Cash moves by the total; only interest and fees are spending.

        Payment 120,000 = principal 100,000 + interest 15,000 + fee 5,000

    Cash        5,000,000 - 120,000 = 4,880,000
    Loan owed     800,000 - 100,000 =   700,000
    Expense        15,000 +   5,000 =    20,000   (principal is not spending)

    Liabilities are the loan alone, since no card is used here.
    """
    from app.db.enums import LoanDirection
    from app.services.loans import create_loan, record_payment

    checking, _, _ = books
    loan = create_loan(
        db,
        user=user,
        direction=LoanDirection.PAYABLE,
        name="Car",
        currency="RWF",
        original_principal=Decimal("800000"),
        opening_outstanding_principal=Decimal("800000"),
        start_date=date(2026, 8, 1),
    )
    db.commit()

    record_payment(
        db,
        user=user,
        loan=loan,
        account_id=checking.id,
        total_amount=Decimal("120000"),
        principal_amount=Decimal("100000"),
        interest_amount=Decimal("15000"),
        fee_amount=Decimal("5000"),
        payment_date=TODAY,
        occurred_at=NOW,
    )
    db.commit()

    assert _balance(db, checking) == Decimal("4880000")

    figures = _figures(db, user)
    assert figures["expense"] == "20000.00"
    assert figures["liabilities"] == "700000.00"
    # 4,880,000 cash + 500,000 savings-less books = assets are cash alone here.
    assert figures["assets"] == "4880000.00"
    assert figures["net_worth"] == "4180000.00"


# ---------------------------------------------------------- multi-currency


def test_a_foreign_balance_is_converted_before_it_is_totalled(db, user, books):
    """500 dollars at 1,400 is 700,000 francs, not 500.

    Assets    5,000,000 francs + (500 x 1,400) = 5,700,000
    """
    from app.services.accounts import create_account
    from app.services.currency import set_rate

    set_rate(db, user=user, base_currency="USD", quote_currency="RWF", rate=Decimal("1400"))
    create_account(
        db,
        user=user,
        name="Dollars",
        account_type=AccountType.SAVINGS,
        currency="USD",
        opening_balance=Decimal("500"),
        opening_balance_at=datetime(2026, 8, 1, 9, 0, tzinfo=UTC),
    )
    db.commit()

    assert _figures(db, user)["assets"] == "5700000.00"


def test_an_unconvertible_balance_is_left_out_and_named(db, user, books):
    """Adding it at 1:1 would give a wrong total rather than a rough one."""
    from app.services.accounts import create_account

    create_account(
        db,
        user=user,
        name="Yen",
        account_type=AccountType.SAVINGS,
        currency="JPY",
        opening_balance=Decimal("90000"),
        opening_balance_at=datetime(2026, 8, 1, 9, 0, tzinfo=UTC),
    )
    db.commit()

    position = reporting.net_worth(db, user=user, context="personal")
    assert position["assets"] == "5000000.00"
    assert position["unconverted_currencies"] == ["JPY"]


# ------------------------------------------------------- features together


def test_an_excluded_account_leaves_the_totals_but_not_the_spending(db, user, books):
    """The distinction drawn when the flag was added, checked on real figures.

    Cash 5,000,000 counts. The 800,000 float does not, but the 30,000 spent
    from it still does.
    """
    checking, _, _ = books
    float_account = make_account(
        db, user, "Float", Visibility.PRIVATE, opening="800000", excluded_from_totals=True
    )
    _spend(db, user, float_account, "30000", _category(db, user, "Shopping"))
    db.commit()

    figures = _figures(db, user)
    assert figures["assets"] == "5000000.00", "the float is out of the total"
    assert figures["expense"] == "30000.00", "but its spending is not"
    assert _balance(db, float_account) == Decimal("770000")


def test_a_goal_contribution_is_a_transfer_and_nothing_more(db, user, books):
    """A goal moves money between two accounts you already own, so net worth
    is unchanged and nothing is spent — while the goal reads as funded."""
    from app.services import goals as goal_service

    checking, savings, _ = books
    goal = goal_service.create_goal(
        db, user=user, name="Laptop", account=savings, target_amount=Decimal("600000")
    )
    db.commit()
    goal_service.contribute(
        db, user=user, goal=goal, source=checking, amount=Decimal("400000"), occurred_at=NOW
    )
    db.commit()

    figures = _figures(db, user)
    assert figures["net_worth"] == "5000000.00"
    assert figures["expense"] == "0.00"
    assert _balance(db, checking) == Decimal("4600000")
    assert _balance(db, savings) == Decimal("400000")
    assert goal_service.list_goals(db, user=user)[0]["saved"] == "400000.00"


def test_a_budget_counts_the_same_spending_the_month_does(db, user, books):
    """Two features reading the same events must agree. A month's expense
    total and a budget's spent figure are computed separately; a disagreement
    would mean one of them is wrong."""
    from app.services import budgets as budget_service

    checking, _, _ = books
    groceries = _category(db, user, "Groceries")
    budget_service.create_budget(
        db, user=user, category_id=groceries.id, amount=Decimal("200000")
    )
    db.commit()

    _spend(db, user, checking, "120000", groceries)
    _spend(db, user, checking, "30000", _category(db, user, "Transport"))
    db.commit()

    status = budget_service.status(db, user=user, today=TODAY)
    spent_on_groceries = next(
        b["spent"] for b in status["budgets"] if b["category"]["name"] == "Groceries"
    )
    assert spent_on_groceries == "120000.00"
    # The month counts both; the budget counts only its own category.
    assert _figures(db, user)["expense"] == "150000.00"


def test_the_whole_picture_after_a_realistic_month(db, user, books):
    """Everything above, in one sequence, checked once at the end.

    Cash    5,000,000 + 2,500,000 salary
                      -   100,000 groceries
                      -    50,000 fuel      -  1,000 its fee
                      -   500,000 to savings
                      -   400,000 to the goal
                      -   100,000 card payment          = 6,349,000
    Savings         0 +   500,000 +   400,000           =   900,000
    Card                  200,000 debt -   100,000 paid =   100,000

    Assets      6,349,000 + 900,000 = 7,249,000
    Liabilities                          100,000
    Net worth   7,249,000 - 100,000 = 7,149,000

    Income                            2,500,000
    Expense   100,000 + 50,000 + 1,000 + 200,000 = 351,000
              (transfers, the goal and the card payment are not spending)
    """
    from app.services import credit_cards
    from app.services import goals as goal_service

    checking, savings, card = books

    _earn(db, user, checking, "2500000")
    _spend(db, user, checking, "100000", _category(db, user, "Groceries"))
    _spend(db, user, checking, "50000", _category(db, user, "Fuel"), fee="1000")
    _move(db, user, checking, savings, "500000")

    goal = goal_service.create_goal(
        db, user=user, name="Laptop", account=savings, target_amount=Decimal("600000")
    )
    db.commit()
    goal_service.contribute(
        db, user=user, goal=goal, source=checking, amount=Decimal("400000"), occurred_at=NOW
    )

    _spend(db, user, card, "200000", _category(db, user, "Shopping"))
    credit_cards.pay_card(
        db, user=user, card=card, source=checking, amount=Decimal("100000"), occurred_at=NOW
    )
    db.commit()

    assert _balance(db, checking) == Decimal("6349000")
    assert _balance(db, savings) == Decimal("900000")
    assert _balance(db, card) == Decimal("100000")

    assert _figures(db, user) == {
        "assets": "7249000.00",
        "liabilities": "100000.00",
        "net_worth": "7149000.00",
        "income": "2500000.00",
        "expense": "351000.00",
    }
    assert goal_service.list_goals(db, user=user)[0]["saved"] == "400000.00"
