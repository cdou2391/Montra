"""Recurring and planned transfers.

The same property that governs all planning: a planned transfer moves nothing
until completed, and then completes as a real transfer — two linked entries,
no expense.
"""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.errors import ValidationFailed
from app.db.enums import (
    Direction,
    Frequency,
    PlannedStatus,
    PlannedType,
    TransactionType,
)
from app.models.finance import Transaction, Transfer
from app.models.planning import PlannedTransaction
from app.services import planning
from app.services.posting import PostingService

SOON = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)


def _planned_transfer(db, user, source, destination, **kw):
    return planning.create_planned(
        db,
        user=user,
        account_id=source.id,
        destination_account_id=destination.id,
        planned_type=PlannedType.TRANSFER,
        amount=kw.pop("amount", Decimal("100000")),
        expected_at=kw.pop("expected_at", SOON),
        description=kw.pop("description", "Monthly savings"),
        **kw,
    )


# ----------------------------------------------------------------- validation


def test_transfer_requires_a_destination(db, bank_account, user):
    with pytest.raises(ValidationFailed) as exc:
        planning.create_planned(
            db,
            user=user,
            account_id=bank_account.id,
            planned_type=PlannedType.TRANSFER,
            amount=Decimal("1000"),
            expected_at=SOON,
            description="Nowhere",
        )
    assert exc.value.code == "DESTINATION_REQUIRED"


def test_expense_rejects_a_destination(db, bank_account, savings_account, user):
    """A destination on an expense would be silently ignored otherwise."""
    with pytest.raises(ValidationFailed) as exc:
        planning.create_planned(
            db,
            user=user,
            account_id=bank_account.id,
            destination_account_id=savings_account.id,
            planned_type=PlannedType.EXPENSE,
            amount=Decimal("1000"),
            expected_at=SOON,
            description="Rent",
        )
    assert exc.value.code == "DESTINATION_NOT_APPLICABLE"


def test_transfer_to_the_same_account_is_refused(db, bank_account, user):
    with pytest.raises(ValidationFailed):
        _planned_transfer(db, user, bank_account, bank_account)


def test_cannot_transfer_to_another_users_account(db, bank_account, user, other_user):
    from app.core.errors import NotFound
    from app.db.enums import AccountType
    from app.services.accounts import create_account

    theirs = create_account(
        db,
        user=other_user,
        name="Theirs",
        account_type=AccountType.CHECKING,
        currency="RWF",
        opening_balance=Decimal("100"),
        opening_balance_at=SOON,
    )
    db.commit()
    with pytest.raises(NotFound):
        _planned_transfer(db, user, bank_account, theirs)


# ------------------------------------------------------- planned is not posted


def test_planning_a_transfer_moves_no_money(db, bank_account, savings_account, user):
    _planned_transfer(db, user, bank_account, savings_account)
    db.commit()
    posting = PostingService(db)
    assert posting.balance_of(bank_account) == Decimal("1000000.0000")
    assert posting.balance_of(savings_account) == Decimal("500000.0000")
    assert db.scalars(select(Transfer)).all() == []


# ------------------------------------------------------------------ completion


def test_completing_a_planned_transfer_creates_a_real_transfer(
    db, bank_account, savings_account, user
):
    planned = _planned_transfer(db, user, bank_account, savings_account)
    db.commit()
    planning.complete_planned(db, user=user, planned_id=planned.id)
    db.commit()

    posting = PostingService(db)
    assert posting.balance_of(bank_account) == Decimal("900000.0000")
    assert posting.balance_of(savings_account) == Decimal("600000.0000")

    transfer = db.scalars(select(Transfer)).one()
    assert planned.completed_transfer_id == transfer.id
    assert planned.status is PlannedStatus.COMPLETED
    # Linked as a transfer, not squeezed into the single-transaction column.
    assert planned.completed_transaction_id is None


def test_completed_transfer_writes_two_linked_entries(db, bank_account, savings_account, user):
    planned = _planned_transfer(db, user, bank_account, savings_account)
    db.commit()
    planning.complete_planned(db, user=user, planned_id=planned.id)
    db.commit()

    sides = db.scalars(
        select(Transaction).where(Transaction.transfer_id == planned.completed_transfer_id)
    ).all()
    assert len(sides) == 2
    assert {s.transaction_type for s in sides} == {TransactionType.TRANSFER}
    by_account = {s.account_id: s.direction for s in sides}
    assert by_account[bank_account.id] is Direction.DECREASE
    assert by_account[savings_account.id] is Direction.INCREASE


def test_completed_transfer_is_not_an_expense(db, bank_account, savings_account, user):
    planned = _planned_transfer(db, user, bank_account, savings_account)
    db.commit()
    planning.complete_planned(db, user=user, planned_id=planned.id)
    db.commit()

    expenses = db.scalars(
        select(Transaction).where(Transaction.transaction_type == TransactionType.EXPENSE)
    ).all()
    assert expenses == []


def test_completed_transfer_preserves_net_worth(db, bank_account, savings_account, user):
    planned = _planned_transfer(db, user, bank_account, savings_account)
    db.commit()
    posting = PostingService(db)
    before = posting.net_worth_contribution(bank_account) + posting.net_worth_contribution(
        savings_account
    )
    planning.complete_planned(db, user=user, planned_id=planned.id)
    db.commit()
    after = posting.net_worth_contribution(bank_account) + posting.net_worth_contribution(
        savings_account
    )
    assert before == after


def test_transfer_to_a_credit_card_lowers_debt(db, bank_account, credit_card, user):
    """Direction still comes from account nature, so a planned card payment
    behaves exactly like a manual one."""
    planned = _planned_transfer(
        db,
        user,
        bank_account,
        credit_card,
        amount=Decimal("150000"),
        description="Card payment",
    )
    db.commit()
    planning.complete_planned(db, user=user, planned_id=planned.id)
    db.commit()

    posting = PostingService(db)
    assert posting.balance_of(credit_card) == Decimal("50000.0000")
    assert posting.balance_of(bank_account) == Decimal("850000.0000")


def test_completing_a_transfer_twice_is_refused(db, bank_account, savings_account, user):
    from app.core.errors import Conflict

    planned = _planned_transfer(db, user, bank_account, savings_account)
    db.commit()
    planning.complete_planned(db, user=user, planned_id=planned.id)
    db.commit()
    with pytest.raises(Conflict):
        planning.complete_planned(db, user=user, planned_id=planned.id)
    # And no second transfer.
    assert len(db.scalars(select(Transfer)).all()) == 1


# ------------------------------------------------------------------ recurrence


def test_recurring_transfer_generates_occurrences(db, bank_account, savings_account, user):
    rule = planning.create_rule(
        db,
        user=user,
        account_id=bank_account.id,
        destination_account_id=savings_account.id,
        planned_type=PlannedType.TRANSFER,
        amount=Decimal("50000"),
        name="Monthly savings",
        frequency=Frequency.MONTHLY,
        start_date=date(2026, 8, 26),
    )
    db.commit()
    created = planning.generate_occurrences(db, rule, owner=user, today=date(2026, 8, 24))
    db.commit()

    assert len(created) >= 3
    # Each occurrence carries the destination through from the rule.
    assert all(p.destination_account_id == savings_account.id for p in created)
    assert all(p.planned_type is PlannedType.TRANSFER for p in created)
    # Still nothing posted.
    assert db.scalars(select(Transfer)).all() == []


def test_recurring_transfer_rule_requires_a_destination(db, bank_account, user):
    with pytest.raises(ValidationFailed) as exc:
        planning.create_rule(
            db,
            user=user,
            account_id=bank_account.id,
            planned_type=PlannedType.TRANSFER,
            amount=Decimal("1000"),
            name="Nowhere",
            frequency=Frequency.MONTHLY,
            start_date=date(2026, 8, 26),
        )
    assert exc.value.code == "DESTINATION_REQUIRED"


def test_generated_transfer_occurrence_completes_correctly(db, bank_account, savings_account, user):
    rule = planning.create_rule(
        db,
        user=user,
        account_id=bank_account.id,
        destination_account_id=savings_account.id,
        planned_type=PlannedType.TRANSFER,
        amount=Decimal("50000"),
        name="Monthly savings",
        frequency=Frequency.MONTHLY,
        start_date=date(2026, 8, 26),
    )
    db.commit()
    planning.generate_occurrences(db, rule, owner=user, today=date(2026, 8, 24))
    db.commit()

    first = db.scalars(select(PlannedTransaction).order_by(PlannedTransaction.expected_at)).first()
    planning.complete_planned(db, user=user, planned_id=first.id)
    db.commit()

    posting = PostingService(db)
    assert posting.balance_of(bank_account) == Decimal("950000.0000")
    assert posting.balance_of(savings_account) == Decimal("550000.0000")


def test_serialized_transfer_names_both_sides(db, bank_account, savings_account, user):
    _planned_transfer(db, user, bank_account, savings_account)
    db.commit()
    rows = planning.list_planned(db, user=user)
    payload = planning.serialize_planned(rows[0], timezone_name="UTC", today=date(2026, 9, 1))
    assert payload["planned_type"] == "TRANSFER"
    assert payload["account"]["name"] == "BK Current"
    assert payload["destination_account"]["name"] == "BK Savings"
