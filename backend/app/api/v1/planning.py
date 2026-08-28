"""Planned transaction, recurring rule and notification endpoints."""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Header, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.api.deps import current_user, db_session, parse_uuid
from app.core.errors import NotFound
from app.core.responses import collection, single
from app.core.timezone import to_local
from app.db.base import utcnow
from app.db.enums import (
    PlannedSource,
    PlannedStatus,
    PlannedType,
    RecurringStatus,
)
from app.models.planning import Notification, RecurringRule
from app.models.user import User
from app.schemas.planning import (
    PlannedComplete,
    PlannedCreate,
    PlannedReschedule,
    PlannedUpdate,
    RecurringRuleCreate,
    RecurringRuleUpdate,
)
from app.services import planning as planning_service
from app.services.authz import get_transactable_account

router = APIRouter(tags=["planning"])


def _today(user: User) -> date:
    return to_local(utcnow(), user.timezone).date()


# ------------------------------------------------------- planned transactions


@router.get("/planned-transactions")
def list_planned(
    status_filter: PlannedStatus | None = Query(default=None, alias="status"),
    type: PlannedType | None = None,  # noqa: A002
    account_id: str | None = None,
    source: PlannedSource | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    include_closed: bool = False,
    limit: int = Query(default=100, ge=1, le=200),
    context: str = Query(default="personal", pattern="^(personal|family)$"),
    db: DbSession = Depends(db_session),
    user: User = Depends(current_user),
) -> dict:
    # Correct the list even when the worker is behind.
    planning_service.refresh_due_status(db, user=user)
    rows = planning_service.list_planned(
        db,
        user=user,
        status=status_filter,
        planned_type=type,
        account_id=parse_uuid(account_id, "account_id"),
        source=source,
        date_from=date_from,
        date_to=date_to,
        include_closed=include_closed,
        limit=limit,
        context=context,
    )
    today = _today(user)
    db.commit()
    return collection(
        [
            planning_service.serialize_planned(p, timezone_name=user.timezone, today=today)
            for p in rows
        ],
        limit=limit,
    )


@router.post("/planned-transactions", status_code=status.HTTP_201_CREATED)
def create_planned(
    payload: PlannedCreate,
    db: DbSession = Depends(db_session),
    user: User = Depends(current_user),
) -> dict:
    planned = planning_service.create_planned(
        db,
        user=user,
        account_id=parse_uuid(payload.account_id, "account_id"),
        planned_type=payload.planned_type,
        amount=payload.amount,
        expected_at=payload.expected_at,
        description=payload.description,
        category_id=parse_uuid(payload.category_id, "category_id"),
        notes=payload.notes,
        reminder_days_before=payload.reminder_days_before,
        destination_account_id=parse_uuid(payload.destination_account_id, "destination_account_id"),
        goal_id=parse_uuid(payload.goal_id, "goal_id"),
    )
    today = _today(user)
    db.commit()
    db.refresh(planned)
    return single(
        planning_service.serialize_planned(planned, timezone_name=user.timezone, today=today)
    )


@router.get("/planned-transactions/{planned_id}")
def get_planned(
    planned_id: uuid.UUID,
    db: DbSession = Depends(db_session),
    user: User = Depends(current_user),
) -> dict:
    planned = planning_service.get_planned(db, planned_id, user)
    today = _today(user)
    db.commit()
    return single(
        planning_service.serialize_planned(planned, timezone_name=user.timezone, today=today)
    )


@router.patch("/planned-transactions/{planned_id}")
def update_planned(
    planned_id: uuid.UUID,
    payload: PlannedUpdate,
    db: DbSession = Depends(db_session),
    user: User = Depends(current_user),
) -> dict:
    from app.core.timezone import ensure_aware

    planned = planning_service.get_planned(db, planned_id, user)
    get_transactable_account(db, planned.account_id, user)
    planning_service._require_open(planned)

    if payload.amount is not None:
        planned.amount = payload.amount
    if payload.expected_at is not None:
        planned.expected_at = ensure_aware(payload.expected_at, user.timezone)
        planned.occurrence_date = to_local(planned.expected_at, user.timezone).date()
    if payload.description is not None:
        planned.description = payload.description
    if payload.category_id is not None:
        planned.category_id = parse_uuid(payload.category_id, "category_id")
    if payload.notes is not None:
        planned.notes = payload.notes

    today = _today(user)
    db.commit()
    db.refresh(planned)
    return single(
        planning_service.serialize_planned(planned, timezone_name=user.timezone, today=today)
    )


@router.post("/planned-transactions/{planned_id}/complete", status_code=status.HTTP_201_CREATED)
def complete_planned(
    planned_id: uuid.UUID,
    payload: PlannedComplete,
    db: DbSession = Depends(db_session),
    user: User = Depends(current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    planned = planning_service.complete_planned(
        db,
        user=user,
        planned_id=planned_id,
        actual_amount=payload.actual_amount,
        actual_occurred_at=payload.actual_occurred_at,
        account_id=parse_uuid(payload.account_id, "account_id"),
        idempotency_key=idempotency_key,
    )
    today = _today(user)
    db.commit()
    db.refresh(planned)
    return single(
        planning_service.serialize_planned(planned, timezone_name=user.timezone, today=today)
    )


def _lifecycle(action):
    def handler(
        planned_id: uuid.UUID,
        db: DbSession = Depends(db_session),
        user: User = Depends(current_user),
    ) -> dict:
        planned = action(db, user=user, planned_id=planned_id)
        today = _today(user)
        db.commit()
        db.refresh(planned)
        return single(
            planning_service.serialize_planned(planned, timezone_name=user.timezone, today=today)
        )

    return handler


@router.post("/planned-transactions/{planned_id}/reschedule")
def reschedule_planned(
    planned_id: uuid.UUID,
    payload: PlannedReschedule,
    db: DbSession = Depends(db_session),
    user: User = Depends(current_user),
) -> dict:
    planned = planning_service.reschedule_planned(
        db,
        user=user,
        planned_id=planned_id,
        expected_at=payload.expected_at,
        amount=payload.amount,
        reminder_days_before=payload.reminder_days_before,
    )
    today = _today(user)
    db.commit()
    db.refresh(planned)
    return single(
        planning_service.serialize_planned(planned, timezone_name=user.timezone, today=today)
    )


router.add_api_route(
    "/planned-transactions/{planned_id}/cancel",
    _lifecycle(planning_service.cancel_planned),
    methods=["POST"],
    tags=["planning"],
)
router.add_api_route(
    "/planned-transactions/{planned_id}/mark-missed",
    _lifecycle(planning_service.mark_missed),
    methods=["POST"],
    tags=["planning"],
)
router.add_api_route(
    "/planned-transactions/{planned_id}/skip",
    _lifecycle(planning_service.skip_planned),
    methods=["POST"],
    tags=["planning"],
)


# ------------------------------------------------------------- recurring rules


@router.get("/recurring-rules")
def list_rules(
    status_filter: RecurringStatus | None = Query(default=None, alias="status"),
    db: DbSession = Depends(db_session),
    user: User = Depends(current_user),
) -> dict:
    from app.services.authz import visible_accounts

    account_ids = select(visible_accounts(db, user, include_archived=True).subquery().c.id)
    stmt = select(RecurringRule).where(RecurringRule.account_id.in_(account_ids))
    if status_filter is not None:
        stmt = stmt.where(RecurringRule.status == status_filter)
    rows = list(db.scalars(stmt.order_by(RecurringRule.next_occurrence_date)))
    db.commit()
    return collection([planning_service.serialize_rule(r) for r in rows], limit=len(rows))


@router.post("/recurring-rules", status_code=status.HTTP_201_CREATED)
def create_rule(
    payload: RecurringRuleCreate,
    db: DbSession = Depends(db_session),
    user: User = Depends(current_user),
) -> dict:
    rule = planning_service.create_rule(
        db,
        user=user,
        account_id=parse_uuid(payload.account_id, "account_id"),
        planned_type=payload.planned_type,
        amount=payload.amount,
        name=payload.name,
        frequency=payload.frequency,
        start_date=payload.start_date,
        interval_value=payload.interval_value,
        end_date=payload.end_date,
        category_id=parse_uuid(payload.category_id, "category_id"),
        notes=payload.notes,
        occurrence_hour=payload.occurrence_hour,
        reminder_days_before=payload.reminder_days_before,
        destination_account_id=parse_uuid(payload.destination_account_id, "destination_account_id"),
        goal_id=parse_uuid(payload.goal_id, "goal_id"),
    )
    # Populate the window immediately so the series is visible without waiting
    # for the next scheduler run.
    planning_service.generate_occurrences(db, rule, owner=user)
    db.commit()
    db.refresh(rule)
    return single(planning_service.serialize_rule(rule))


def _get_rule(db: DbSession, rule_id: uuid.UUID, user: User) -> RecurringRule:
    rule = db.get(RecurringRule, rule_id)
    if rule is None:
        raise NotFound("Recurring rule not found.", code="RECURRING_RULE_NOT_FOUND")
    get_transactable_account(db, rule.account_id, user)
    return rule


@router.get("/recurring-rules/{rule_id}")
def get_rule(
    rule_id: uuid.UUID,
    db: DbSession = Depends(db_session),
    user: User = Depends(current_user),
) -> dict:
    rule = _get_rule(db, rule_id, user)
    db.commit()
    return single(planning_service.serialize_rule(rule))


@router.patch("/recurring-rules/{rule_id}")
def update_rule(
    rule_id: uuid.UUID,
    payload: RecurringRuleUpdate,
    db: DbSession = Depends(db_session),
    user: User = Depends(current_user),
) -> dict:
    rule = _get_rule(db, rule_id, user)
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(rule, field, value)
    db.commit()
    db.refresh(rule)
    return single(planning_service.serialize_rule(rule))


def _rule_status(new_status: RecurringStatus):
    def handler(
        rule_id: uuid.UUID,
        db: DbSession = Depends(db_session),
        user: User = Depends(current_user),
    ) -> dict:
        rule = planning_service.set_rule_status(db, user=user, rule_id=rule_id, status=new_status)
        if new_status is RecurringStatus.ACTIVE:
            planning_service.generate_occurrences(db, rule, owner=user)
        db.commit()
        db.refresh(rule)
        return single(planning_service.serialize_rule(rule))

    return handler


for path, rule_status in (
    ("pause", RecurringStatus.PAUSED),
    ("resume", RecurringStatus.ACTIVE),
    ("end", RecurringStatus.ENDED),
):
    router.add_api_route(
        f"/recurring-rules/{{rule_id}}/{path}",
        _rule_status(rule_status),
        methods=["POST"],
        tags=["planning"],
    )


# --------------------------------------------------------------- notifications


@router.get("/notifications")
def list_notifications(
    unread_only: bool = False,
    limit: int = Query(default=50, ge=1, le=100),
    db: DbSession = Depends(db_session),
    user: User = Depends(current_user),
) -> dict:
    stmt = select(Notification).where(Notification.user_id == user.id)
    if unread_only:
        stmt = stmt.where(Notification.read_at.is_(None))
    rows = list(db.scalars(stmt.order_by(Notification.created_at.desc()).limit(limit)))
    unread = db.scalar(
        select(Notification.id)
        .where(Notification.user_id == user.id, Notification.read_at.is_(None))
        .limit(1)
    )
    db.commit()
    payload = collection(
        [
            {
                "id": str(n.id),
                "notification_type": n.notification_type.value,
                "title": n.title,
                "body": n.body,
                "related_entity_type": (
                    n.related_entity_type.value if n.related_entity_type else None
                ),
                "related_entity_id": (str(n.related_entity_id) if n.related_entity_id else None),
                "read_at": n.read_at.isoformat() if n.read_at else None,
                "created_at": n.created_at.isoformat(),
            }
            for n in rows
        ],
        limit=limit,
    )
    payload["has_unread"] = unread is not None
    return payload


@router.post("/notifications/{notification_id}/read", status_code=status.HTTP_204_NO_CONTENT)
def mark_read(
    notification_id: uuid.UUID,
    db: DbSession = Depends(db_session),
    user: User = Depends(current_user),
) -> Response:
    notification = db.get(Notification, notification_id)
    if notification is None or notification.user_id != user.id:
        raise NotFound("Notification not found.", code="NOTIFICATION_NOT_FOUND")
    if notification.read_at is None:
        notification.read_at = utcnow()
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/notifications/read-all", status_code=status.HTTP_204_NO_CONTENT)
def mark_all_read(
    db: DbSession = Depends(db_session),
    user: User = Depends(current_user),
) -> Response:
    from sqlalchemy import update

    db.execute(
        update(Notification)
        .where(Notification.user_id == user.id, Notification.read_at.is_(None))
        .values(read_at=utcnow())
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
