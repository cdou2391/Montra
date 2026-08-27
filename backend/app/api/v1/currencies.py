"""Exchange rates the user maintains.

Reporting only: a USD account holds dollars whatever rate is recorded.
"""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session as DbSession

from app.api.deps import current_user, db_session
from app.core.responses import collection, single
from app.models.user import User
from app.schemas.common import MontraModel
from app.services import currency as currency_service

router = APIRouter(tags=["currencies"])


class ExchangeRateUpsert(MontraModel):
    base_currency: str
    quote_currency: str
    rate: str
    as_of: date | None = None


@router.get("/exchange-rates")
def list_rates(
    db: DbSession = Depends(db_session),
    user: User = Depends(current_user),
) -> dict:
    rows = currency_service.list_rates(db, user=user)
    payload = [currency_service.serialize(r) for r in rows]
    return collection(payload, limit=len(payload))


@router.get("/exchange-rates/currencies-in-use")
def currencies_in_use(
    db: DbSession = Depends(db_session),
    user: User = Depends(current_user),
) -> dict:
    """Which currencies the user holds, and which still need a rate."""
    codes = currency_service.currencies_in_use(db, user=user)
    converter = currency_service.converter_for(db, user=user)
    return single(
        {
            "base_currency": user.base_currency,
            "currencies": codes,
            "missing": [c for c in codes if not converter.can_convert(c)],
        }
    )


@router.post("/exchange-rates/refresh")
def refresh_rates(
    db: DbSession = Depends(db_session),
    user: User = Depends(current_user),
) -> dict:
    """Fetch now rather than waiting for the morning run: a foreign account
    added at noon should not sit uncounted until tomorrow."""
    currency_service.refresh_market_rates(db)
    db.commit()
    return single(currency_service.market_summary(db))


@router.get("/exchange-rates/market")
def market_rates(
    db: DbSession = Depends(db_session),
    user: User = Depends(current_user),
) -> dict:
    """The shared table, as the app reads it."""
    rows = currency_service.market_rates(db)
    payload = [currency_service.serialize_market(r) for r in rows]
    return collection(payload, limit=len(payload))


@router.put("/exchange-rates", status_code=status.HTTP_200_OK)
def upsert_rate(
    payload: ExchangeRateUpsert,
    db: DbSession = Depends(db_session),
    user: User = Depends(current_user),
) -> dict:
    from app.core.money import to_decimal

    rate = currency_service.set_rate(
        db,
        user=user,
        base_currency=payload.base_currency,
        quote_currency=payload.quote_currency,
        rate=to_decimal(payload.rate, "rate"),
        as_of=payload.as_of,
    )
    db.commit()
    db.refresh(rate)
    return single(currency_service.serialize(rate))


@router.delete("/exchange-rates/{rate_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rate(
    rate_id: uuid.UUID,
    db: DbSession = Depends(db_session),
    user: User = Depends(current_user),
) -> None:
    currency_service.delete_rate(db, user=user, rate_id=rate_id)
    db.commit()
