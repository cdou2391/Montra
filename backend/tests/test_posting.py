"""Financial invariant tests for the posting engine.

Implementation Plan Phase 5: "This is one of the most important phases in the
project." These assert the ledger rules directly, not through the API.
"""

from datetime import date
from decimal import Decimal

import pytest

from app.db.enums import AccountNature, Direction, TransactionType
from app.services.posting import DIRECTION_RULES, Operation, PostingService, resolve_direction

TODAY = date(2026, 8, 24)


# --------------------------------------------------------------- direction table


@pytest.mark.parametrize(
    ("operation", "nature", "expected"),
    [
        (Operation.INCOME, AccountNature.ASSET, Direction.INCREASE),
        (Operation.INCOME, AccountNature.LIABILITY, Direction.DECREASE),
        (Operation.EXPENSE, AccountNature.ASSET, Direction.DECREASE),
        (Operation.EXPENSE, AccountNature.LIABILITY, Direction.INCREASE),
        (Operation.TRANSFER_OUT, AccountNature.ASSET, Direction.DECREASE),
        (Operation.TRANSFER_OUT, AccountNature.LIABILITY, Direction.INCREASE),
        (Operation.TRANSFER_IN, AccountNature.ASSET, Direction.INCREASE),
        (Operation.TRANSFER_IN, AccountNature.LIABILITY, Direction.DECREASE),
    ],
)
def test_direction_rules(operation, nature, expected):
    assert resolve_direction(operation, nature) is expected


def test_direction_table_is_total():
    """Every operation/nature pair must be defined; a missing rule is a silent
    KeyError at posting time."""
    expected = {(op, nature) for op in Operation for nature in AccountNature}
    assert set(DIRECTION_RULES) == expected


# ------------------------------------------------------------------ asset ledger


def test_income_into_asset_increases_balance(db, bank_account):
    posting = PostingService(db)
    posting.record_income(
        account=bank_account,
        amount=Decimal("2500000"),
        currency="RWF",
        transaction_date=TODAY,
        actor_id=bank_account.owner_user_id,
    )
    db.commit()
    assert posting.balance_of(bank_account) == Decimal("3500000.0000")


def test_expense_from_asset_decreases_balance(db, bank_account):
    posting = PostingService(db)
    posting.record_expense(
        account=bank_account,
        amount=Decimal("85000"),
        currency="RWF",
        transaction_date=TODAY,
        actor_id=bank_account.owner_user_id,
    )
    db.commit()
    assert posting.balance_of(bank_account) == Decimal("915000.0000")


# -------------------------------------------------------------- liability ledger


def test_credit_card_expense_increases_debt(db, credit_card):
    """Data Model section 83: a card purchase raises the liability balance."""
    posting = PostingService(db)
    txn = posting.record_expense(
        account=credit_card,
        amount=Decimal("85000"),
        currency="RWF",
        transaction_date=TODAY,
        actor_id=credit_card.owner_user_id,
    )
    db.commit()
    assert txn.direction is Direction.INCREASE
    assert posting.balance_of(credit_card) == Decimal("285000.0000")


def test_credit_card_expense_is_still_an_expense(db, credit_card):
    """Debt rises, and the transaction still classifies as spending for analytics."""
    posting = PostingService(db)
    txn = posting.record_expense(
        account=credit_card,
        amount=Decimal("85000"),
        currency="RWF",
        transaction_date=TODAY,
        actor_id=credit_card.owner_user_id,
    )
    db.commit()
    assert txn.transaction_type is TransactionType.EXPENSE


def test_credit_card_payment_decreases_debt(db, bank_account, credit_card):
    """Data Model section 84: both sides of a repayment are DECREASE."""
    posting = PostingService(db)
    posting.transfer_funds(
        source=bank_account,
        destination=credit_card,
        source_amount=Decimal("150000"),
        destination_amount=Decimal("150000"),
        transfer_date=TODAY,
        actor_id=bank_account.owner_user_id,
    )
    db.commit()
    assert posting.balance_of(credit_card) == Decimal("50000.0000")
    assert posting.balance_of(bank_account) == Decimal("850000.0000")


def test_refund_to_card_decreases_debt(db, credit_card):
    posting = PostingService(db)
    txn = posting.record_income(
        account=credit_card,
        amount=Decimal("20000"),
        currency="RWF",
        transaction_date=TODAY,
        actor_id=credit_card.owner_user_id,
    )
    db.commit()
    assert txn.direction is Direction.DECREASE
    assert posting.balance_of(credit_card) == Decimal("180000.0000")


def test_cash_advance_from_card_increases_debt(db, bank_account, credit_card):
    """Money out of a liability is borrowing: debt rises and cash rises."""
    posting = PostingService(db)
    posting.transfer_funds(
        source=credit_card,
        destination=bank_account,
        source_amount=Decimal("100000"),
        destination_amount=Decimal("100000"),
        transfer_date=TODAY,
        actor_id=bank_account.owner_user_id,
    )
    db.commit()
    assert posting.balance_of(credit_card) == Decimal("300000.0000")
    assert posting.balance_of(bank_account) == Decimal("1100000.0000")


# ---------------------------------------------------------------------- net worth


def test_liability_subtracts_from_net_worth(db, bank_account, credit_card):
    posting = PostingService(db)
    assert posting.net_worth_contribution(bank_account) == Decimal("1000000.0000")
    assert posting.net_worth_contribution(credit_card) == Decimal("-200000.0000")


# --------------------------------------------------------------------- integrity


def test_zero_and_negative_amounts_are_rejected(db, bank_account):
    posting = PostingService(db)
    from app.core.errors import ValidationFailed

    for bad in (Decimal("0"), Decimal("-1")):
        with pytest.raises(ValidationFailed):
            posting.record_expense(
                account=bank_account,
                amount=bad,
                currency="RWF",
                transaction_date=TODAY,
                actor_id=bank_account.owner_user_id,
            )


def test_currency_must_match_account(db, bank_account):
    from app.core.errors import ValidationFailed

    with pytest.raises(ValidationFailed):
        PostingService(db).record_expense(
            account=bank_account,
            amount=Decimal("100"),
            currency="USD",
            transaction_date=TODAY,
            actor_id=bank_account.owner_user_id,
        )


def test_balance_is_derived_not_cached(db, bank_account):
    """Balance must reconstruct from opening balance plus ledger every time."""
    posting = PostingService(db)
    for _ in range(5):
        posting.record_expense(
            account=bank_account,
            amount=Decimal("10000"),
            currency="RWF",
            transaction_date=TODAY,
            actor_id=bank_account.owner_user_id,
        )
    db.commit()
    assert posting.balance_of(bank_account) == Decimal("950000.0000")

    # A fresh service instance sees the same number: nothing is memoised.
    assert PostingService(db).balance_of(bank_account) == Decimal("950000.0000")


def test_decimal_precision_survives_many_postings(db, bank_account):
    """No floating point drift across repeated fractional amounts."""
    posting = PostingService(db)
    for _ in range(100):
        posting.record_expense(
            account=bank_account,
            amount=Decimal("0.1000"),
            currency="RWF",
            transaction_date=TODAY,
            actor_id=bank_account.owner_user_id,
        )
    db.commit()
    assert posting.balance_of(bank_account) == Decimal("999990.0000")


def test_cancelled_transactions_do_not_affect_balance(db, bank_account):
    from app.db.enums import TransactionStatus

    posting = PostingService(db)
    txn = posting.record_expense(
        account=bank_account,
        amount=Decimal("50000"),
        currency="RWF",
        transaction_date=TODAY,
        actor_id=bank_account.owner_user_id,
    )
    db.commit()
    assert posting.balance_of(bank_account) == Decimal("950000.0000")

    txn.status = TransactionStatus.CANCELLED
    db.commit()
    assert posting.balance_of(bank_account) == Decimal("1000000.0000")


def test_soft_deleted_transactions_do_not_affect_balance(db, bank_account):
    from app.db.base import utcnow

    posting = PostingService(db)
    txn = posting.record_expense(
        account=bank_account,
        amount=Decimal("50000"),
        currency="RWF",
        transaction_date=TODAY,
        actor_id=bank_account.owner_user_id,
    )
    db.commit()
    txn.deleted_at = utcnow()
    db.commit()
    assert posting.balance_of(bank_account) == Decimal("1000000.0000")


# -------------------------------------------------------------------- adjustment


def test_adjustment_reconciles_asset_upwards(db, bank_account):
    posting = PostingService(db)
    txn = posting.adjust_balance(
        account=bank_account,
        actual_balance=Decimal("1200000"),
        adjustment_date=TODAY,
        actor_id=bank_account.owner_user_id,
    )
    db.commit()
    assert txn.direction is Direction.INCREASE
    assert txn.amount == Decimal("200000.0000")
    assert posting.balance_of(bank_account) == Decimal("1200000.0000")


def test_adjustment_reconciles_liability_downwards(db, credit_card):
    posting = PostingService(db)
    txn = posting.adjust_balance(
        account=credit_card,
        actual_balance=Decimal("150000"),
        adjustment_date=TODAY,
        actor_id=credit_card.owner_user_id,
    )
    db.commit()
    assert txn.direction is Direction.DECREASE
    assert posting.balance_of(credit_card) == Decimal("150000.0000")


def test_adjustment_is_a_noop_when_balance_matches(db, bank_account):
    posting = PostingService(db)
    assert (
        posting.adjust_balance(
            account=bank_account,
            actual_balance=Decimal("1000000"),
            adjustment_date=TODAY,
            actor_id=bank_account.owner_user_id,
        )
        is None
    )
