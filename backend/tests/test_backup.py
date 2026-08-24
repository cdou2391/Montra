"""Backup and restore.

The property that matters: export then restore reproduces the same financial
position. A backup that loses a transaction is worse than no backup, because it
is trusted.
"""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.errors import InvalidCredentials, ValidationFailed
from app.db.enums import AccountType, LoanDirection, PlannedType
from app.models.finance import Account, Category, Transaction
from app.models.loans import Loan
from app.models.planning import PlannedTransaction
from app.services import backup, planning
from app.services import loans as loan_service
from app.services.accounts import create_account
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
        description="Groceries",
    )
    posting.record_income(
        account=bank_account,
        amount=Decimal("250000"),
        currency="RWF",
        occurred_at=NOW,
        actor_id=user.id,
        description="Salary",
    )
    posting.record_expense(
        account=credit_card,
        amount=Decimal("85000"),
        currency="RWF",
        occurred_at=NOW,
        actor_id=user.id,
        description="Card purchase",
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
        total_amount=Decimal("11000"),
        principal_amount=Decimal("10000"),
        interest_amount=Decimal("1000"),
        payment_date=date(2026, 8, 24),
        occurred_at=NOW,
    )
    db.commit()
    return loan


def test_export_captures_everything(db, user, bank_account, savings_account, credit_card):
    _populate(db, user, bank_account, savings_account, credit_card)
    payload = backup.export_backup(db, user)

    assert payload["montra_backup_version"] == 1
    assert len(payload["accounts"]) == 3
    assert len(payload["loans"]) == 1
    assert len(payload["transfers"]) == 1
    assert len(payload["planned_transactions"]) == 1
    assert len(payload["reminders"]) == 1
    assert len(payload["transactions"]) > 0


def test_export_never_includes_secrets(db, user, bank_account):
    payload = backup.export_backup(db, user)
    blob = str(payload)
    assert "password_hash" not in blob
    assert user.password_hash not in blob
    assert "token_hash" not in blob


def test_restore_reproduces_the_financial_position(
    db, user, bank_account, savings_account, credit_card
):
    """The property that matters: same balances, same loan, same everything."""
    loan = _populate(db, user, bank_account, savings_account, credit_card)
    posting = PostingService(db)
    before = {
        "bank": posting.balance_of(bank_account),
        "savings": posting.balance_of(savings_account),
        "card": posting.balance_of(credit_card),
        "loan": loan_service.outstanding_principal(db, loan),
    }
    payload = backup.export_backup(db, user)
    db.commit()

    backup.restore_backup(db, user=user, payload=payload, password=PASSWORD)
    db.commit()

    accounts = {a.name: a for a in db.scalars(select(Account))}
    restored_loan = db.scalars(select(Loan)).one()
    after = {
        "bank": posting.balance_of(accounts["BK Current"]),
        "savings": posting.balance_of(accounts["BK Savings"]),
        "card": posting.balance_of(accounts["BK Visa"]),
        "loan": loan_service.outstanding_principal(db, restored_loan),
    }
    assert after == before


def test_restore_regenerates_identifiers(db, user, bank_account):
    """Original ids would collide if a backup were restored elsewhere."""
    payload = backup.export_backup(db, user)
    original_ids = {a["id"] for a in payload["accounts"]}
    db.commit()

    backup.restore_backup(db, user=user, payload=payload, password=PASSWORD)
    db.commit()

    new_ids = {str(a.id) for a in db.scalars(select(Account))}
    assert new_ids.isdisjoint(original_ids)


def test_restore_into_a_different_account_works(db, user, other_user, bank_account):
    """A backup is portable: exporting from one account and restoring into
    another must not collide with the rows it came from."""
    PostingService(db).record_expense(
        account=bank_account,
        amount=Decimal("1000"),
        currency="RWF",
        occurred_at=NOW,
        actor_id=user.id,
        description="Coffee",
    )
    db.commit()
    payload = backup.export_backup(db, user)
    db.commit()

    backup.restore_backup(db, user=other_user, payload=payload, password="another good passphrase")
    db.commit()

    theirs = db.scalars(select(Account).where(Account.owner_user_id == other_user.id)).all()
    mine = db.scalars(select(Account).where(Account.owner_user_id == user.id)).all()
    assert len(theirs) == 1
    # The original owner still has their own copy.
    assert len(mine) == 1
    assert theirs[0].id != mine[0].id


def test_restore_replaces_rather_than_merges(db, user, bank_account):
    payload = backup.export_backup(db, user)
    db.commit()

    create_account(
        db,
        user=user,
        name="Added Later",
        account_type=AccountType.CASH,
        currency="RWF",
        opening_balance=Decimal("100"),
        opening_balance_at=NOW,
    )
    db.commit()
    assert len(db.scalars(select(Account)).all()) == 2

    backup.restore_backup(db, user=user, payload=payload, password=PASSWORD)
    db.commit()

    names = [a.name for a in db.scalars(select(Account))]
    assert names == ["BK Current"]


def test_restore_requires_the_password(db, user, bank_account):
    payload = backup.export_backup(db, user)
    db.commit()
    with pytest.raises(InvalidCredentials):
        backup.restore_backup(db, user=user, payload=payload, password="wrong")
    db.rollback()
    assert db.scalars(select(Account)).all() != []


def test_restore_rejects_a_foreign_file(db, user):
    with pytest.raises(ValidationFailed) as exc:
        backup.restore_backup(db, user=user, payload={"hello": "world"}, password=PASSWORD)
    assert exc.value.code == "UNSUPPORTED_BACKUP_VERSION"
    db.rollback()


def test_restore_rejects_a_future_version(db, user):
    with pytest.raises(ValidationFailed) as exc:
        backup.restore_backup(
            db, user=user, payload={"montra_backup_version": 99}, password=PASSWORD
        )
    assert exc.value.code == "UNSUPPORTED_BACKUP_VERSION"
    db.rollback()


def test_malformed_amount_is_refused_and_changes_nothing(db, user, bank_account):
    payload = backup.export_backup(db, user)
    payload["accounts"][0]["opening_balance"] = "not-a-number"
    db.commit()

    with pytest.raises(ValidationFailed) as exc:
        backup.restore_backup(db, user=user, payload=payload, password=PASSWORD)
    assert exc.value.code == "INVALID_BACKUP"
    db.rollback()
    # The transaction rolled back, so the original account is untouched.
    assert [a.name for a in db.scalars(select(Account))] == ["BK Current"]


def test_dangling_references_are_dropped_not_guessed(db, user, bank_account):
    """A transaction whose account is missing cannot be placed anywhere, so it
    is dropped rather than attached to some other account."""
    PostingService(db).record_expense(
        account=bank_account,
        amount=Decimal("1000"),
        currency="RWF",
        occurred_at=NOW,
        actor_id=user.id,
        description="Orphan",
    )
    db.commit()
    payload = backup.export_backup(db, user)
    payload["accounts"] = []  # every transaction now dangles
    db.commit()

    backup.restore_backup(db, user=user, payload=payload, password=PASSWORD)
    db.commit()
    assert db.scalars(select(Transaction)).all() == []


def test_restore_brings_back_categories_without_duplicating_defaults(db, user, bank_account):
    payload = backup.export_backup(db, user)
    db.commit()
    backup.restore_backup(db, user=user, payload=payload, password=PASSWORD)
    db.commit()
    categories = db.scalars(select(Category).where(Category.user_id == user.id)).all()
    # Exactly the backed-up set, not those plus a fresh default set.
    assert len(categories) == 29


def test_restore_preserves_planned_items_and_their_links(
    db, user, bank_account, savings_account, credit_card
):
    _populate(db, user, bank_account, savings_account, credit_card)
    payload = backup.export_backup(db, user)
    db.commit()
    backup.restore_backup(db, user=user, payload=payload, password=PASSWORD)
    db.commit()

    planned = db.scalars(select(PlannedTransaction)).one()
    assert planned.description == "Rent"
    # The link was remapped, not carried over stale.
    assert db.get(Account, planned.account_id) is not None
