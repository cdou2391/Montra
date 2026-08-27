"""Loans.

The plan names the properties directly:

    Payable                     Receivable
    Cash down                   Cash up
    Liability principal down    Receivable principal down
    Interest -> Expense         Interest -> Income
    Fees -> Expense

The trap this suite exists to catch: treating the whole payment as spending.
Only interest and fees are spending; principal settles a debt already carried.
"""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.errors import Conflict, ValidationFailed
from app.db.enums import LoanDirection, LoanStatus, TransactionType
from app.models.finance import Transaction
from app.services import loans as loan_service
from app.services.posting import PostingService

WHEN = datetime(2026, 8, 28, 12, 0, tzinfo=UTC)
PAY_DATE = date(2026, 8, 28)


def _loan(db, user, **kw):
    return loan_service.create_loan(
        db,
        user=user,
        name=kw.pop("name", "Car Loan"),
        direction=kw.pop("direction", LoanDirection.PAYABLE),
        currency="RWF",
        original_principal=kw.pop("original_principal", Decimal("18000000")),
        opening_outstanding_principal=kw.pop("opening", Decimal("11850000")),
        start_date=kw.pop("start_date", date(2025, 1, 1)),
        **kw,
    )


def _totals(db, user_id, txn_type: TransactionType) -> Decimal:
    rows = db.scalars(
        select(Transaction.amount).where(
            Transaction.created_by == user_id,
            Transaction.transaction_type == txn_type,
            Transaction.deleted_at.is_(None),
        )
    ).all()
    return sum(rows, Decimal("0"))


# --------------------------------------------------------------- payable rules


def test_payable_payment_moves_cash_and_principal(db, bank_account, user):
    loan = _loan(db, user)
    db.commit()
    loan_service.record_payment(
        db,
        user=user,
        loan=loan,
        account_id=bank_account.id,
        total_amount=Decimal("750000"),
        principal_amount=Decimal("650000"),
        interest_amount=Decimal("90000"),
        fee_amount=Decimal("10000"),
        payment_date=PAY_DATE,
        occurred_at=WHEN,
    )
    db.commit()

    # Cash falls by the whole payment.
    assert PostingService(db).balance_of(bank_account) == Decimal("250000.0000")
    # The loan falls by the principal portion only.
    assert loan_service.outstanding_principal(db, loan) == Decimal("11200000.0000")


def test_payable_interest_and_fees_are_expenses_but_principal_is_not(db, bank_account, user):
    """The property most easily got wrong: a repayment is not all spending."""
    loan = _loan(db, user)
    db.commit()
    loan_service.record_payment(
        db,
        user=user,
        loan=loan,
        account_id=bank_account.id,
        total_amount=Decimal("750000"),
        principal_amount=Decimal("650000"),
        interest_amount=Decimal("90000"),
        fee_amount=Decimal("10000"),
        payment_date=PAY_DATE,
        occurred_at=WHEN,
    )
    db.commit()

    # Only interest + fees count as spending.
    assert _totals(db, user.id, TransactionType.EXPENSE) == Decimal("100000.0000")
    # The principal moved as a transfer, not an expense.
    assert _totals(db, user.id, TransactionType.TRANSFER) == Decimal("650000.0000")
    assert _totals(db, user.id, TransactionType.INCOME) == Decimal("0")


def test_payable_payment_of_pure_principal_records_no_expense(db, bank_account, user):
    loan = _loan(db, user)
    db.commit()
    loan_service.record_payment(
        db,
        user=user,
        loan=loan,
        account_id=bank_account.id,
        total_amount=Decimal("500000"),
        principal_amount=Decimal("500000"),
        payment_date=PAY_DATE,
        occurred_at=WHEN,
    )
    db.commit()
    assert _totals(db, user.id, TransactionType.EXPENSE) == Decimal("0")
    assert PostingService(db).balance_of(bank_account) == Decimal("500000.0000")


def test_payable_principal_repayment_preserves_net_worth(db, bank_account, user):
    """Cash down, debt down by the same amount: no wealth created or destroyed."""
    loan = _loan(db, user, opening=Decimal("500000"))
    db.commit()
    posting = PostingService(db)
    before = posting.net_worth_contribution(bank_account) + loan_service.net_worth_contribution(
        db, loan
    )

    loan_service.record_payment(
        db,
        user=user,
        loan=loan,
        account_id=bank_account.id,
        total_amount=Decimal("200000"),
        principal_amount=Decimal("200000"),
        payment_date=PAY_DATE,
        occurred_at=WHEN,
    )
    db.commit()

    after = posting.net_worth_contribution(bank_account) + loan_service.net_worth_contribution(
        db, loan
    )
    assert before == after


def test_interest_reduces_net_worth(db, bank_account, user):
    """Unlike principal, interest is a genuine loss."""
    loan = _loan(db, user, opening=Decimal("500000"))
    db.commit()
    posting = PostingService(db)
    before = posting.net_worth_contribution(bank_account) + loan_service.net_worth_contribution(
        db, loan
    )
    loan_service.record_payment(
        db,
        user=user,
        loan=loan,
        account_id=bank_account.id,
        total_amount=Decimal("100000"),
        principal_amount=Decimal("90000"),
        interest_amount=Decimal("10000"),
        payment_date=PAY_DATE,
        occurred_at=WHEN,
    )
    db.commit()
    after = posting.net_worth_contribution(bank_account) + loan_service.net_worth_contribution(
        db, loan
    )
    assert after == before - Decimal("10000.0000")


# ------------------------------------------------------------ receivable rules


def test_receivable_payment_raises_cash_and_lowers_receivable(db, bank_account, user):
    loan = _loan(
        db,
        user,
        name="Loan to Jean",
        direction=LoanDirection.RECEIVABLE,
        original_principal=Decimal("300000"),
        opening=Decimal("300000"),
    )
    db.commit()
    loan_service.record_payment(
        db,
        user=user,
        loan=loan,
        account_id=bank_account.id,
        total_amount=Decimal("110000"),
        principal_amount=Decimal("100000"),
        interest_amount=Decimal("10000"),
        payment_date=PAY_DATE,
        occurred_at=WHEN,
    )
    db.commit()

    assert PostingService(db).balance_of(bank_account) == Decimal("1110000.0000")
    assert loan_service.outstanding_principal(db, loan) == Decimal("200000.0000")


def test_receivable_interest_is_income_and_principal_is_not(db, bank_account, user):
    loan = _loan(
        db,
        user,
        direction=LoanDirection.RECEIVABLE,
        original_principal=Decimal("300000"),
        opening=Decimal("300000"),
    )
    db.commit()
    loan_service.record_payment(
        db,
        user=user,
        loan=loan,
        account_id=bank_account.id,
        total_amount=Decimal("110000"),
        principal_amount=Decimal("100000"),
        interest_amount=Decimal("10000"),
        payment_date=PAY_DATE,
        occurred_at=WHEN,
    )
    db.commit()

    # Getting your own money back is not earnings; the interest on it is.
    assert _totals(db, user.id, TransactionType.INCOME) == Decimal("10000.0000")
    assert _totals(db, user.id, TransactionType.TRANSFER) == Decimal("100000.0000")
    assert _totals(db, user.id, TransactionType.EXPENSE) == Decimal("0")


def test_receivable_counts_as_an_asset_in_net_worth(db, user):
    payable = _loan(db, user, opening=Decimal("400000"))
    receivable = _loan(
        db,
        user,
        name="Loan to Jean",
        direction=LoanDirection.RECEIVABLE,
        original_principal=Decimal("300000"),
        opening=Decimal("300000"),
    )
    db.commit()
    assert loan_service.net_worth_contribution(db, payable) == Decimal("-400000.0000")
    assert loan_service.net_worth_contribution(db, receivable) == Decimal("300000.0000")


# ----------------------------------------------------------------- allocation


def test_allocation_must_add_up(db, bank_account, user):
    loan = _loan(db, user)
    db.commit()
    with pytest.raises(ValidationFailed) as exc:
        loan_service.record_payment(
            db,
            user=user,
            loan=loan,
            account_id=bank_account.id,
            total_amount=Decimal("750000"),
            principal_amount=Decimal("650000"),
            interest_amount=Decimal("50000"),  # 50k short
            payment_date=PAY_DATE,
            occurred_at=WHEN,
        )
    assert exc.value.code == "ALLOCATION_MISMATCH"


def test_mismatched_allocation_is_refused_by_the_database(db, bank_account, user):
    """The service check is a convenience; the constraint is the real guard."""
    from sqlalchemy.exc import IntegrityError

    from app.models.loans import LoanPayment

    loan = _loan(db, user)
    db.commit()
    db.add(
        LoanPayment(
            loan_id=loan.id,
            account_id=bank_account.id,
            payment_date=PAY_DATE,
            total_amount=Decimal("100"),
            principal_amount=Decimal("50"),
            interest_amount=Decimal("10"),
            fee_amount=Decimal("0"),
            created_by=user.id,
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_cannot_pay_more_principal_than_remains(db, bank_account, user):
    loan = _loan(db, user, original_principal=Decimal("100000"), opening=Decimal("100000"))
    db.commit()
    with pytest.raises(ValidationFailed) as exc:
        loan_service.record_payment(
            db,
            user=user,
            loan=loan,
            account_id=bank_account.id,
            total_amount=Decimal("150000"),
            principal_amount=Decimal("150000"),
            payment_date=PAY_DATE,
            occurred_at=WHEN,
        )
    assert exc.value.code == "PRINCIPAL_EXCEEDS_OUTSTANDING"


def test_payment_must_come_from_an_asset_account(db, credit_card, user):
    loan = _loan(db, user)
    db.commit()
    with pytest.raises(ValidationFailed) as exc:
        loan_service.record_payment(
            db,
            user=user,
            loan=loan,
            account_id=credit_card.id,
            total_amount=Decimal("1000"),
            principal_amount=Decimal("1000"),
            payment_date=PAY_DATE,
            occurred_at=WHEN,
        )
    assert exc.value.code == "INVALID_PAYMENT_ACCOUNT"


# -------------------------------------------------------------------- balance


def test_outstanding_is_derived_never_overwritten(db, bank_account, user):
    """Data Model section 33: the original loan amount is never rewritten."""
    loan = _loan(db, user, original_principal=Decimal("100000"), opening=Decimal("100000"))
    db.commit()
    for _ in range(4):
        loan_service.record_payment(
            db,
            user=user,
            loan=loan,
            account_id=bank_account.id,
            total_amount=Decimal("10000"),
            principal_amount=Decimal("10000"),
            payment_date=PAY_DATE,
            occurred_at=WHEN,
        )
    db.commit()
    assert loan_service.outstanding_principal(db, loan) == Decimal("60000.0000")
    assert loan.original_principal == Decimal("100000.0000")
    assert loan.opening_outstanding_principal == Decimal("100000.0000")


def test_loan_settles_when_fully_repaid(db, bank_account, user):
    loan = _loan(db, user, original_principal=Decimal("50000"), opening=Decimal("50000"))
    db.commit()
    loan_service.record_payment(
        db,
        user=user,
        loan=loan,
        account_id=bank_account.id,
        total_amount=Decimal("50000"),
        principal_amount=Decimal("50000"),
        payment_date=PAY_DATE,
        occurred_at=WHEN,
    )
    db.commit()
    assert loan_service.outstanding_principal(db, loan) == Decimal("0.0000")
    assert loan.status is LoanStatus.SETTLED


def test_progress_reflects_a_loan_taken_on_part_way_through(db, user):
    """Opening outstanding below the original means some was already paid."""
    loan = _loan(db, user, original_principal=Decimal("18000000"), opening=Decimal("11850000"))
    db.commit()
    payload = loan_service.serialize_loan(db, loan)
    assert payload["outstanding_principal"] == "11850000.00"
    assert payload["principal_paid"] == "6150000.00"
    assert payload["percent_paid"] == "34.17"


# ----------------------------------------------------------------- guardrails


def test_family_visibility_is_refused_until_family_ships(db, user):
    from app.db.enums import Visibility

    with pytest.raises(ValidationFailed) as exc:
        _loan(db, user, visibility=Visibility.FAMILY_VISIBLE)
    assert exc.value.code == "NO_ACTIVE_FAMILY"


def test_outstanding_cannot_exceed_original(db, user):
    with pytest.raises(ValidationFailed):
        _loan(db, user, original_principal=Decimal("100"), opening=Decimal("200"))


def test_archived_loan_refuses_payments(db, bank_account, user):
    loan = _loan(db, user)
    db.commit()
    loan_service.archive_loan(db, loan)
    db.commit()
    with pytest.raises(Conflict) as exc:
        loan_service.record_payment(
            db,
            user=user,
            loan=loan,
            account_id=bank_account.id,
            total_amount=Decimal("1000"),
            principal_amount=Decimal("1000"),
            payment_date=PAY_DATE,
            occurred_at=WHEN,
        )
    assert exc.value.code == "LOAN_ARCHIVED"


def test_another_user_cannot_see_a_loan(db, user, other_user):
    loan = _loan(db, user)
    db.commit()
    from app.core.errors import NotFound

    with pytest.raises(NotFound):
        loan_service.get_loan(db, loan.id, other_user)
    assert loan_service.list_loans(db, user=other_user) == []
