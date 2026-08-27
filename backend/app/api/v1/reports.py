"""Dashboard and net worth."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session as DbSession

from app.api.deps import current_user, db_session
from app.core.responses import collection, single
from app.models.user import User
from app.services import forecast as forecast_service
from app.services import insights as insight_service
from app.services import reporting

router = APIRouter(tags=["reports"])

Context = Query(default="personal", pattern="^(personal|family)$")


@router.get("/dashboard")
def dashboard(
    context: str = Context,
    db: DbSession = Depends(db_session),
    user: User = Depends(current_user),
) -> dict:
    payload = reporting.dashboard(db, user=user, context=context)
    db.commit()
    return single(payload)


@router.get("/reports/net-worth")
def net_worth(
    context: str = Context,
    db: DbSession = Depends(db_session),
    user: User = Depends(current_user),
) -> dict:
    payload = reporting.net_worth(db, user=user, context=context)
    db.commit()
    return single(payload)


@router.get("/forecasts/cash-flow")
def cash_flow(
    context: str = Context,
    period: str = Query(default="30d", pattern="^(7d|30d)$"),
    account_id: str | None = None,
    db: DbSession = Depends(db_session),
    user: User = Depends(current_user),
) -> dict:
    """Projected balance over the period, from what is already known."""
    from app.api.deps import parse_uuid

    payload = forecast_service.cash_flow(
        db,
        user=user,
        context=context,
        period=period,
        account_id=parse_uuid(account_id, "account_id"),
    )
    db.commit()
    return single(payload)


@router.get("/insights")
def insights(
    context: str = Context,
    db: DbSession = Depends(db_session),
    user: User = Depends(current_user),
) -> dict:
    payload = insight_service.generate(db, user=user, context=context)
    db.commit()
    return collection(payload, limit=len(payload))
