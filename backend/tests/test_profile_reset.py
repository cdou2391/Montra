"""Profile reset.

Irreversible, so the tests care about two things: that it removes exactly what
it claims, and that it cannot be triggered without the account password.
"""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.errors import InvalidCredentials
from app.db.enums import CategoryType, LoanDirection, NotificationType, PlannedType
from app.models.finance import Account, Category, Transaction, Transfer
from app.models.loans import Loan
from app.models.planning import Notification, PlannedTransaction, Reminder
from app.models.user import User, UserPreference
from app.services import loans as loan_service
from app.services import planning, profile
from app.services.posting import PostingService

PASSWORD = "correct horse battery"
NOW = datetime(2026, 8, 24, 12, 0, tzinfo=UTC)


def _populate(db, user, bank_account, savings_account, credit_card):
    posting = PostingService(db)
    posting.record_expense(
        account=bank_account,
        amount=Decimal("5000"),
        currency="RWF",
        occurred_at=NOW,
        actor_id=user.id,
    )
    posting.transfer_funds(
        source=bank_account,
        destination=savings_account,
        source_amount=Decimal("1000"),
        destination_amount=Decimal("1000"),
        occurred_at=NOW,
        actor_id=user.id,
    )
    planning.create_planned(
        db,
        user=user,
        account_id=bank_account.id,
        planned_type=PlannedType.EXPENSE,
        amount=Decimal("2000"),
        expected_at=NOW,
        description="Rent",
        reminder_days_before=3,
    )
    loan = loan_service.create_loan(
        db,
        user=user,
        name="Car Loan",
        direction=LoanDirection.PAYABLE,
        currency="RWF",
        original_principal=Decimal("100000"),
        opening_outstanding_principal=Decimal("100000"),
        start_date=date(2026, 1, 1),
    )
    loan_service.record_payment(
        db,
        user=user,
        loan=loan,
        account_id=bank_account.id,
        total_amount=Decimal("10000"),
        principal_amount=Decimal("10000"),
        payment_date=date(2026, 8, 24),
        occurred_at=NOW,
    )
    db.add(
        Category(
            user_id=user.id, name="Custom", category_type=CategoryType.EXPENSE, is_system=False
        )
    )
    planning.notify(
        db,
        user_id=user.id,
        notification_type=NotificationType.SYSTEM,
        title="Hello",
        body="body",
    )
    db.commit()


def test_summary_counts_what_would_be_deleted(db, user, bank_account, savings_account, credit_card):
    _populate(db, user, bank_account, savings_account, credit_card)
    summary = profile.reset_summary(db, user)

    assert summary["accounts"] == 3
    assert summary["loans"] == 1
    assert summary["loan_payments"] == 1
    assert summary["planned_transactions"] == 1
    assert summary["custom_categories"] == 1
    assert summary["transactions"] > 0
    assert summary["transfers"] == 1


def test_reset_removes_every_financial_record(db, user, bank_account, savings_account, credit_card):
    _populate(db, user, bank_account, savings_account, credit_card)
    profile.reset_profile(db, user=user, password=PASSWORD)
    db.commit()

    for model in (Account, Transaction, Transfer, Loan, PlannedTransaction, Notification):
        assert db.scalars(select(model)).all() == [], model.__name__
    assert db.scalars(select(Reminder)).all() == []


def test_reset_keeps_the_login(db, user, bank_account):
    profile.reset_profile(db, user=user, password=PASSWORD)
    db.commit()
    # This is "start over", not "delete my account".
    still_there = db.scalar(select(User).where(User.id == user.id))
    assert still_there is not None
    assert still_there.email == user.email


def test_reset_restores_default_categories(db, user, bank_account):
    db.add(
        Category(
            user_id=user.id, name="Custom", category_type=CategoryType.EXPENSE, is_system=False
        )
    )
    db.commit()

    profile.reset_profile(db, user=user, password=PASSWORD)
    db.commit()

    categories = db.scalars(select(Category).where(Category.user_id == user.id)).all()
    assert len(categories) == 29
    assert all(c.is_system for c in categories)


def test_reset_restores_default_preferences(db, user):
    prefs = db.scalar(select(UserPreference).where(UserPreference.user_id == user.id))
    prefs.hide_balances = True
    prefs.notifications_enabled = False
    db.commit()

    profile.reset_profile(db, user=user, password=PASSWORD)
    db.commit()
    db.refresh(prefs)
    assert prefs.hide_balances is False
    assert prefs.notifications_enabled is True


def test_reset_requires_the_correct_password(db, user, bank_account):
    with pytest.raises(InvalidCredentials):
        profile.reset_profile(db, user=user, password="not the password")
    db.rollback()
    # Nothing was destroyed on a failed attempt.
    assert db.scalars(select(Account)).all() != []


def test_reset_does_not_touch_another_user(db, user, other_user, bank_account):
    from app.db.enums import AccountType
    from app.services.accounts import create_account

    theirs = create_account(
        db,
        user=other_user,
        name="Their Account",
        account_type=AccountType.CHECKING,
        currency="RWF",
        opening_balance=Decimal("500"),
        opening_balance_at=NOW,
    )
    db.commit()

    profile.reset_profile(db, user=user, password=PASSWORD)
    db.commit()

    survivors = db.scalars(select(Account)).all()
    assert [a.id for a in survivors] == [theirs.id]
    assert db.scalars(select(Category).where(Category.user_id == other_user.id)).all() != []
