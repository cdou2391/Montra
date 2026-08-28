"""Goal endpoints.

A goal is a target and a link to the account the money sits in. Contributing
posts a real transfer through the posting engine and tags it, so a goal never
holds a balance of its own.
"""

import uuid

from fastapi import APIRouter, Depends, Header, Query, status

from app.api.deps import current_user, db_session, parse_uuid
from app.core.responses import collection, single
from app.core.timezone import ensure_aware
from app.models.user import User
from app.schemas.goals import GoalContribution, GoalCreate, GoalUpdate
from app.services import goals as goal_service
from app.services.authz import get_transactable_account, get_viewable_account

router = APIRouter(tags=["goals"], prefix="/goals")


@router.get("")
def list_goals(
    context: str = Query(default="personal", pattern="^(personal|family)$"),
    db=Depends(db_session),
    user: User = Depends(current_user),
) -> dict:
    payload = goal_service.list_goals(db, user=user, context=context)
    return collection(payload, limit=len(payload))


@router.post("", status_code=status.HTTP_201_CREATED)
def create_goal(
    payload: GoalCreate,
    db=Depends(db_session),
    user: User = Depends(current_user),
) -> dict:
    account = get_viewable_account(db, parse_uuid(payload.account_id, "account_id"), user)
    goal = goal_service.create_goal(
        db,
        user=user,
        name=payload.name,
        account=account,
        target_amount=payload.target_amount,
        target_date=payload.target_date,
        visibility=payload.visibility,
    )
    db.commit()
    db.refresh(goal)
    from app.core.timezone import to_local
    from app.db.base import utcnow

    return single(
        goal_service.serialize_goal(db, goal, today=to_local(utcnow(), user.timezone).date())
    )


@router.patch("/{goal_id}")
def update_goal(
    goal_id: uuid.UUID,
    payload: GoalUpdate,
    db=Depends(db_session),
    user: User = Depends(current_user),
) -> dict:
    goal = goal_service.get_goal(db, goal_id, user)
    goal_service.update_goal(
        db,
        goal=goal,
        name=payload.name,
        target_amount=payload.target_amount,
        target_date=payload.target_date,
        clear_target_date=payload.clear_target_date,
    )
    # The target may have moved past or below what is already saved.
    goal_service.refresh_status(db, goal)
    db.commit()
    db.refresh(goal)
    from app.core.timezone import to_local
    from app.db.base import utcnow

    return single(
        goal_service.serialize_goal(db, goal, today=to_local(utcnow(), user.timezone).date())
    )


@router.post("/{goal_id}/contributions", status_code=status.HTTP_201_CREATED)
def contribute(
    goal_id: uuid.UUID,
    payload: GoalContribution,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db=Depends(db_session),
    user: User = Depends(current_user),
) -> dict:
    """Move money into the goal, as a tagged transfer.

    Carries an Idempotency-Key like the other transfer endpoints: replaying one
    returns the original rather than moving the money twice.
    """
    from app.db.base import utcnow

    goal = goal_service.get_goal(db, goal_id, user)
    source = get_transactable_account(
        db, parse_uuid(payload.source_account_id, "source_account_id"), user
    )
    goal_service.contribute(
        db,
        user=user,
        goal=goal,
        source=source,
        amount=payload.amount,
        occurred_at=(
            ensure_aware(payload.occurred_at, user.timezone) if payload.occurred_at else utcnow()
        ),
        idempotency_key=idempotency_key,
    )
    db.commit()
    db.refresh(goal)
    from app.core.timezone import to_local

    return single(
        goal_service.serialize_goal(db, goal, today=to_local(utcnow(), user.timezone).date())
    )


@router.post("/{goal_id}/archive")
def archive_goal(
    goal_id: uuid.UUID,
    db=Depends(db_session),
    user: User = Depends(current_user),
) -> dict:
    """Archived, not deleted. The contributions stay: they were real movements
    and the ledger keeps them either way."""
    goal = goal_service.get_goal(db, goal_id, user)
    goal_service.archive_goal(db, goal)
    db.commit()
    db.refresh(goal)
    from app.core.timezone import to_local
    from app.db.base import utcnow

    return single(
        goal_service.serialize_goal(db, goal, today=to_local(utcnow(), user.timezone).date())
    )
