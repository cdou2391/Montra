from datetime import date, datetime
from decimal import Decimal

from pydantic import Field

from app.db.enums import Frequency, PlannedType
from app.schemas.common import MontraModel, amount_validator


class PlannedCreate(MontraModel):
    planned_type: PlannedType
    account_id: str
    amount: Decimal
    expected_at: datetime
    description: str = Field(min_length=1, max_length=255)
    category_id: str | None = None
    notes: str | None = None
    reminder_days_before: int | None = Field(default=None, ge=0, le=60)
    # TRANSFER only: where the money goes. account_id is the source.
    destination_account_id: str | None = None
    # A one-off contribution towards a goal, tagged so completing it counts.
    goal_id: str | None = None

    _v_amount = amount_validator("amount")


class PlannedUpdate(MontraModel):
    amount: Decimal | None = None
    expected_at: datetime | None = None
    description: str | None = Field(default=None, min_length=1, max_length=255)
    category_id: str | None = None
    notes: str | None = None

    _v_amount = amount_validator("amount")


class PlannedComplete(MontraModel):
    """Every field defaults from the planned item when omitted."""

    actual_amount: Decimal | None = None
    actual_occurred_at: datetime | None = None
    account_id: str | None = None

    _v_amount = amount_validator("actual_amount")


class PlannedReschedule(MontraModel):
    expected_at: datetime
    amount: Decimal | None = None
    reminder_days_before: int | None = Field(default=None, ge=0, le=60)

    _v_amount = amount_validator("amount")


class RecurringRuleCreate(MontraModel):
    planned_type: PlannedType
    account_id: str
    amount: Decimal
    name: str = Field(min_length=1, max_length=160)
    frequency: Frequency
    start_date: date
    interval_value: int = Field(default=1, ge=1, le=52)
    end_date: date | None = None
    category_id: str | None = None
    notes: str | None = None
    occurrence_hour: int = Field(default=9, ge=0, le=23)
    reminder_days_before: int | None = Field(default=None, ge=0, le=60)
    destination_account_id: str | None = None
    # A recurring contribution: each occurrence this generates is tagged, so
    # completing one counts towards the goal rather than merely moving money.
    goal_id: str | None = None

    _v_amount = amount_validator("amount")


class RecurringRuleUpdate(MontraModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    amount: Decimal | None = None
    end_date: date | None = None
    notes: str | None = None
    reminder_days_before: int | None = Field(default=None, ge=0, le=60)

    _v_amount = amount_validator("amount")
