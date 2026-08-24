from datetime import datetime
from decimal import Decimal

from pydantic import Field

from app.db.enums import AccountType, OwnershipType, Visibility
from app.schemas.common import MontraModel, amount_validator


class AccountCreate(MontraModel):
    name: str = Field(min_length=1, max_length=160)
    account_type: AccountType
    currency: str = Field(min_length=3, max_length=3)
    opening_balance: Decimal = Decimal("0")
    opening_balance_at: datetime
    institution_id: str | None = None
    account_identifier: str | None = Field(default=None, max_length=64)
    ownership_type: OwnershipType = OwnershipType.PERSONAL
    visibility: Visibility = Visibility.PRIVATE
    family_id: str | None = None
    description: str | None = None

    # Optional card metadata, rejected on non-card accounts by the service.
    credit_limit: Decimal | None = None
    statement_balance: Decimal | None = None
    statement_closing_day: int | None = Field(default=None, ge=1, le=31)
    payment_due_day: int | None = Field(default=None, ge=1, le=31)
    minimum_payment: Decimal | None = None
    interest_rate: Decimal | None = Field(default=None, ge=0, le=100)
    expiry_month: int | None = Field(default=None, ge=1, le=12)
    expiry_year: int | None = Field(default=None, ge=2000, le=2100)

    _v_opening = amount_validator("opening_balance")
    _v_limit = amount_validator("credit_limit")
    _v_statement = amount_validator("statement_balance")
    _v_minimum = amount_validator("minimum_payment")


class AccountUpdate(MontraModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = None
    institution_id: str | None = None
    account_identifier: str | None = Field(default=None, max_length=64)
    currency: str | None = Field(default=None, min_length=3, max_length=3)

    credit_limit: Decimal | None = None
    statement_balance: Decimal | None = None
    statement_closing_day: int | None = Field(default=None, ge=1, le=31)
    payment_due_day: int | None = Field(default=None, ge=1, le=31)
    minimum_payment: Decimal | None = None
    interest_rate: Decimal | None = Field(default=None, ge=0, le=100)
    expiry_month: int | None = Field(default=None, ge=1, le=12)
    expiry_year: int | None = Field(default=None, ge=2000, le=2100)

    _v_limit = amount_validator("credit_limit")
    _v_statement = amount_validator("statement_balance")
    _v_minimum = amount_validator("minimum_payment")


class BalanceAdjustmentCreate(MontraModel):
    actual_balance: Decimal
    occurred_at: datetime
    reason: str | None = Field(default=None, max_length=255)

    _v_actual = amount_validator("actual_balance")


class CreditCardFields(MontraModel):
    """Card metadata. Only meaningful where account_type = CREDIT_CARD."""

    credit_limit: Decimal | None = None
    statement_balance: Decimal | None = None
    statement_closing_day: int | None = Field(default=None, ge=1, le=31)
    payment_due_day: int | None = Field(default=None, ge=1, le=31)
    minimum_payment: Decimal | None = None
    interest_rate: Decimal | None = Field(default=None, ge=0, le=100)
    expiry_month: int | None = Field(default=None, ge=1, le=12)
    expiry_year: int | None = Field(default=None, ge=2000, le=2100)

    _v_limit = amount_validator("credit_limit")
    _v_statement = amount_validator("statement_balance")
    _v_minimum = amount_validator("minimum_payment")


class CreditCardPayment(MontraModel):
    source_account_id: str
    amount: Decimal
    occurred_at: datetime

    _v_amount = amount_validator("amount")


class PrepaidTopUp(MontraModel):
    source_account_id: str
    amount: Decimal
    occurred_at: datetime

    _v_amount = amount_validator("amount")


class VisibilityUpdate(MontraModel):
    visibility: Visibility
