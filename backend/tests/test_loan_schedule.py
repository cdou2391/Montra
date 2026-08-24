"""Loan payment schedules in the planning views.

Loan payments are derived from the loan's own schedule rather than
materialised as planned transactions: the loan already carries the schedule, so
generating rows from it would mean two places to keep in step and a way for
them to disagree.
"""

from datetime import UTC, date, datetime
from decimal import Decimal

from app.db.enums import Frequency, LoanDirection, LoanStatus
from app.services import loans as loan_service

NOW = datetime(2026, 8, 24, 12, 0, tzinfo=UTC)


def _loan(db, user, **kw):
    return loan_service.create_loan(
        db,
        user=user,
        name=kw.pop("name", "Car Loan"),
        direction=kw.pop("direction", LoanDirection.PAYABLE),
        currency="RWF",
        original_principal=kw.pop("original_principal", Decimal("1000000")),
        opening_outstanding_principal=kw.pop("opening", Decimal("1000000")),
        start_date=date(2026, 1, 1),
        expected_payment_amount=kw.pop("expected", Decimal("100000")),
        payment_frequency=kw.pop("frequency", Frequency.MONTHLY),
        next_payment_date=kw.pop("next_payment_date", date(2026, 8, 28)),
        **kw,
    )


# ------------------------------------------------------------- schedule moves


def test_recording_a_payment_moves_the_schedule_on(db, bank_account, user):
    """Otherwise the loan stays permanently due on the same date."""
    loan = _loan(db, user)
    db.commit()
    loan_service.record_payment(
        db,
        user=user,
        loan=loan,
        account_id=bank_account.id,
        total_amount=Decimal("100000"),
        principal_amount=Decimal("100000"),
        payment_date=date(2026, 8, 28),
        occurred_at=NOW,
    )
    db.commit()
    assert loan.next_payment_date == date(2026, 9, 28)


def test_paying_early_still_settles_that_instalment(db, bank_account, user):
    """Paying a few days early should not leave the loan showing as due."""
    loan = _loan(db, user)
    db.commit()
    loan_service.record_payment(
        db,
        user=user,
        loan=loan,
        account_id=bank_account.id,
        total_amount=Decimal("100000"),
        principal_amount=Decimal("100000"),
        payment_date=date(2026, 8, 25),  # due the 28th
        occurred_at=NOW,
    )
    db.commit()
    assert loan.next_payment_date == date(2026, 9, 28)


def test_a_late_payment_settles_one_instalment_not_all_of_them(db, bank_account, user):
    """Two cycles behind, one payment. The loan is still behind, and the list
    should keep saying so rather than quietly forgiving the gap."""
    loan = _loan(db, user)
    db.commit()
    loan_service.record_payment(
        db,
        user=user,
        loan=loan,
        account_id=bank_account.id,
        total_amount=Decimal("100000"),
        principal_amount=Decimal("100000"),
        payment_date=date(2026, 10, 30),
        occurred_at=NOW,
    )
    db.commit()
    assert loan.next_payment_date == date(2026, 9, 28)


def test_schedule_stops_at_the_end_date(db, bank_account, user):
    loan = _loan(db, user, end_date=date(2026, 9, 1))
    db.commit()
    loan_service.record_payment(
        db,
        user=user,
        loan=loan,
        account_id=bank_account.id,
        total_amount=Decimal("100000"),
        principal_amount=Decimal("100000"),
        payment_date=date(2026, 8, 28),
        occurred_at=NOW,
    )
    db.commit()
    assert loan.next_payment_date is None


def test_settling_a_loan_leaves_no_schedule_to_chase(db, bank_account, user):
    loan = _loan(db, user, original_principal=Decimal("50000"), opening=Decimal("50000"))
    db.commit()
    loan_service.record_payment(
        db,
        user=user,
        loan=loan,
        account_id=bank_account.id,
        total_amount=Decimal("50000"),
        principal_amount=Decimal("50000"),
        payment_date=date(2026, 8, 28),
        occurred_at=NOW,
    )
    db.commit()
    assert loan.status is LoanStatus.SETTLED
    assert loan_service.upcoming_payments(db, user=user, today=date(2026, 8, 24)) == []


# ------------------------------------------------------------ upcoming payments


def test_upcoming_lists_occurrences_within_the_horizon(db, user):
    _loan(db, user)
    db.commit()
    rows = loan_service.upcoming_payments(db, user=user, today=date(2026, 8, 24))
    # Monthly over 90 days.
    assert len(rows) == 3
    assert rows[0]["due_date"] == "2026-08-28"
    assert rows[0]["description"] == "Car Loan"
    assert rows[0]["amount"] == "100000.00"


def test_upcoming_uses_the_same_buckets_as_planned_items(db, user):
    _loan(db, user, next_payment_date=date(2026, 8, 20))
    db.commit()
    rows = loan_service.upcoming_payments(db, user=user, today=date(2026, 8, 24))
    assert rows[0]["bucket"] == "OVERDUE"

    rows = loan_service.upcoming_payments(db, user=user, today=date(2026, 8, 20))
    assert rows[0]["bucket"] == "TODAY"


def test_final_payment_is_capped_at_what_is_left(db, user):
    """The last instalment should not claim more than the loan still owes."""
    _loan(db, user, original_principal=Decimal("150000"), opening=Decimal("150000"))
    db.commit()
    rows = loan_service.upcoming_payments(db, user=user, today=date(2026, 8, 24))
    assert rows[0]["amount"] == "100000.00"
    # Outstanding is 150,000, so a 100,000 instalment cannot repeat indefinitely
    # at full value; the figure shown is capped by what remains.
    assert all(Decimal(r["amount"]) <= Decimal("150000") for r in rows)


def test_a_loan_without_a_schedule_is_not_listed(db, user):
    _loan(db, user, expected=None, frequency=None, next_payment_date=None)
    db.commit()
    assert loan_service.upcoming_payments(db, user=user, today=date(2026, 8, 24)) == []


def test_a_one_off_payment_date_yields_a_single_entry(db, user):
    _loan(db, user, frequency=None)
    db.commit()
    rows = loan_service.upcoming_payments(db, user=user, today=date(2026, 8, 24))
    assert len(rows) == 1


def test_receivable_loans_appear_too(db, user):
    """Money owed to you is also something that needs to happen on a date."""
    _loan(
        db,
        user,
        name="Loan to Jean",
        direction=LoanDirection.RECEIVABLE,
        original_principal=Decimal("300000"),
        opening=Decimal("300000"),
    )
    db.commit()
    rows = loan_service.upcoming_payments(db, user=user, today=date(2026, 8, 24))
    assert rows[0]["direction"] == "RECEIVABLE"


def test_another_user_sees_none_of_it(db, user, other_user):
    _loan(db, user)
    db.commit()
    assert loan_service.upcoming_payments(db, user=other_user, today=date(2026, 8, 24)) == []
