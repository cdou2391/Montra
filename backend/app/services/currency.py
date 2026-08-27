"""Converting balances into a reporting currency.

Two rules shape everything here:

* The original currency and amount are never replaced. Conversion exists so
  that *totals* mean something, and nowhere else.
* A missing rate is not a licence to add the numbers anyway. Summing USD into
  RWF at 1:1 gives a wrong total, not an approximate one, so an unconvertible
  balance is left out and reported as left out.

Rates come from a published feed refreshed daily into a shared table; a rate
the user sets themselves overrides it.
"""

import logging
import uuid
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.core.errors import NotFound, ValidationFailed
from app.models.finance import ExchangeRate, MarketRate
from app.models.user import User

logger = logging.getLogger(__name__)

MANUAL = "MANUAL"

# Two bases is enough: everything else is reached by crossing through one, and
# each base costs one request a day however many currencies it covers.
MARKET_BASES = ("RWF", "USD")

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
    """Converts many balances against one snapshot of the rates.

    Built once per request, not queried per account: otherwise every row of a
    listing issues its own lookup and is free to disagree with the others.

    A rate the user set wins over the shared published table.
    """

    def __init__(
        self,
        rates: dict[tuple[str, str], Decimal],
        base: str,
        market: dict[tuple[str, str], Decimal] | None = None,
    ):
        self._rates = rates
        self._market = market or {}
        self.base = base

    def _lookup(self, table, source: str, target: str) -> Decimal | None:
        direct = table.get((source, target))
        if direct is not None:
            return direct
        # One rate defines the pair both ways; requiring both entries would let
        # a user contradict themselves.
        inverse = table.get((target, source))
        if inverse is not None and inverse > 0:
            return (Decimal(1) / inverse).quantize(RATE_QUANTUM, rounding=ROUND_HALF_UP)
        return None

    def _cross(self, source: str, target: str) -> Decimal | None:
        """Go via a currency the table has both sides of.

        With RWF→USD and RWF→EUR on hand, USD→EUR follows without a fetch.
        """
        for pivot in MARKET_BASES:
            if pivot in (source, target):
                continue
            left = self._lookup(self._market, source, pivot)
            right = self._lookup(self._market, pivot, target)
            if left is not None and right is not None:
                return (left * right).quantize(RATE_QUANTUM, rounding=ROUND_HALF_UP)
        return None

    def rate(self, source: str, target: str) -> Decimal | None:
        source, target = source.upper(), target.upper()
        if source == target:
            return Decimal(1)
        return (
            self._lookup(self._rates, source, target)
            or self._lookup(self._market, source, target)
            or self._cross(source, target)
        )

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
    overrides = {(r.base_currency, r.quote_currency): Decimal(r.rate) for r in rows}
    market = {
        (r.base_currency, r.quote_currency): Decimal(r.rate)
        for r in db.scalars(select(MarketRate))
    }
    return Converter(overrides, (base or user.base_currency).upper(), market)


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

    Upserts: the user is stating what a currency is worth now, and keeping past
    guesses would leave reporting to choose between them.
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
    # The pair the other way round is the same fact; updating in place stops
    # two rates that disagree.
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
        existing.source = MANUAL
        db.flush()
        return existing

    created = ExchangeRate(
        user_id=user.id,
        base_currency=base_currency,
        quote_currency=quote_currency,
        rate=rate,
        as_of=as_of,
        source=MANUAL,
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

    Asking for a USD rate only matters once a dollar account exists.
    """
    from app.models.finance import Account

    rows = db.scalars(
        select(Account.currency).where(Account.owner_user_id == user.id).distinct()
    ).all()
    return sorted({c.upper() for c in rows})


# ------------------------------------------------------------- automatic rates


def refresh_market_rates(db: DbSession, *, fetcher=None) -> int:
    """Pull the published rates into the shared table.

    One request per base however many currencies or users — the point of the
    table. Nothing is written unless a real number came back, so a feed being
    down leaves yesterday's rates rather than a gap.
    """
    from app.services import fx_feed

    fetcher = fetcher or fx_feed.fetch_all
    today = date.today()

    existing = {(r.base_currency, r.quote_currency): r for r in db.scalars(select(MarketRate))}
    written = 0

    for base in MARKET_BASES:
        published = fetcher(base)
        for quote, (rate, source) in published.items():
            if quote == base or rate <= 0:
                continue
            row = existing.get((base, quote))
            if row is None:
                row = MarketRate(
                    base_currency=base,
                    quote_currency=quote,
                    rate=rate,
                    as_of=today,
                    source=source,
                )
                db.add(row)
                existing[(base, quote)] = row
            else:
                row.rate = rate
                row.as_of = today
                row.source = source
            written += 1

    db.flush()
    return written


def market_rates(db: DbSession) -> list[MarketRate]:
    return list(
        db.scalars(
            select(MarketRate).order_by(MarketRate.base_currency, MarketRate.quote_currency)
        )
    )


def market_summary(db: DbSession) -> dict:
    """What the shared table currently holds, for the screen that shows it."""
    rows = market_rates(db)
    return {
        "bases": list(MARKET_BASES),
        "pair_count": len(rows),
        "as_of": max((r.as_of for r in rows), default=None),
        "sources": sorted({r.source for r in rows}),
    }


def serialize_market(rate: MarketRate) -> dict:
    from app.core.money import serialize_rate

    return {
        "base_currency": rate.base_currency,
        "quote_currency": rate.quote_currency,
        "rate": serialize_rate(Decimal(rate.rate)),
        "as_of": rate.as_of.isoformat(),
        "source": rate.source,
    }


def serialize(rate: ExchangeRate) -> dict:
    from app.core.money import serialize_rate

    return {
        "id": str(rate.id),
        "base_currency": rate.base_currency,
        "quote_currency": rate.quote_currency,
        "rate": serialize_rate(Decimal(rate.rate)),
        "as_of": rate.as_of.isoformat(),
        "source": rate.source,
        "automatic": rate.source != MANUAL,
    }
