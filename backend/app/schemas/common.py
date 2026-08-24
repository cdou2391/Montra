from decimal import Decimal

from pydantic import BaseModel, ConfigDict, field_validator

from app.core.money import to_decimal


class MontraModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class AmountField(MontraModel):
    """Mixin-style validator helper for string-serialized money."""

    @staticmethod
    def parse(value: str | Decimal, field: str = "amount") -> Decimal:
        return to_decimal(value, field)


def amount_validator(field_name: str):
    def _validate(cls, v):  # noqa: N805
        if v is None:
            return v
        return to_decimal(v, field_name)

    return field_validator(field_name)(classmethod(_validate))
