"""Money handling.

Amounts are stored as DECIMAL(20,4) and serialized as strings so that no
JSON float ever touches a financial value (API spec section 12).
"""

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from app.core.errors import ValidationFailed

QUANTUM = Decimal("0.0001")
DISPLAY_QUANTUM = Decimal("0.01")


def to_decimal(value: str | int | float | Decimal, field: str = "amount") -> Decimal:
    try:
        dec = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValidationFailed(
            details=[{"field": field, "message": "Not a valid amount."}]
        ) from exc
    if not dec.is_finite():
        raise ValidationFailed(details=[{"field": field, "message": "Not a valid amount."}])
    return dec.quantize(QUANTUM, rounding=ROUND_HALF_UP)


def serialize(value: Decimal) -> str:
    """Render a stored amount for the API, at two decimal places."""
    return str(value.quantize(DISPLAY_QUANTUM, rounding=ROUND_HALF_UP))


def money(value: Decimal, currency: str) -> dict[str, str]:
    return {"amount": serialize(value), "currency": currency}


def serialize_rate(value: Decimal) -> str:
    """Render a percentage without trailing zeros.

    normalize() alone would turn 100 into 1E+2, so the result is formatted with
    :f to keep plain notation.
    """
    return f"{Decimal(value).normalize():f}"
