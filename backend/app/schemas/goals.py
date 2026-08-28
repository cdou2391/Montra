from datetime import date, datetime
from decimal import Decimal

from pydantic import Field

from app.db.enums import Visibility
from app.schemas.common import MontraModel, amount_validator


class GoalCreate(MontraModel):
    name: str = Field(min_length=1, max_length=160)
    account_id: str
    target_amount: Decimal = Field(gt=0)
    # Optional by design: an emergency fund has no deadline, and the form lets
    # the user decide rather than inventing one.
    target_date: date | None = None
    visibility: Visibility = Visibility.PRIVATE

    _v_target = amount_validator("target_amount")


class GoalUpdate(MontraModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    target_amount: Decimal | None = Field(default=None, gt=0)
    target_date: date | None = None
    # None means "not supplied"; this says "remove the one that is there".
    clear_target_date: bool = False
    visibility: Visibility | None = None

    _v_target = amount_validator("target_amount")


class GoalContribution(MontraModel):
    source_account_id: str
    amount: Decimal = Field(gt=0)
    occurred_at: datetime | None = None

    _v_amount = amount_validator("amount")
