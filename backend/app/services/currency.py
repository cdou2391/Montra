"""Converting balances into a reporting currency.

Two rules from Data Model section 65 shape everything here:

* The original currency and amount are never replaced. An account in USD holds
  dollars, and its own screens say so. Conversion exists so that *totals* mean
  something, and nowhere else.
* A missing rate is not a licence to add the numbers anyway. Summing USD into
  RWF at 1:1 does not produce an approximate total, it produces a wrong one —
  so an unconvertible balance is left out and reported as left out.

Rates are entered by the user. The PRD defers automatic rates, and a net worth
that moves because a third party changed a number is worse than one the user
set deliberately and can explain.
"""

import uuid
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.core.errors import NotFound, ValidationFailed
from app.models.finance import ExchangeRate
from app.models.user import User

QUANTUM = Decimal("0.0001")
RATE_QUANTUM = Decimal("0.00000001")


def normalize(code: str) -> str:
    code = (code or "").strip().upper()
    if len(code) != 3 or not code.isalpha():
        raise ValidationFailed(
            "A currency is a three-letter code.",
            code="INVALID_CURRENCY",
            details=[{"field": "currency", "message": "Three letters, like RWF or USD."}],
        )
    return code


class Converter:
    """Converts many balances against one snapshot of a user's rates.

    Built once per request rather than queried per account: a page listing
    accounts would otherwise issue one lookup per row, and every row would be
    free to disagree with the others about the rate.
    """

    def __init__(self, rates: dict[tuple[str, str], Decimal], base: str):
        self._rates = rates
        self.base = base

    def rate(self, source: str, target: str) -> Decimal | None:
        source, target = source.upper(), target.upper()
        if source == target:
            return Decimal(1)
        direct = self._rates.get((source, target))
        if direct is not None:
            return direct
        # One rate defines the pair both ways. Storing USD→RWF and then
        # refusing RWF→USD would make the user enter the same fact twice and
        # give them a way to contradict themselves.
        inverse = self._rates.get((target, source))
        if inverse is not None and inverse > 0:
            return (Decimal(1) / inverse).quantize(RATE_QUANTUM, rounding=ROUND_HALF_UP)
        return None

    def convert(self, amount: Decimal, source: str, target: str | None = None) -> Decimal | None:
        """The amount in the target currency, or None if no rate is known."""
        target = target or self.base
        rate = self.rate(source, target)
        if rate is None:
            return None
        return (Decimal(amount) * rate).quantize(QUANTUM, rounding=ROUND_HALF_UP)

    def can_convert(self, source: str) -> bool:
        return self.rate(source, self.base) is not None


def converter_for(db: DbSession, *, user: User, base: str | None = None) -> Converter:
    rows = db.scalars(select(ExchangeRate).where(ExchangeRate.user_id == user.id)).all()
    rates = {(r.base_currency, r.quote_currency): Decimal(r.rate) for r in rows}
    return Converter(rates, (base or user.base_currency).upper())


# ------------------------------------------------------------------ management


def set_rate(
    db: DbSession,
    *,
    user: User,
    base_currency: str,
    quote_currency: str,
    rate: Decimal,
    as_of: date | None = None,
) -> ExchangeRate:
    """Record or update one pair.

    Upserts rather than appending: the user is stating what a currency is worth
    now, and keeping every past guess would leave the reporting to choose
    between them.
    """
    base_currency = normalize(base_currency)
    quote_currency = normalize(quote_currency)

    if base_currency == quote_currency:
        raise ValidationFailed(
            "A currency is always worth one of itself.",
            code="SAME_CURRENCY",
            details=[{"field": "quote_currency", "message": "Choose two different currencies."}],
        )
    if rate <= 0:
        raise ValidationFailed(
            details=[{"field": "rate", "message": "A rate must be more than zero."}]
        )

    existing = db.scalar(
        select(ExchangeRate).where(
            ExchangeRate.user_id == user.id,
            ExchangeRate.base_currency == base_currency,
            ExchangeRate.quote_currency == quote_currency,
        )
    )
    # The same pair entered the other way round is the same fact. Updating it
    # in place stops a user holding two rates that disagree.
    inverted = db.scalar(
        select(ExchangeRate).where(
            ExchangeRate.user_id == user.id,
            ExchangeRate.base_currency == quote_currency,
            ExchangeRate.quote_currency == base_currency,
        )
    )
    if existing is None and inverted is not None:
        db.delete(inverted)
        db.flush()

    as_of = as_of or date.today()
    if existing is not None:
        existing.rate = rate
        existing.as_of = as_of
        db.flush()
        return existing

    created = ExchangeRate(
        user_id=user.id,
        base_currency=base_currency,
        quote_currency=quote_currency,
        rate=rate,
        as_of=as_of,
    )
    db.add(created)
    db.flush()
    return created


def list_rates(db: DbSession, *, user: User) -> list[ExchangeRate]:
    return list(
        db.scalars(
            select(ExchangeRate)
            .where(ExchangeRate.user_id == user.id)
            .order_by(ExchangeRate.base_currency, ExchangeRate.quote_currency)
        )
    )


def delete_rate(db: DbSession, *, user: User, rate_id: uuid.UUID) -> None:
    row = db.get(ExchangeRate, rate_id)
    if row is None or row.user_id != user.id:
        raise NotFound("Rate not found.", code="EXCHANGE_RATE_NOT_FOUND")
    db.delete(row)
    db.flush()


def currencies_in_use(db: DbSession, *, user: User) -> list[str]:
    """Every currency the user actually holds something in.

    Drives the prompt to set a rate: asking for USD only matters once there is
    a dollar account to convert.
    """
    from app.models.finance import Account

    rows = db.scalars(
        select(Account.currency).where(Account.owner_user_id == user.id).distinct()
    ).all()
    return sorted({c.upper() for c in rows})


def serialize(rate: ExchangeRate) -> dict:
    from app.core.money import serialize_rate

    return {
        "id": str(rate.id),
        "base_currency": rate.base_currency,
        "quote_currency": rate.quote_currency,
        "rate": serialize_rate(Decimal(rate.rate)),
        "as_of": rate.as_of.isoformat(),
    }
