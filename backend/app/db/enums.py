"""Domain enumerations shared across models and schemas."""

from enum import StrEnum


class UserStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"


class Context(StrEnum):
    PERSONAL = "PERSONAL"
    FAMILY = "FAMILY"


class AccountType(StrEnum):
    CHECKING = "CHECKING"
    SAVINGS = "SAVINGS"
    CASH = "CASH"
    MOBILE_MONEY = "MOBILE_MONEY"
    CREDIT_CARD = "CREDIT_CARD"
    PREPAID_CARD = "PREPAID_CARD"
    INVESTMENT = "INVESTMENT"
    OTHER = "OTHER"


class AccountNature(StrEnum):
    ASSET = "ASSET"
    LIABILITY = "LIABILITY"


class OwnershipType(StrEnum):
    PERSONAL = "PERSONAL"
    JOINT = "JOINT"


class Visibility(StrEnum):
    PRIVATE = "PRIVATE"
    FAMILY_VISIBLE = "FAMILY_VISIBLE"
    SHARED = "SHARED"


class AccountStatus(StrEnum):
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class TransactionType(StrEnum):
    INCOME = "INCOME"
    EXPENSE = "EXPENSE"
    TRANSFER = "TRANSFER"
    ADJUSTMENT = "ADJUSTMENT"


class Direction(StrEnum):
    """Ledger effect, relative to the account's own balance scale.

    Data Model section 19/20: INCREASE raises the account's own balance —
    asset value for an ASSET account, outstanding debt for a LIABILITY account.
    This is deliberately not double-entry debit/credit.
    """

    INCREASE = "INCREASE"
    DECREASE = "DECREASE"


class TransactionStatus(StrEnum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class TransferStatus(StrEnum):
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class CategoryType(StrEnum):
    INCOME = "INCOME"
    EXPENSE = "EXPENSE"


class CategoryStatus(StrEnum):
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class InstitutionType(StrEnum):
    BANK = "BANK"
    MOBILE_MONEY = "MOBILE_MONEY"
    CARD_ISSUER = "CARD_ISSUER"
    OTHER = "OTHER"


# Account type to nature, per Data Model section 73.
ACCOUNT_NATURE_BY_TYPE: dict[AccountType, AccountNature] = {
    AccountType.CHECKING: AccountNature.ASSET,
    AccountType.SAVINGS: AccountNature.ASSET,
    AccountType.CASH: AccountNature.ASSET,
    AccountType.MOBILE_MONEY: AccountNature.ASSET,
    AccountType.PREPAID_CARD: AccountNature.ASSET,
    AccountType.INVESTMENT: AccountNature.ASSET,
    AccountType.CREDIT_CARD: AccountNature.LIABILITY,
    AccountType.OTHER: AccountNature.ASSET,
}


def nature_for(account_type: AccountType) -> AccountNature:
    return ACCOUNT_NATURE_BY_TYPE[account_type]


class PlannedType(StrEnum):
    """Data Model section 76 anticipated TRANSFER here from the start."""

    INCOME = "INCOME"
    EXPENSE = "EXPENSE"
    TRANSFER = "TRANSFER"


class PlannedStatus(StrEnum):
    UPCOMING = "UPCOMING"
    DUE = "DUE"
    COMPLETED = "COMPLETED"
    MISSED = "MISSED"
    CANCELLED = "CANCELLED"
    SKIPPED = "SKIPPED"


class PlannedSource(StrEnum):
    ONE_TIME = "ONE_TIME"
    RECURRING = "RECURRING"


class Frequency(StrEnum):
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"
    QUARTERLY = "QUARTERLY"
    YEARLY = "YEARLY"


class RecurringStatus(StrEnum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    ENDED = "ENDED"


class ReminderEntity(StrEnum):
    PLANNED_TRANSACTION = "PLANNED_TRANSACTION"
    LOAN = "LOAN"
    CREDIT_CARD = "CREDIT_CARD"
    FAMILY_INVITATION = "FAMILY_INVITATION"


class ReminderStatus(StrEnum):
    PENDING = "PENDING"
    SENT = "SENT"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


class NotificationType(StrEnum):
    PLANNED_DUE = "PLANNED_DUE"
    PLANNED_OVERDUE = "PLANNED_OVERDUE"
    CARD_PAYMENT_DUE = "CARD_PAYMENT_DUE"
    LOAN_DUE = "LOAN_DUE"
    SYSTEM = "SYSTEM"


# Statuses a planned item can still move on from. Terminal states are excluded
# so a completed item can never be rescheduled or completed twice.
OPEN_PLANNED_STATUSES = frozenset({PlannedStatus.UPCOMING, PlannedStatus.DUE, PlannedStatus.MISSED})


class LoanDirection(StrEnum):
    """PAYABLE is money you owe; RECEIVABLE is money owed to you."""

    PAYABLE = "PAYABLE"
    RECEIVABLE = "RECEIVABLE"


class LoanStatus(StrEnum):
    ACTIVE = "ACTIVE"
    SETTLED = "SETTLED"
    ARCHIVED = "ARCHIVED"
