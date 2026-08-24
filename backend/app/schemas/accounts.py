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

    _v_opening = amount_validator("opening_balance")


class AccountUpdate(MontraModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = None
    institution_id: str | None = None
    account_identifier: str | None = Field(default=None, max_length=64)
    currency: str | None = Field(default=None, min_length=3, max_length=3)


class BalanceAdjustmentCreate(MontraModel):
    actual_balance: Decimal
    occurred_at: datetime
    reason: str | None = Field(default=None, max_length=255)

    _v_actual = amount_validator("actual_balance")
