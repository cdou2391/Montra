"""Credit-card and prepaid-card behaviour (Implementation Plan Phases 9-10).

The plan names three properties to test carefully:

    Purchase  = Expense + increased liability
    Payment   = reduced cash + reduced liability
    Payment  != Expense
"""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.errors import ValidationFailed
from app.db.enums import Direction, TransactionType
from app.models.finance import Transaction
from app.services import credit_cards as cards
from app.services.posting import PostingService

NOW = datetime(2026, 8, 24, 14, 30, tzinfo=UTC)


def _totals(db, user_id, txn_type: TransactionType) -> Decimal:
    rows = db.scalars(
        select(Transaction.amount).where(
            Transaction.created_by == user_id,
            Transaction.transaction_type == txn_type,
            Transaction.deleted_at.is_(None),
        )
    ).all()
    return sum(rows, Decimal("0"))


# ------------------------------------------------------- the three properties


def test_purchase_is_an_expense_and_raises_liability(db, credit_card, user):
    txn = PostingService(db).record_expense(
        account=credit_card,
        amount=Decimal("85000"),
        currency="RWF",
        occurred_at=NOW,
        actor_id=user.id,
    )
    db.commit()
    assert txn.transaction_type is TransactionType.EXPENSE
    assert txn.direction is Direction.INCREASE
    assert PostingService(db).balance_of(credit_card) == Decimal("285000.0000")
    assert _totals(db, user.id, TransactionType.EXPENSE) == Decimal("85000.0000")


def test_payment_reduces_cash_and_liability(db, bank_account, credit_card, user):
    cards.pay_card(
        db,
        user=user,
        card=credit_card,
        source=bank_account,
        amount=Decimal("150000"),
        occurred_at=NOW,
    )
    db.commit()
    posting = PostingService(db)
    assert posting.balance_of(bank_account) == Decimal("850000.0000")
    assert posting.balance_of(credit_card) == Decimal("50000.0000")


def test_payment_is_not_an_expense(db, bank_account, credit_card, user):
    """The property most likely to be got wrong: paying a card is moving money
    you already owed, not spending it again."""
    cards.pay_card(
        db,
        user=user,
        card=credit_card,
        source=bank_account,
        amount=Decimal("150000"),
        occurred_at=NOW,
    )
    db.commit()
    assert _totals(db, user.id, TransactionType.EXPENSE) == Decimal("0")
    assert _totals(db, user.id, TransactionType.INCOME) == Decimal("0")


def test_payment_preserves_net_worth(db, bank_account, credit_card, user):
    posting = PostingService(db)
    before = posting.net_worth_contribution(bank_account) + posting.net_worth_contribution(
        credit_card
    )
    cards.pay_card(
        db,
        user=user,
        card=credit_card,
        source=bank_account,
        amount=Decimal("150000"),
        occurred_at=NOW,
    )
    db.commit()
    after = posting.net_worth_contribution(bank_account) + posting.net_worth_contribution(
        credit_card
    )
    assert before == after


def test_purchase_then_payment_settles_correctly(db, bank_account, credit_card, user):
    posting = PostingService(db)
    posting.record_expense(
        account=credit_card,
        amount=Decimal("85000"),
        currency="RWF",
        occurred_at=NOW,
        actor_id=user.id,
    )
    db.commit()
    cards.pay_card(
        db,
        user=user,
        card=credit_card,
        source=bank_account,
        amount=Decimal("285000"),
        occurred_at=NOW,
    )
    db.commit()
    # Card cleared, and only the purchase counted as spending.
    assert posting.balance_of(credit_card) == Decimal("0.0000")
    assert posting.balance_of(bank_account) == Decimal("715000.0000")
    assert _totals(db, user.id, TransactionType.EXPENSE) == Decimal("85000.0000")


# ------------------------------------------------------------------- guardrails


def test_payment_source_must_be_an_asset(db, credit_card, user, savings_account):
    """Paying one card with another is not a payment; it is a balance transfer,
    which the MVP does not model."""
    other_card = credit_card
    with pytest.raises(ValidationFailed) as exc:
        cards.pay_card(
            db,
            user=user,
            card=other_card,
            source=other_card,
            amount=Decimal("1000"),
            occurred_at=NOW,
        )
    assert exc.value.code == "INVALID_PAYMENT_SOURCE"


def test_summary_rejects_a_non_card_account(db, bank_account):
    with pytest.raises(ValidationFailed) as exc:
        cards.summary(db, bank_account)
    assert exc.value.code == "NOT_A_CREDIT_CARD"


def test_card_fields_rejected_on_non_card_account(db, bank_account):
    with pytest.raises(ValidationFailed):
        cards.apply_card_fields(bank_account, {"credit_limit": Decimal("100")})


# ---------------------------------------------------------------------- summary


def test_summary_computes_utilization_and_available_credit(db, credit_card, user):
    credit_card.credit_limit = Decimal("3000000")
    credit_card.statement_balance = Decimal("180000")
    credit_card.minimum_payment = Decimal("20000")
    db.commit()

    PostingService(db).record_expense(
        account=credit_card,
        amount=Decimal("1220000"),
        currency="RWF",
        occurred_at=NOW,
        actor_id=user.id,
    )
    db.commit()

    s = cards.summary(db, credit_card, today=date(2026, 8, 24))
    assert s["outstanding_balance"] == "1420000.00"
    assert s["available_credit"] == "1580000.00"
    assert s["credit_limit"] == "3000000.00"
    assert s["utilization_percentage"] == "47.33"
    assert s["utilization_band"] == "NEUTRAL"
    assert s["statement_balance"] == "180000.00"


def test_summary_without_a_limit_reports_no_utilization(db, credit_card):
    s = cards.summary(db, credit_card, today=date(2026, 8, 24))
    assert s["credit_limit"] is None
    assert s["available_credit"] is None
    assert s["utilization_percentage"] is None
    assert s["utilization_band"] is None
    assert s["outstanding_balance"] == "200000.00"


def test_over_limit_reports_negative_available_credit(db, credit_card, user):
    """Reporting the real number beats clamping to zero and hiding it."""
    credit_card.credit_limit = Decimal("100000")
    db.commit()
    s = cards.summary(db, credit_card, today=date(2026, 8, 24))
    assert s["available_credit"] == "-100000.00"
    assert s["utilization_band"] == "HIGH"


@pytest.mark.parametrize(
    ("pct", "band"),
    [
        (Decimal("0"), "NORMAL"),
        (Decimal("30"), "NORMAL"),
        (Decimal("30.01"), "NEUTRAL"),
        (Decimal("60"), "NEUTRAL"),
        (Decimal("60.01"), "WARNING"),
        (Decimal("80"), "WARNING"),
        (Decimal("80.01"), "HIGH"),
        (Decimal("140"), "HIGH"),
    ],
)
def test_utilization_bands(pct, band):
    assert cards.utilization_band(pct) == band


# ------------------------------------------------------------------- due dates


@pytest.mark.parametrize(
    ("today", "due_day", "expected"),
    [
        # Still ahead of the due day this month.
        (date(2026, 8, 1), 5, date(2026, 8, 5)),
        # On the day itself: due today, not next month.
        (date(2026, 8, 5), 5, date(2026, 8, 5)),
        # Past it: rolls to next month.
        (date(2026, 8, 6), 5, date(2026, 9, 5)),
        # Year boundary.
        (date(2026, 12, 20), 5, date(2027, 1, 5)),
        # A card due on the 31st must still resolve in a short month.
        (date(2027, 2, 1), 31, date(2027, 2, 28)),
        (date(2026, 4, 1), 31, date(2026, 4, 30)),
    ],
)
def test_next_due_date(today, due_day, expected):
    assert cards.next_occurrence(due_day, today=today) == expected


def test_interest_rate_drops_trailing_zeros(db, credit_card):
    """DECIMAL(8,5) stores 18.50000; nobody wants to read that."""
    credit_card.interest_rate = Decimal("18.5")
    db.commit()
    assert cards.summary(db, credit_card, today=date(2026, 8, 24))["interest_rate"] == "18.5"


def test_whole_interest_rate_avoids_scientific_notation(db, credit_card):
    credit_card.interest_rate = Decimal("100")
    db.commit()
    assert cards.summary(db, credit_card, today=date(2026, 8, 24))["interest_rate"] == "100"


def test_summary_reports_the_next_due_date(db, credit_card):
    credit_card.payment_due_day = 5
    db.commit()
    s = cards.summary(db, credit_card, today=date(2026, 8, 24))
    assert s["payment_due_date"] == "2026-09-05"


# -------------------------------------------------------------- prepaid top-up


def test_prepaid_top_up_is_a_transfer_not_an_expense(db, bank_account, prepaid_card, user):
    posting = PostingService(db)
    before = posting.net_worth_contribution(bank_account) + posting.net_worth_contribution(
        prepaid_card
    )
    cards.top_up_prepaid(
        db,
        user=user,
        card=prepaid_card,
        source=bank_account,
        amount=Decimal("100000"),
        occurred_at=NOW,
    )
    db.commit()

    assert posting.balance_of(bank_account) == Decimal("900000.0000")
    assert posting.balance_of(prepaid_card) == Decimal("950000.0000")
    assert _totals(db, user.id, TransactionType.EXPENSE) == Decimal("0")
    after = posting.net_worth_contribution(bank_account) + posting.net_worth_contribution(
        prepaid_card
    )
    assert before == after


def test_top_up_rejects_a_credit_card(db, bank_account, credit_card, user):
    with pytest.raises(ValidationFailed) as exc:
        cards.top_up_prepaid(
            db,
            user=user,
            card=credit_card,
            source=bank_account,
            amount=Decimal("1000"),
            occurred_at=NOW,
        )
    assert exc.value.code == "NOT_A_PREPAID_CARD"
