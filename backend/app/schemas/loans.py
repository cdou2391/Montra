from datetime import date, datetime
from decimal import Decimal

from pydantic import Field

from app.db.enums import Frequency, LoanDirection, OwnershipType, Visibility
from app.schemas.common import MontraModel, amount_validator


class LoanCreate(MontraModel):
    name: str = Field(min_length=1, max_length=160)
    direction: LoanDirection
    currency: str = Field(min_length=3, max_length=3)
    original_principal: Decimal
    opening_outstanding_principal: Decimal
    start_date: date

    counterparty: str | None = Field(default=None, max_length=160)
    interest_rate: Decimal | None = Field(default=None, ge=0, le=1000)
    end_date: date | None = None
    expected_payment_amount: Decimal | None = None
    payment_frequency: Frequency | None = None
    next_payment_date: date | None = None
    visibility: Visibility = Visibility.PRIVATE
    ownership_type: OwnershipType = OwnershipType.PERSONAL
    family_id: str | None = None
    notes: str | None = None

    _v_original = amount_validator("original_principal")
    _v_opening = amount_validator("opening_outstanding_principal")
    _v_expected = amount_validator("expected_payment_amount")


class LoanUpdate(MontraModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    counterparty: str | None = Field(default=None, max_length=160)
    interest_rate: Decimal | None = Field(default=None, ge=0, le=1000)
    end_date: date | None = None
    expected_payment_amount: Decimal | None = None
    payment_frequency: Frequency | None = None
    next_payment_date: date | None = None
    notes: str | None = None

    _v_expected = amount_validator("expected_payment_amount")


class LoanPaymentCreate(MontraModel):
    account_id: str
    payment_date: date
    occurred_at: datetime | None = None
    total_amount: Decimal
    principal_amount: Decimal
    interest_amount: Decimal = Decimal("0")
    fee_amount: Decimal = Decimal("0")
    notes: str | None = None

    _v_total = amount_validator("total_amount")
    _v_principal = amount_validator("principal_amount")
    _v_interest = amount_validator("interest_amount")
    _v_fee = amount_validator("fee_amount")
