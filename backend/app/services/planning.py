"""Planned transactions, recurrence generation and reminders.

Implementation Plan Phases 11-13.

The rule that shapes this module: a planned transaction is not a ledger entry.
Creating, rescheduling and cancelling touch no balance. Only completion does,
and completion delegates to the posting engine rather than writing its own.
"""

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import selectinload

from app.core.errors import Conflict, NotFound, ValidationFailed
from app.core.timezone import day_end, day_start, ensure_aware, to_local, zone_for
from app.db.base import utcnow
from app.db.enums import (
    OPEN_PLANNED_STATUSES,
    Frequency,
    NotificationType,
    PlannedSource,
    PlannedStatus,
    PlannedType,
    RecurringStatus,
    ReminderEntity,
    ReminderStatus,
)
from app.models.planning import Notification, PlannedTransaction, RecurringRule, Reminder
from app.models.user import User
from app.services.authz import get_transactable_account, get_viewable_account, visible_accounts
from app.services.posting import PostingService
from app.services.recurrence import occurrences_between

# Data Model section 31: keep a forward window rather than years of rows.
GENERATION_WINDOW_DAYS = 90


# --------------------------------------------------------------------- helpers


def _local_date(moment: datetime, timezone_name: str) -> date:
    return to_local(moment, timezone_name).date()


def _stamp(day: date, hour: int, timezone_name: str) -> datetime:
    """A local day plus an hour, as a UTC instant."""
    return datetime(day.year, day.month, day.day, hour, tzinfo=zone_for(timezone_name)).astimezone(
        zone_for("UTC")
    )


def get_planned(db: DbSession, planned_id: uuid.UUID, user: User) -> PlannedTransaction:
    planned = db.get(PlannedTransaction, planned_id)
    if planned is None:
        raise NotFound("Planned transaction not found.", code="PLANNED_TRANSACTION_NOT_FOUND")
    get_viewable_account(db, planned.account_id, user)
    return planned


def _require_open(planned: PlannedTransaction) -> None:
    if planned.status is PlannedStatus.COMPLETED:
        raise Conflict(
            "This item has already been completed.",
            code="PLANNED_TRANSACTION_ALREADY_COMPLETED",
        )
    if planned.status is PlannedStatus.CANCELLED:
        raise Conflict("This item was cancelled.", code="PLANNED_TRANSACTION_CANCELLED")


# ------------------------------------------------------------------ reminders


def schedule_reminder(
    db: DbSession,
    *,
    user: User,
    planned: PlannedTransaction,
    days_before: int | None,
) -> Reminder | None:
    """Create the reminder for a planned item, replacing any pending one."""
    cancel_reminders(db, planned.id)
    if days_before is None:
        return None

    remind_at = planned.expected_at - timedelta(days=days_before)
    reminder = Reminder(
        user_id=user.id,
        entity_type=ReminderEntity.PLANNED_TRANSACTION,
        entity_id=planned.id,
        remind_at=remind_at,
        status=ReminderStatus.PENDING,
    )
    db.add(reminder)
    db.flush()
    return reminder


def cancel_reminders(db: DbSession, entity_id: uuid.UUID) -> None:
    pending = db.scalars(
        select(Reminder).where(
            Reminder.entity_id == entity_id, Reminder.status == ReminderStatus.PENDING
        )
    ).all()
    for reminder in pending:
        reminder.status = ReminderStatus.CANCELLED


# ---------------------------------------------------------------------- create


def create_planned(
    db: DbSession,
    *,
    user: User,
    account_id: uuid.UUID,
    planned_type: PlannedType,
    amount: Decimal,
    expected_at: datetime,
    description: str,
    category_id: uuid.UUID | None = None,
    notes: str | None = None,
    reminder_days_before: int | None = None,
) -> PlannedTransaction:
    account = get_transactable_account(db, account_id, user)
    if amount <= 0:
        raise ValidationFailed(
            details=[{"field": "amount", "message": "Amount must be greater than zero."}]
        )

    expected_at = ensure_aware(expected_at, user.timezone)
    planned = PlannedTransaction(
        account_id=account.id,
        planned_type=planned_type,
        amount=amount,
        currency=account.currency,
        expected_at=expected_at,
        occurrence_date=_local_date(expected_at, user.timezone),
        category_id=category_id,
        description=description.strip(),
        notes=notes,
        status=PlannedStatus.UPCOMING,
        source=PlannedSource.ONE_TIME,
        created_by=user.id,
    )
    db.add(planned)
    db.flush()

    schedule_reminder(db, user=user, planned=planned, days_before=reminder_days_before)
    return planned


# ------------------------------------------------------------------- lifecycle


def complete_planned(
    db: DbSession,
    *,
    user: User,
    planned_id: uuid.UUID,
    actual_amount: Decimal | None = None,
    actual_occurred_at: datetime | None = None,
    account_id: uuid.UUID | None = None,
    idempotency_key: str | None = None,
):
    """Turn a planned item into a real ledger entry.

    API spec section 22 requires this to be atomic, idempotent and locked
    against duplicates. The row is locked FOR UPDATE before its status is read,
    so two concurrent completions cannot both see it as open and both post.
    """
    # Lock first, then read status. Checking before locking is the race.
    locked = db.execute(
        select(PlannedTransaction).where(PlannedTransaction.id == planned_id).with_for_update()
    ).scalar_one_or_none()
    if locked is None:
        raise NotFound("Planned transaction not found.", code="PLANNED_TRANSACTION_NOT_FOUND")

    get_viewable_account(db, locked.account_id, user)

    # A replayed key returns the original outcome instead of posting again.
    if (
        idempotency_key
        and locked.completion_key == idempotency_key
        and locked.status is PlannedStatus.COMPLETED
    ):
        return locked

    _require_open(locked)

    account = get_transactable_account(db, account_id or locked.account_id, user)
    amount = actual_amount if actual_amount is not None else Decimal(locked.amount)
    occurred_at = (
        ensure_aware(actual_occurred_at, user.timezone)
        if actual_occurred_at is not None
        else locked.expected_at
    )

    posting = PostingService(db)
    record = (
        posting.record_income
        if locked.planned_type is PlannedType.INCOME
        else posting.record_expense
    )
    txn = record(
        account=account,
        amount=amount,
        currency=account.currency,
        occurred_at=occurred_at,
        actor_id=user.id,
        category_id=locked.category_id,
        description=locked.description,
        notes=locked.notes,
    )

    locked.status = PlannedStatus.COMPLETED
    locked.completed_transaction_id = txn.id
    locked.completion_key = idempotency_key
    cancel_reminders(db, locked.id)
    db.flush()
    return locked


def reschedule_planned(
    db: DbSession,
    *,
    user: User,
    planned_id: uuid.UUID,
    expected_at: datetime,
    amount: Decimal | None = None,
    reminder_days_before: int | None = None,
) -> PlannedTransaction:
    planned = get_planned(db, planned_id, user)
    _require_open(planned)
    get_transactable_account(db, planned.account_id, user)

    if planned.original_expected_at is None:
        planned.original_expected_at = planned.expected_at

    planned.expected_at = ensure_aware(expected_at, user.timezone)
    planned.occurrence_date = _local_date(planned.expected_at, user.timezone)
    if amount is not None:
        if amount <= 0:
            raise ValidationFailed(
                details=[{"field": "amount", "message": "Amount must be greater than zero."}]
            )
        planned.amount = amount
    # A moved date means the old reminder is wrong; it is recalculated, never kept.
    planned.status = PlannedStatus.UPCOMING
    schedule_reminder(db, user=user, planned=planned, days_before=reminder_days_before)
    db.flush()
    return planned


def cancel_planned(db: DbSession, *, user: User, planned_id: uuid.UUID) -> PlannedTransaction:
    planned = get_planned(db, planned_id, user)
    _require_open(planned)
    planned.status = PlannedStatus.CANCELLED
    cancel_reminders(db, planned.id)
    db.flush()
    return planned


def mark_missed(db: DbSession, *, user: User, planned_id: uuid.UUID) -> PlannedTransaction:
    planned = get_planned(db, planned_id, user)
    _require_open(planned)
    planned.status = PlannedStatus.MISSED
    db.flush()
    return planned


def skip_planned(db: DbSession, *, user: User, planned_id: uuid.UUID) -> PlannedTransaction:
    """Skip one occurrence of a recurring series without ending the rule."""
    planned = get_planned(db, planned_id, user)
    _require_open(planned)
    planned.status = PlannedStatus.SKIPPED
    cancel_reminders(db, planned.id)
    db.flush()
    return planned


# ------------------------------------------------------------------- querying


def list_planned(
    db: DbSession,
    *,
    user: User,
    status: PlannedStatus | None = None,
    planned_type: PlannedType | None = None,
    account_id: uuid.UUID | None = None,
    source: PlannedSource | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    include_closed: bool = False,
    limit: int = 100,
) -> list[PlannedTransaction]:
    account_ids = select(visible_accounts(user, include_archived=True).subquery().c.id)
    stmt = (
        select(PlannedTransaction)
        .options(
            selectinload(PlannedTransaction.account),
            selectinload(PlannedTransaction.category),
        )
        .where(PlannedTransaction.account_id.in_(account_ids))
    )

    if status is not None:
        stmt = stmt.where(PlannedTransaction.status == status)
    elif not include_closed:
        # The upcoming screen is about what still needs action.
        stmt = stmt.where(PlannedTransaction.status.in_(tuple(OPEN_PLANNED_STATUSES)))

    if planned_type is not None:
        stmt = stmt.where(PlannedTransaction.planned_type == planned_type)
    if account_id is not None:
        get_viewable_account(db, account_id, user)
        stmt = stmt.where(PlannedTransaction.account_id == account_id)
    if source is not None:
        stmt = stmt.where(PlannedTransaction.source == source)
    if date_from is not None:
        stmt = stmt.where(PlannedTransaction.expected_at >= day_start(date_from, user.timezone))
    if date_to is not None:
        stmt = stmt.where(PlannedTransaction.expected_at < day_end(date_to, user.timezone))

    return list(db.scalars(stmt.order_by(PlannedTransaction.expected_at).limit(limit)))


def bucket_for(planned: PlannedTransaction, *, today: date, timezone_name: str) -> str:
    """Grouping used by the upcoming screen (Implementation Plan Phase 11)."""
    day = _local_date(planned.expected_at, timezone_name)
    if planned.status is PlannedStatus.MISSED or day < today:
        return "OVERDUE"
    if day == today:
        return "TODAY"
    if day == today + timedelta(days=1):
        return "TOMORROW"
    if day <= today + timedelta(days=7):
        return "THIS_WEEK"
    return "LATER"


def refresh_due_status(db: DbSession, *, user: User) -> int:
    """Promote UPCOMING items whose day has arrived to DUE.

    Read-path housekeeping so the list is correct even if the worker is down.
    """
    today = _local_date(utcnow(), user.timezone)
    boundary = day_end(today, user.timezone)
    account_ids = select(visible_accounts(user, include_archived=True).subquery().c.id)
    rows = db.scalars(
        select(PlannedTransaction).where(
            PlannedTransaction.account_id.in_(account_ids),
            PlannedTransaction.status == PlannedStatus.UPCOMING,
            PlannedTransaction.expected_at < boundary,
        )
    ).all()
    for row in rows:
        row.status = PlannedStatus.DUE
    return len(rows)


# ------------------------------------------------------- recurrence generation


def create_rule(
    db: DbSession,
    *,
    user: User,
    account_id: uuid.UUID,
    planned_type: PlannedType,
    amount: Decimal,
    name: str,
    frequency: Frequency,
    start_date: date,
    interval_value: int = 1,
    end_date: date | None = None,
    category_id: uuid.UUID | None = None,
    notes: str | None = None,
    occurrence_hour: int = 9,
    reminder_days_before: int | None = None,
) -> RecurringRule:
    account = get_transactable_account(db, account_id, user)
    if amount <= 0:
        raise ValidationFailed(
            details=[{"field": "amount", "message": "Amount must be greater than zero."}]
        )
    if end_date is not None and end_date < start_date:
        raise ValidationFailed(
            details=[{"field": "end_date", "message": "End date cannot precede the start date."}]
        )

    rule = RecurringRule(
        account_id=account.id,
        planned_type=planned_type,
        amount=amount,
        currency=account.currency,
        category_id=category_id,
        name=name.strip(),
        notes=notes,
        frequency=frequency,
        interval_value=interval_value,
        start_date=start_date,
        end_date=end_date,
        next_occurrence_date=start_date,
        occurrence_hour=occurrence_hour,
        reminder_days_before=reminder_days_before,
        status=RecurringStatus.ACTIVE,
        created_by=user.id,
    )
    db.add(rule)
    db.flush()
    return rule


def generate_occurrences(
    db: DbSession,
    rule: RecurringRule,
    *,
    owner: User,
    today: date | None = None,
    window_days: int = GENERATION_WINDOW_DAYS,
) -> list[PlannedTransaction]:
    """Materialise this rule's occurrences inside the forward window.

    Idempotent: existing occurrence dates are skipped, and the database carries
    a unique constraint on (recurring_rule_id, occurrence_date) so a concurrent
    generation cannot duplicate one either.
    """
    if rule.status is not RecurringStatus.ACTIVE:
        return []

    today = today or _local_date(utcnow(), owner.timezone)
    window_end = today + timedelta(days=window_days)

    wanted = occurrences_between(
        start=rule.start_date,
        frequency=rule.frequency,
        interval=rule.interval_value,
        window_start=today,
        window_end=window_end,
        end_date=rule.end_date,
    )
    if not wanted:
        return []

    existing = set(
        db.scalars(
            select(PlannedTransaction.occurrence_date).where(
                PlannedTransaction.recurring_rule_id == rule.id
            )
        ).all()
    )

    created: list[PlannedTransaction] = []
    for day in wanted:
        if day in existing:
            continue
        expected_at = _stamp(day, rule.occurrence_hour, owner.timezone)
        planned = PlannedTransaction(
            account_id=rule.account_id,
            planned_type=rule.planned_type,
            amount=rule.amount,
            currency=rule.currency,
            expected_at=expected_at,
            occurrence_date=day,
            category_id=rule.category_id,
            description=rule.name,
            notes=rule.notes,
            status=PlannedStatus.UPCOMING,
            source=PlannedSource.RECURRING,
            recurring_rule_id=rule.id,
            created_by=rule.created_by,
        )
        db.add(planned)
        db.flush()
        created.append(planned)

        if rule.reminder_days_before is not None:
            db.add(
                Reminder(
                    user_id=rule.created_by,
                    entity_type=ReminderEntity.PLANNED_TRANSACTION,
                    entity_id=planned.id,
                    remind_at=expected_at - timedelta(days=rule.reminder_days_before),
                    status=ReminderStatus.PENDING,
                )
            )

    # Point the rule at the first occurrence still ahead of today.
    ahead = [d for d in wanted if d >= today]
    rule.next_occurrence_date = ahead[0] if ahead else None
    db.flush()
    return created


def set_rule_status(
    db: DbSession, *, user: User, rule_id: uuid.UUID, status: RecurringStatus
) -> RecurringRule:
    rule = db.get(RecurringRule, rule_id)
    if rule is None:
        raise NotFound("Recurring rule not found.", code="RECURRING_RULE_NOT_FOUND")
    get_transactable_account(db, rule.account_id, user)

    if rule.status is RecurringStatus.ENDED:
        raise Conflict("This series has already ended.", code="RECURRING_RULE_ENDED")

    rule.status = status
    if status in (RecurringStatus.PAUSED, RecurringStatus.ENDED):
        # Pausing must not leave generated future items sitting in the list.
        future = db.scalars(
            select(PlannedTransaction).where(
                PlannedTransaction.recurring_rule_id == rule.id,
                PlannedTransaction.status.in_((PlannedStatus.UPCOMING, PlannedStatus.DUE)),
                PlannedTransaction.expected_at > utcnow(),
            )
        ).all()
        for planned in future:
            planned.status = PlannedStatus.CANCELLED
            cancel_reminders(db, planned.id)
    db.flush()
    return rule


# --------------------------------------------------------------- notifications


def notify(
    db: DbSession,
    *,
    user_id: uuid.UUID,
    notification_type: NotificationType,
    title: str,
    body: str,
    entity_type: ReminderEntity | None = None,
    entity_id: uuid.UUID | None = None,
) -> Notification:
    notification = Notification(
        user_id=user_id,
        notification_type=notification_type,
        title=title,
        body=body,
        related_entity_type=entity_type,
        related_entity_id=entity_id,
    )
    db.add(notification)
    db.flush()
    return notification


def process_due_reminders(db: DbSession, *, now: datetime | None = None, limit: int = 500) -> int:
    """Turn due reminders into notifications.

    Phase 13 requires each reminder to be revalidated at send time: the thing it
    points at may have been completed, cancelled or deleted since it was
    scheduled, and a reminder for a bill you already paid is worse than none.
    """
    now = now or utcnow()
    due = db.scalars(
        select(Reminder)
        .where(Reminder.status == ReminderStatus.PENDING, Reminder.remind_at <= now)
        .order_by(Reminder.remind_at)
        .limit(limit)
        .with_for_update(skip_locked=True)
    ).all()

    sent = 0
    for reminder in due:
        if reminder.entity_type is not ReminderEntity.PLANNED_TRANSACTION:
            reminder.status = ReminderStatus.CANCELLED
            continue

        planned = db.get(PlannedTransaction, reminder.entity_id)
        if planned is None or planned.status not in OPEN_PLANNED_STATUSES:
            # Still valid to stop, just no longer worth telling anyone about.
            reminder.status = ReminderStatus.CANCELLED
            continue

        owner = db.get(User, reminder.user_id)
        if owner is None:
            reminder.status = ReminderStatus.CANCELLED
            continue

        local_day = _local_date(planned.expected_at, owner.timezone)
        verb = "due" if planned.planned_type is PlannedType.EXPENSE else "expected"
        notify(
            db,
            user_id=reminder.user_id,
            notification_type=NotificationType.PLANNED_DUE,
            title=f"{planned.description} {verb} {local_day.isoformat()}",
            body=f"{planned.currency} {planned.amount:,.2f}",
            entity_type=ReminderEntity.PLANNED_TRANSACTION,
            entity_id=planned.id,
        )
        reminder.status = ReminderStatus.SENT
        reminder.delivered_at = now
        sent += 1

    db.flush()
    return sent


def serialize_planned(planned: PlannedTransaction, *, timezone_name: str, today: date) -> dict:
    from app.core.money import serialize

    return {
        "id": str(planned.id),
        "planned_type": planned.planned_type.value,
        "amount": serialize(Decimal(planned.amount)),
        "currency": planned.currency,
        "expected_at": planned.expected_at.isoformat(),
        "occurrence_date": planned.occurrence_date.isoformat(),
        "description": planned.description,
        "notes": planned.notes,
        "status": planned.status.value,
        "source": planned.source.value,
        "bucket": bucket_for(planned, today=today, timezone_name=timezone_name),
        "account": (
            {"id": str(planned.account.id), "name": planned.account.name}
            if planned.account
            else None
        ),
        "category": (
            {"id": str(planned.category.id), "name": planned.category.name}
            if planned.category
            else None
        ),
        "recurring_rule_id": (
            str(planned.recurring_rule_id) if planned.recurring_rule_id else None
        ),
        "completed_transaction_id": (
            str(planned.completed_transaction_id) if planned.completed_transaction_id else None
        ),
    }


def serialize_rule(rule: RecurringRule) -> dict:
    from app.core.money import serialize

    return {
        "id": str(rule.id),
        "name": rule.name,
        "planned_type": rule.planned_type.value,
        "amount": serialize(Decimal(rule.amount)),
        "currency": rule.currency,
        "frequency": rule.frequency.value,
        "interval_value": rule.interval_value,
        "start_date": rule.start_date.isoformat(),
        "end_date": rule.end_date.isoformat() if rule.end_date else None,
        "next_occurrence_date": (
            rule.next_occurrence_date.isoformat() if rule.next_occurrence_date else None
        ),
        "status": rule.status.value,
        "reminder_days_before": rule.reminder_days_before,
        "account_id": str(rule.account_id),
        "category_id": str(rule.category_id) if rule.category_id else None,
    }
