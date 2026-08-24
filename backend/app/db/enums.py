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
