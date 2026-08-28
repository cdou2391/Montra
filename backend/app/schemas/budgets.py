from decimal import Decimal

from pydantic import Field

from app.db.enums import BudgetPeriod, Visibility
from app.schemas.common import MontraModel, amount_validator


class BudgetCreate(MontraModel):
    category_id: str
    amount: Decimal = Field(gt=0)
    visibility: Visibility = Visibility.PRIVATE
    period: BudgetPeriod = BudgetPeriod.MONTHLY

    _v_amount = amount_validator("amount")


class BudgetUpdate(MontraModel):
    amount: Decimal | None = Field(default=None, gt=0)
    visibility: Visibility | None = None

    _v_amount = amount_validator("amount")
