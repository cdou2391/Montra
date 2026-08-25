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


ZERO_DECIMAL_CURRENCIES = {"RWF", "JPY", "KRW", "VND", "UGX", "BIF"}


def format_money(value: Decimal, currency: str) -> str:
    """Render an amount as prose, the way the UI writes it.

    Most amounts leave the API as bare strings for the client to format. These
    are the exception: insight and warning text is composed as a sentence
    server-side, so the number inside it has to arrive already readable.
    """
    quantum = Decimal("1") if currency in ZERO_DECIMAL_CURRENCIES else DISPLAY_QUANTUM
    amount = value.quantize(quantum, rounding=ROUND_HALF_UP)
    sign = "-" if amount < 0 else ""
    whole, _, fraction = f"{abs(amount):f}".partition(".")
    grouped = f"{int(whole):,}"
    body = grouped if not fraction else f"{grouped}.{fraction}"
    return f"{sign}{currency} {body}"
