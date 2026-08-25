"""Fees charged on an expense.

A fee is money that really left the account, so it is its own line in the
ledger rather than an adjustment to the amount beside it. Folding the two
together would put every reconciliation out by the fee and would overstate
what the purchase itself cost.
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.errors import ValidationFailed
from app.db.enums import TransactionType
from app.models.finance import Transaction
from app.services import transactions as txn_service
from app.services.posting import PostingService

NOW = datetime(2026, 8, 25, 12, 0, tzinfo=UTC)


def _spend(db, user, account, *, amount="10000", fee=None, description="Cash withdrawal"):
    return txn_service.create_transaction(
        db,
        user=user,
        account_id=account.id,
        transaction_type=TransactionType.EXPENSE,
        amount=Decimal(amount),
        occurred_at=NOW,
        description=description,
        fee_amount=Decimal(fee) if fee is not None else None,
    )


def _rows(db, account):
    return list(
        db.scalars(
            select(Transaction)
            .where(Transaction.account_id == account.id, Transaction.deleted_at.is_(None))
            .order_by(Transaction.created_at)
        )
    )


# --------------------------------------------------------------- separate line


def test_a_fee_is_its_own_transaction(db, user, bank_account):
    parent = _spend(db, user, bank_account, amount="10000", fee="500")
    db.commit()
    fees = db.scalars(
        select(Transaction).where(Transaction.fee_for_transaction_id == parent.id)
    ).all()
    assert len(fees) == 1


def test_the_charge_keeps_its_own_amount(db, user, bank_account):
    """The purchase cost what it cost; the fee is not added to it."""
    parent = _spend(db, user, bank_account, amount="10000", fee="500")
    db.commit()
    assert Decimal(parent.amount) == Decimal("10000")


def test_both_lines_come_off_the_balance(db, user, bank_account):
    posting = PostingService(db)
    before = posting.balance_of(bank_account)
    _spend(db, user, bank_account, amount="10000", fee="500")
    db.commit()
    assert posting.balance_of(bank_account) == before - Decimal("10500")


def test_the_fee_is_named_after_what_it_was_charged_on(db, user, bank_account):
    _spend(db, user, bank_account, fee="500", description="ATM withdrawal")
    db.commit()
    fee = db.scalar(
        select(Transaction).where(Transaction.fee_for_transaction_id.is_not(None))
    )
    assert fee.description == "ATM withdrawal — fee"


def test_an_unnamed_charge_still_yields_a_readable_fee(db, user, bank_account):
    txn_service.create_transaction(
        db,
        user=user,
        account_id=bank_account.id,
        transaction_type=TransactionType.EXPENSE,
        amount=Decimal("10000"),
        occurred_at=NOW,
        fee_amount=Decimal("500"),
    )
    db.commit()
    fee = db.scalar(
        select(Transaction).where(Transaction.fee_for_transaction_id.is_not(None))
    )
    assert fee.description == "Fee"


def test_no_fee_means_no_extra_line(db, user, bank_account):
    _spend(db, user, bank_account, amount="10000")
    db.commit()
    assert len(_rows(db, bank_account)) == 1


def test_the_fee_shares_the_moment_of_the_charge(db, user, bank_account):
    """They happened together; a list sorted by time should not separate them."""
    parent = _spend(db, user, bank_account, fee="500")
    db.commit()
    fee = db.scalar(
        select(Transaction).where(Transaction.fee_for_transaction_id == parent.id)
    )
    assert fee.occurred_at == parent.occurred_at


# ------------------------------------------------------------------- on a card


def test_a_fee_on_a_card_raises_debt_like_the_purchase(db, user, credit_card):
    """The account's nature decides direction, for the fee as for anything."""
    posting = PostingService(db)
    owed_before = posting.balance_of(credit_card)
    _spend(db, user, credit_card, amount="30000", fee="900", description="Foreign purchase")
    db.commit()
    assert posting.balance_of(credit_card) == owed_before + Decimal("30900")


# ------------------------------------------------------------------- refusals


def test_a_fee_cannot_be_charged_on_income(db, user, bank_account):
    with pytest.raises(ValidationFailed) as exc:
        txn_service.create_transaction(
            db,
            user=user,
            account_id=bank_account.id,
            transaction_type=TransactionType.INCOME,
            amount=Decimal("50000"),
            occurred_at=NOW,
            fee_amount=Decimal("500"),
        )
    assert exc.value.code == "FEE_NOT_APPLICABLE"


@pytest.mark.parametrize("bad", ["0", "-100"])
def test_a_fee_must_be_a_real_amount(db, user, bank_account, bad):
    with pytest.raises(ValidationFailed):
        _spend(db, user, bank_account, fee=bad)


def test_a_refused_fee_leaves_nothing_behind(db, user, bank_account):
    """The check runs before anything is posted, so a bad fee does not cost
    the user a stranded expense."""
    posting = PostingService(db)
    before = posting.balance_of(bank_account)
    with pytest.raises(ValidationFailed):
        _spend(db, user, bank_account, amount="10000", fee="-100")
    db.rollback()
    assert posting.balance_of(bank_account) == before
    assert _rows(db, bank_account) == []


# ------------------------------------------------------------------- deletion


def test_deleting_the_charge_takes_its_fee_with_it(db, user, bank_account):
    """A fee outliving what it was charged on is a line nobody can explain."""
    posting = PostingService(db)
    before = posting.balance_of(bank_account)
    parent = _spend(db, user, bank_account, amount="10000", fee="500")
    db.commit()

    txn_service.delete_transaction(db, user=user, transaction_id=parent.id)
    db.commit()
    assert posting.balance_of(bank_account) == before
    assert _rows(db, bank_account) == []


def test_deleting_the_fee_alone_leaves_the_charge(db, user, bank_account):
    """A fee wrongly recorded can be removed without undoing the purchase."""
    posting = PostingService(db)
    parent = _spend(db, user, bank_account, amount="10000", fee="500")
    db.commit()
    fee = db.scalar(
        select(Transaction).where(Transaction.fee_for_transaction_id == parent.id)
    )

    txn_service.delete_transaction(db, user=user, transaction_id=fee.id)
    db.commit()
    assert len(_rows(db, bank_account)) == 1
    assert posting.balance_of(bank_account) == Decimal(bank_account.opening_balance) - Decimal(
        "10000"
    )


# -------------------------------------------------------------------- listing


def test_both_lines_appear_in_the_list(db, user, bank_account):
    _spend(db, user, bank_account, amount="10000", fee="500", description="ATM withdrawal")
    db.commit()
    rows, _ = txn_service.list_transactions(db, user=user)
    assert sorted(t.description for t in rows) == ["ATM withdrawal", "ATM withdrawal — fee"]


def test_the_payload_says_what_a_fee_belongs_to(db, user, bank_account):
    parent = _spend(db, user, bank_account, fee="500")
    db.commit()
    fee = db.scalar(
        select(Transaction).where(Transaction.fee_for_transaction_id == parent.id)
    )
    payload = txn_service.serialize_transaction(fee)
    assert payload["fee_for_transaction_id"] == str(parent.id)
    assert txn_service.serialize_transaction(parent)["fee_for_transaction_id"] is None


# ------------------------------------------------------------------- transfers


def _move(db, user, source, destination, *, amount="50000", fee=None, notes="MoMo send"):
    return PostingService(db).transfer_funds(
        source=source,
        destination=destination,
        source_amount=Decimal(amount),
        destination_amount=Decimal(amount),
        occurred_at=NOW,
        actor_id=user.id,
        notes=notes,
        fee_amount=Decimal(fee) if fee is not None else None,
    )


def test_a_transfer_fee_comes_off_the_sender(db, user, bank_account, savings_account):
    """The sender pays the charge, so it is not the destination's problem."""
    posting = PostingService(db)
    from_before = posting.balance_of(bank_account)
    to_before = posting.balance_of(savings_account)

    _move(db, user, bank_account, savings_account, amount="50000", fee="1000")
    db.commit()

    assert posting.balance_of(bank_account) == from_before - Decimal("51000")
    # What arrived is what arrived: the fee did not follow the money across.
    assert posting.balance_of(savings_account) == to_before + Decimal("50000")


def test_the_transfer_still_records_the_amount_that_moved(db, user, bank_account, savings_account):
    transfer = _move(db, user, bank_account, savings_account, amount="50000", fee="1000")
    db.commit()
    assert Decimal(transfer.source_amount) == Decimal("50000")


def test_a_transfer_fee_is_an_expense_not_a_transfer(db, user, bank_account, savings_account):
    """Money moved between your own accounts is not spending; the charge is."""
    _move(db, user, bank_account, savings_account, fee="1000")
    db.commit()
    fee = db.scalar(select(Transaction).where(Transaction.fee_for_transaction_id.is_not(None)))
    assert fee.transaction_type is TransactionType.EXPENSE
    assert fee.account_id == bank_account.id


def test_the_transfer_fee_hangs_off_the_outgoing_side(db, user, bank_account, savings_account):
    transfer = _move(db, user, bank_account, savings_account, fee="1000")
    db.commit()
    fee = db.scalar(select(Transaction).where(Transaction.fee_for_transaction_id.is_not(None)))
    parent = db.get(Transaction, fee.fee_for_transaction_id)
    assert parent.transfer_id == transfer.id
    assert parent.account_id == bank_account.id


def test_the_transfer_fee_is_named_after_the_transfer(db, user, bank_account, savings_account):
    _move(db, user, bank_account, savings_account, fee="1000", notes="Rent to landlord")
    db.commit()
    fee = db.scalar(select(Transaction).where(Transaction.fee_for_transaction_id.is_not(None)))
    assert fee.description == "Rent to landlord — fee"


def test_an_unnamed_transfer_still_yields_a_readable_fee(db, user, bank_account, savings_account):
    _move(db, user, bank_account, savings_account, fee="1000", notes=None)
    db.commit()
    fee = db.scalar(select(Transaction).where(Transaction.fee_for_transaction_id.is_not(None)))
    assert fee.description == f"Transfer to {savings_account.name} — fee"


def test_cancelling_a_transfer_cancels_its_fee(db, user, bank_account, savings_account):
    """Otherwise you are charged for a movement the ledger no longer shows."""
    posting = PostingService(db)
    before = posting.balance_of(bank_account)
    transfer = _move(db, user, bank_account, savings_account, amount="50000", fee="1000")
    db.commit()

    posting.cancel_transfer(transfer, actor_id=user.id)
    db.commit()
    assert posting.balance_of(bank_account) == before


def test_a_transfer_fee_must_be_a_real_amount(db, user, bank_account, savings_account):
    with pytest.raises(ValidationFailed):
        _move(db, user, bank_account, savings_account, fee="0")


def test_no_fee_on_a_transfer_means_two_lines_only(db, user, bank_account, savings_account):
    _move(db, user, bank_account, savings_account)
    db.commit()
    rows = db.scalars(select(Transaction).where(Transaction.deleted_at.is_(None))).all()
    assert len(rows) == 2
