"""Dashboard and net worth (API spec sections 26-27)."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session as DbSession

from app.api.deps import current_user, db_session
from app.core.responses import single
from app.models.user import User
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
