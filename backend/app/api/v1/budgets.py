"""Budget endpoints.

A budget is a number to compare the ledger against; nothing here posts, and
reading one always re-derives what has been spent.
"""

import uuid

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import current_user, db_session, parse_uuid
from app.core.responses import single
from app.models.user import User
from app.schemas.budgets import BudgetCreate, BudgetUpdate
from app.services import budgets as budget_service

router = APIRouter(tags=["budgets"], prefix="/budgets")


@router.get("")
def list_budgets(
    context: str = Query(default="personal", pattern="^(personal|family)$"),
    db=Depends(db_session),
    user: User = Depends(current_user),
) -> dict:
    """Every visible budget with this period's spending against it."""
    return single(budget_service.status(db, user=user, context=context))


@router.post("", status_code=status.HTTP_201_CREATED)
def create_budget(
    payload: BudgetCreate,
    db=Depends(db_session),
    user: User = Depends(current_user),
) -> dict:
    budget = budget_service.create_budget(
        db,
        user=user,
        category_id=parse_uuid(payload.category_id, "category_id"),
        amount=payload.amount,
        visibility=payload.visibility,
        period=payload.period,
    )
    db.commit()
    db.refresh(budget)
    return single(budget_service.serialize_budget(budget))


@router.patch("/{budget_id}")
def update_budget(
    budget_id: uuid.UUID,
    payload: BudgetUpdate,
    db=Depends(db_session),
    user: User = Depends(current_user),
) -> dict:
    budget = budget_service.get_budget(db, budget_id, user)
    budget_service.update_budget(
        db,
        user=user,
        budget=budget,
        amount=payload.amount,
        visibility=payload.visibility,
    )
    db.commit()
    db.refresh(budget)
    return single(budget_service.serialize_budget(budget))


@router.post("/{budget_id}/archive")
def archive_budget(
    budget_id: uuid.UUID,
    db=Depends(db_session),
    user: User = Depends(current_user),
) -> dict:
    """Archived, not deleted: what you used to aim for is history, and it frees
    the category for a new budget."""
    budget = budget_service.get_budget(db, budget_id, user)
    budget_service.archive_budget(db, budget)
    db.commit()
    db.refresh(budget)
    return single(budget_service.serialize_budget(budget))
