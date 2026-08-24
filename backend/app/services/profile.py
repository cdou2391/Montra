"""Profile reset.

Not in the API specification — added on request. It wipes a user's financial
data while keeping their login, which is the difference between "start over"
and "delete my account".

The operation is irreversible, so it is deliberately awkward: it requires the
account password, and it reports exactly what it is about to destroy before
it does so.
"""

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session as DbSession

from app.core.errors import InvalidCredentials
from app.core.security import verify_password
from app.models.finance import Account, Category, Institution, Transaction, Transfer
from app.models.loans import Loan, LoanPayment
from app.models.planning import Notification, PlannedTransaction, RecurringRule, Reminder
from app.models.user import User, UserPreference
from app.services.categories import create_default_categories


def _count(db: DbSession, model, *conditions) -> int:
    return int(db.scalar(select(func.count()).select_from(model).where(*conditions)) or 0)


def reset_summary(db: DbSession, user: User) -> dict:
    """What a reset would destroy.

    A warning that names real numbers is a warning; "this cannot be undone" on
    its own is wallpaper.
    """
    account_ids = select(Account.id).where(Account.owner_user_id == user.id)
    return {
        "accounts": _count(db, Account, Account.owner_user_id == user.id),
        "transactions": _count(db, Transaction, Transaction.account_id.in_(account_ids)),
        "transfers": _count(db, Transfer, Transfer.created_by == user.id),
        "loans": _count(db, Loan, Loan.owner_user_id == user.id),
        "loan_payments": _count(db, LoanPayment, LoanPayment.created_by == user.id),
        "planned_transactions": _count(
            db, PlannedTransaction, PlannedTransaction.created_by == user.id
        ),
        "recurring_rules": _count(db, RecurringRule, RecurringRule.created_by == user.id),
        "notifications": _count(db, Notification, Notification.user_id == user.id),
        "custom_categories": _count(
            db,
            Category,
            Category.user_id == user.id,
            Category.is_system.is_(False),
        ),
    }


def reset_profile(db: DbSession, *, user: User, password: str) -> dict:
    """Delete every financial record this user owns and start them fresh.

    Re-authentication is required: a borrowed session should not be able to
    destroy someone's history. Caller owns the surrounding database
    transaction, so a failure part-way leaves nothing deleted.
    """
    if not verify_password(user.password_hash, password):
        raise InvalidCredentials("That password is not correct.")

    summary = reset_summary(db, user)
    account_ids = select(Account.id).where(Account.owner_user_id == user.id)

    # Order matters: rows are removed before whatever they point at, so no
    # RESTRICT foreign key ever blocks the delete.
    db.execute(delete(PlannedTransaction).where(PlannedTransaction.created_by == user.id))
    db.execute(delete(RecurringRule).where(RecurringRule.created_by == user.id))
    db.execute(delete(Reminder).where(Reminder.user_id == user.id))
    db.execute(delete(Notification).where(Notification.user_id == user.id))
    db.execute(delete(Transaction).where(Transaction.account_id.in_(account_ids)))
    db.execute(delete(LoanPayment).where(LoanPayment.created_by == user.id))
    db.execute(delete(Loan).where(Loan.owner_user_id == user.id))
    db.execute(delete(Transfer).where(Transfer.created_by == user.id))
    db.execute(delete(Account).where(Account.owner_user_id == user.id))
    db.execute(delete(Institution).where(Institution.user_id == user.id))
    db.execute(delete(Category).where(Category.user_id == user.id))
    db.flush()

    # A fresh start means the defaults a new account would get.
    create_default_categories(db, user_id=user.id)

    preferences = db.scalar(select(UserPreference).where(UserPreference.user_id == user.id))
    if preferences is not None:
        preferences.hide_balances = False
        preferences.persist_balance_privacy = False
        preferences.default_reminder_days = 3
        preferences.notifications_enabled = True

    db.flush()
    return summary
