"""Transfer invariants (Implementation Plan Phase 7).

The plan names five: source decreases, destination increases, income unchanged,
expense unchanged, net worth unchanged.
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.errors import Conflict, ValidationFailed
from app.db.enums import Direction, TransactionStatus, TransactionType, TransferStatus
from app.models.finance import Transaction
from app.services.posting import PostingService

NOW = datetime(2026, 8, 24, 14, 30, tzinfo=UTC)
AMOUNT = Decimal("100000")


def _totals(db, user_id, txn_type: TransactionType) -> Decimal:
    rows = db.scalars(
        select(Transaction.amount).where(
            Transaction.created_by == user_id,
            Transaction.transaction_type == txn_type,
            Transaction.status == TransactionStatus.COMPLETED,
            Transaction.deleted_at.is_(None),
        )
    ).all()
    return sum(rows, Decimal("0"))


def test_transfer_moves_value_between_asset_accounts(db, bank_account, savings_account, user):
    posting = PostingService(db)
    posting.transfer_funds(
        source=bank_account,
        destination=savings_account,
        source_amount=AMOUNT,
        destination_amount=AMOUNT,
        occurred_at=NOW,
        actor_id=user.id,
    )
    db.commit()
    assert posting.balance_of(bank_account) == Decimal("900000.0000")
    assert posting.balance_of(savings_account) == Decimal("600000.0000")


def test_transfer_leaves_income_and_expense_untouched(db, bank_account, savings_account, user):
    posting = PostingService(db)
    posting.transfer_funds(
        source=bank_account,
        destination=savings_account,
        source_amount=AMOUNT,
        destination_amount=AMOUNT,
        occurred_at=NOW,
        actor_id=user.id,
    )
    db.commit()
    assert _totals(db, user.id, TransactionType.INCOME) == Decimal("0")
    assert _totals(db, user.id, TransactionType.EXPENSE) == Decimal("0")


def test_transfer_preserves_net_worth(db, bank_account, savings_account, user):
    posting = PostingService(db)
    before = posting.net_worth_contribution(bank_account) + posting.net_worth_contribution(
        savings_account
    )
    posting.transfer_funds(
        source=bank_account,
        destination=savings_account,
        source_amount=AMOUNT,
        destination_amount=AMOUNT,
        occurred_at=NOW,
        actor_id=user.id,
    )
    db.commit()
    after = posting.net_worth_contribution(bank_account) + posting.net_worth_contribution(
        savings_account
    )
    assert before == after


def test_card_repayment_preserves_net_worth(db, bank_account, credit_card, user):
    """Paying a card moves nothing in or out of the household: cash falls by the
    same amount debt falls."""
    posting = PostingService(db)
    before = posting.net_worth_contribution(bank_account) + posting.net_worth_contribution(
        credit_card
    )
    posting.transfer_funds(
        source=bank_account,
        destination=credit_card,
        source_amount=Decimal("150000"),
        destination_amount=Decimal("150000"),
        occurred_at=NOW,
        actor_id=user.id,
    )
    db.commit()
    after = posting.net_worth_contribution(bank_account) + posting.net_worth_contribution(
        credit_card
    )
    assert before == after


def test_transfer_creates_exactly_two_linked_entries(db, bank_account, savings_account, user):
    posting = PostingService(db)
    transfer = posting.transfer_funds(
        source=bank_account,
        destination=savings_account,
        source_amount=AMOUNT,
        destination_amount=AMOUNT,
        occurred_at=NOW,
        actor_id=user.id,
    )
    db.commit()
    sides = db.scalars(select(Transaction).where(Transaction.transfer_id == transfer.id)).all()
    assert len(sides) == 2
    assert {s.transaction_type for s in sides} == {TransactionType.TRANSFER}
    by_account = {s.account_id: s for s in sides}
    assert by_account[bank_account.id].direction is Direction.DECREASE
    assert by_account[savings_account.id].direction is Direction.INCREASE


def test_card_repayment_decreases_both_sides(db, bank_account, credit_card, user):
    posting = PostingService(db)
    transfer = posting.transfer_funds(
        source=bank_account,
        destination=credit_card,
        source_amount=Decimal("150000"),
        destination_amount=Decimal("150000"),
        occurred_at=NOW,
        actor_id=user.id,
    )
    db.commit()
    sides = db.scalars(select(Transaction).where(Transaction.transfer_id == transfer.id)).all()
    assert {s.direction for s in sides} == {Direction.DECREASE}


def test_transfer_to_same_account_is_rejected(db, bank_account, user):
    with pytest.raises(ValidationFailed):
        PostingService(db).transfer_funds(
            source=bank_account,
            destination=bank_account,
            source_amount=AMOUNT,
            destination_amount=AMOUNT,
            occurred_at=NOW,
            actor_id=user.id,
        )


def test_mismatched_amounts_are_rejected(db, bank_account, savings_account, user):
    with pytest.raises(ValidationFailed):
        PostingService(db).transfer_funds(
            source=bank_account,
            destination=savings_account,
            source_amount=AMOUNT,
            destination_amount=Decimal("99000"),
            occurred_at=NOW,
            actor_id=user.id,
        )


def test_failed_transfer_writes_nothing(db, bank_account, savings_account, user):
    """A rejected transfer must not leave a dangling Transfer row or one-sided entry."""
    with pytest.raises(ValidationFailed):
        PostingService(db).transfer_funds(
            source=bank_account,
            destination=savings_account,
            source_amount=Decimal("-5"),
            destination_amount=Decimal("-5"),
            occurred_at=NOW,
            actor_id=user.id,
        )
    db.rollback()
    assert db.scalars(select(Transaction)).all() == []
    assert PostingService(db).balance_of(bank_account) == Decimal("1000000.0000")


def test_cancel_reverses_both_sides_together(db, bank_account, savings_account, user):
    posting = PostingService(db)
    transfer = posting.transfer_funds(
        source=bank_account,
        destination=savings_account,
        source_amount=AMOUNT,
        destination_amount=AMOUNT,
        occurred_at=NOW,
        actor_id=user.id,
    )
    db.commit()

    posting.cancel_transfer(transfer, actor_id=user.id)
    db.commit()

    assert transfer.status is TransferStatus.CANCELLED
    sides = db.scalars(select(Transaction).where(Transaction.transfer_id == transfer.id)).all()
    assert {s.status for s in sides} == {TransactionStatus.CANCELLED}
    # Both balances return to where they started.
    assert posting.balance_of(bank_account) == Decimal("1000000.0000")
    assert posting.balance_of(savings_account) == Decimal("500000.0000")


def test_double_cancel_is_rejected(db, bank_account, savings_account, user):
    posting = PostingService(db)
    transfer = posting.transfer_funds(
        source=bank_account,
        destination=savings_account,
        source_amount=AMOUNT,
        destination_amount=AMOUNT,
        occurred_at=NOW,
        actor_id=user.id,
    )
    db.commit()
    posting.cancel_transfer(transfer, actor_id=user.id)
    db.commit()
    with pytest.raises(Conflict):
        posting.cancel_transfer(transfer, actor_id=user.id)
