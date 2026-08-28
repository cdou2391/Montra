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

    INCREASE raises the account's own balance: asset value for an ASSET,
    outstanding debt for a LIABILITY. Deliberately not debit/credit.
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


class GoalStatus(StrEnum):
    ACTIVE = "ACTIVE"
    # Reached its target. It stays visible until the owner archives it: the
    # money is still in the account, and a goal is a plan rather than a vault.
    ACHIEVED = "ACHIEVED"
    ARCHIVED = "ARCHIVED"


class BudgetStatus(StrEnum):
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class BudgetPeriod(StrEnum):
    """Only calendar months for now.

    Named as an enum rather than assumed, because a weekly or yearly budget is
    the same shape and the column should not have to change to allow one.
    """

    MONTHLY = "MONTHLY"


class InstitutionType(StrEnum):
    BANK = "BANK"
    MOBILE_MONEY = "MOBILE_MONEY"
    CARD_ISSUER = "CARD_ISSUER"
    OTHER = "OTHER"


# Account type to nature.
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
    GOAL = "GOAL"
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
    CARD_EXPIRING = "CARD_EXPIRING"
    LOAN_DUE = "LOAN_DUE"
    GOAL_ACHIEVED = "GOAL_ACHIEVED"
    # The goals on an account claim more than the account holds, which happens
    # when money is spent from it without being tagged against a goal.
    GOAL_SHORTFALL = "GOAL_SHORTFALL"
    SYSTEM = "SYSTEM"


# Terminal states are excluded, so a completed item cannot be rescheduled or
# completed twice.
OPEN_PLANNED_STATUSES = frozenset({PlannedStatus.UPCOMING, PlannedStatus.DUE, PlannedStatus.MISSED})


class LoanDirection(StrEnum):
    """PAYABLE is money you owe; RECEIVABLE is money owed to you."""

    PAYABLE = "PAYABLE"
    RECEIVABLE = "RECEIVABLE"


class LoanStatus(StrEnum):
    ACTIVE = "ACTIVE"
    SETTLED = "SETTLED"
    ARCHIVED = "ARCHIVED"


class FamilyStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class FamilyRole(StrEnum):
    """MEMBER is a reduced-permission household member, read-only for now."""

    OWNER = "OWNER"
    ADULT = "ADULT"
    MEMBER = "MEMBER"


class MembershipStatus(StrEnum):
    ACTIVE = "ACTIVE"
    LEFT = "LEFT"
    REMOVED = "REMOVED"


class InvitationStatus(StrEnum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    DECLINED = "DECLINED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


# Roles permitted to transact on a shared account.
TRANSACTING_ROLES = frozenset({FamilyRole.OWNER, FamilyRole.ADULT})
