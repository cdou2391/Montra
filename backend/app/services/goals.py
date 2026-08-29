"""Savings goals.

A goal holds no money and keeps no tally. Its progress is the sum of the
transfers tagged against it — real movements, derived on every read — which is
the same relationship a fee has to the charge it was taken on. That is what
lets several goals share one savings account: each contribution says which
goal it belongs to, so they can be told apart without any of them having a
balance of its own.

The gap that opens up is spending from the account without tagging it. The
goals then claim more than the account holds, and nothing in the write path
can prevent it — the money is the user's to spend. So it is checked once a
day instead, and a shortfall raises a notification rather than being silently
carried.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.core.errors import Conflict, NotFound, ValidationFailed
from app.db.enums import (
    AccountNature,
    GoalStatus,
    NotificationType,
    ReminderEntity,
    TransferStatus,
    Visibility,
    nature_for,
)
from app.models.finance import Account, Goal, Transfer
from app.models.user import User
from app.services import authz
from app.services.posting import PostingService

ZERO = Decimal("0")


def _contributed(db: DbSession, goal: Goal) -> Decimal:
    """What has been put in, less what has been taken back out.

    Read from the transfers themselves rather than a running total, so it
    cannot disagree with the ledger. A cancelled transfer stops counting for
    the same reason a cancelled transaction stops affecting a balance.
    """
    rows = db.execute(
        select(
            Transfer.source_account_id,
            Transfer.destination_account_id,
            Transfer.source_amount,
            Transfer.destination_amount,
        ).where(
            Transfer.goal_id == goal.id,
            Transfer.status == TransferStatus.COMPLETED,
        )
    ).all()

    total = ZERO
    for source_id, destination_id, source_amount, destination_amount in rows:
        if destination_id == goal.account_id:
            total += Decimal(destination_amount)
        elif source_id == goal.account_id:
            total -= Decimal(source_amount)
    return total


def _required_monthly(remaining: Decimal, target_date: date | None, today: date) -> Decimal | None:
    """What it takes each month from here to arrive on time.

    None where there is no date to arrive by, and None once it is reached:
    both are cases where a number would be answering a question nobody asked.
    """
    if target_date is None or remaining <= 0:
        return None
    months = (target_date.year - today.year) * 12 + (target_date.month - today.month)
    # The month you are in still counts; a target this month is one payment.
    months = max(months, 1) if target_date >= today else 0
    if months <= 0:
        return None
    return (remaining / months).quantize(Decimal("0.01"))


def _visible(access: authz.Access, context: str):
    if context == "family":
        if not access.in_family:
            return select(Goal).where(False)
        return select(Goal).where(
            Goal.family_id == access.family_id,
            Goal.visibility.in_((Visibility.FAMILY_VISIBLE, Visibility.SHARED)),
            Goal.status != GoalStatus.ARCHIVED,
        )
    return select(Goal).where(
        Goal.owner_user_id == access.user.id,
        Goal.status != GoalStatus.ARCHIVED,
    )


def serialize_goal(db: DbSession, goal: Goal, *, today: date) -> dict:
    from app.core.money import serialize

    saved = _contributed(db, goal)
    target = Decimal(goal.target_amount)
    remaining = target - saved
    return {
        "id": str(goal.id),
        "name": goal.name,
        "target_amount": serialize(target),
        "saved": serialize(saved),
        # Negative is not useful here: past the target you are done, not
        # "minus 5,000 to go".
        "remaining": serialize(max(remaining, ZERO)),
        "progress_percent": str(
            (saved / target * 100).quantize(Decimal("0.1")) if target > 0 else Decimal("0")
        ),
        "currency": goal.currency,
        "target_date": goal.target_date.isoformat() if goal.target_date else None,
        "required_monthly": (
            serialize(value)
            if (value := _required_monthly(remaining, goal.target_date, today)) is not None
            else None
        ),
        "account": {"id": str(goal.account_id), "name": goal.account.name if goal.account else ""},
        "status": goal.status.value,
        "achieved_at": goal.achieved_at.isoformat() if goal.achieved_at else None,
        "visibility": goal.visibility.value,
    }


def list_goals(
    db: DbSession, *, user: User, context: str = "personal", today: date | None = None
) -> list[dict]:
    from app.core.timezone import to_local
    from app.db.base import utcnow

    access = authz.resolve(db, user)
    today = today or to_local(utcnow(), user.timezone).date()
    goals = list(db.scalars(_visible(access, context)))
    rows = [serialize_goal(db, goal, today=today) for goal in goals]
    # Achieved ones drop to the bottom: they need nothing from you.
    rows.sort(key=lambda r: (r["status"] == "ACHIEVED", r["target_date"] or "9999", r["name"]))
    return rows


def create_goal(
    db: DbSession,
    *,
    user: User,
    name: str,
    account: Account,
    target_amount: Decimal,
    target_date: date | None = None,
    visibility: Visibility = Visibility.PRIVATE,
) -> Goal:
    if target_amount <= 0:
        raise ValidationFailed(
            details=[{"field": "target_amount", "message": "A goal must be more than zero."}]
        )
    if nature_for(account.account_type) is not AccountNature.ASSET:
        raise ValidationFailed(
            "A goal saves into an account that holds money, not one that owes it.",
            code="GOAL_ACCOUNT_NOT_ASSET",
        )

    from app.services.accounts import _resolve_sharing

    goal = Goal(
        owner_user_id=user.id,
        family_id=_resolve_sharing(db, user=user, visibility=visibility, family_id=None),
        account_id=account.id,
        name=name.strip(),
        target_amount=target_amount,
        currency=account.currency,
        target_date=target_date,
        visibility=visibility,
        created_by=user.id,
    )
    db.add(goal)
    db.flush()
    return goal


def get_goal(db: DbSession, goal_id: uuid.UUID, user: User) -> Goal:
    goal = db.get(Goal, goal_id)
    # 404 rather than 403, so the API never confirms someone else's exists.
    if goal is None or goal.owner_user_id != user.id:
        raise NotFound("Goal not found.", code="GOAL_NOT_FOUND")
    return goal


def update_goal(
    db: DbSession,
    *,
    goal: Goal,
    name: str | None = None,
    target_amount: Decimal | None = None,
    target_date: date | None = None,
    clear_target_date: bool = False,
) -> Goal:
    if name is not None:
        goal.name = name.strip()
    if target_amount is not None:
        if target_amount <= 0:
            raise ValidationFailed(
                details=[{"field": "target_amount", "message": "A goal must be more than zero."}]
            )
        goal.target_amount = target_amount
    # Separate flag, because None means "not supplied" and a date can be
    # deliberately removed.
    if clear_target_date:
        goal.target_date = None
    elif target_date is not None:
        goal.target_date = target_date
    db.flush()
    return goal


def contribute(
    db: DbSession,
    *,
    user: User,
    goal: Goal,
    source: Account,
    amount: Decimal,
    occurred_at: datetime,
    idempotency_key: str | None = None,
) -> Transfer:
    """Move money into the goal's account and tag it.

    A contribution is an ordinary transfer — it goes through the posting engine
    like any other, and net worth does not change because money only moved.
    The tag is what makes it a contribution rather than a transfer.
    """
    if goal.status is GoalStatus.ARCHIVED:
        raise Conflict("That goal is archived.", code="GOAL_ARCHIVED")
    if source.id == goal.account_id:
        raise ValidationFailed(
            "Choose an account to move the money from.",
            code="GOAL_SOURCE_IS_TARGET",
        )

    transfer = PostingService(db).transfer_funds(
        source=source,
        destination=goal.account,
        source_amount=amount,
        destination_amount=amount,
        occurred_at=occurred_at,
        actor_id=user.id,
        notes=f"Towards {goal.name}",
        idempotency_key=idempotency_key,
    )
    transfer.goal_id = goal.id
    db.flush()
    refresh_status(db, goal)
    return transfer


def refresh_status(db: DbSession, goal: Goal) -> Goal:
    """Mark a goal achieved once it is, and un-mark it if it stops being.

    Checked on the write paths and again by the daily sweep, so a goal that
    reaches its target through a transfer made anywhere still notices.
    """
    from app.db.base import utcnow

    if goal.status is GoalStatus.ARCHIVED:
        return goal
    reached = _contributed(db, goal) >= Decimal(goal.target_amount)
    if reached and goal.status is not GoalStatus.ACHIEVED:
        goal.status = GoalStatus.ACHIEVED
        goal.achieved_at = utcnow()
        notify_achieved(db, goal)
    elif not reached and goal.status is GoalStatus.ACHIEVED:
        # Money came back out. Saying it is still achieved would be a claim the
        # ledger no longer supports.
        goal.status = GoalStatus.ACTIVE
        goal.achieved_at = None
    db.flush()
    return goal


def set_visibility(
    db: DbSession, *, user: User, goal: Goal, visibility: Visibility
) -> Goal:
    """Share a goal with the household, or take it back.

    Derived from the caller's own membership rather than a family_id in the
    request, so a client cannot share a goal into a household it is not in.
    Taking it back to private clears the household link with it.
    """
    from app.services.accounts import _resolve_sharing

    goal.family_id = _resolve_sharing(
        db, user=user, visibility=visibility, family_id=goal.family_id
    )
    goal.visibility = visibility
    db.flush()
    return goal


def archive_goal(db: DbSession, goal: Goal) -> Goal:
    if goal.status is GoalStatus.ARCHIVED:
        raise Conflict("Goal is already archived.", code="GOAL_ALREADY_ARCHIVED")
    goal.status = GoalStatus.ARCHIVED
    db.flush()
    return goal


def notify_achieved(db: DbSession, goal: Goal) -> None:
    from app.core.money import format_money
    from app.services.planning import notify

    notify(
        db,
        user_id=goal.owner_user_id,
        notification_type=NotificationType.GOAL_ACHIEVED,
        title=f"{goal.name} reached",
        body=(
            f"You have saved {format_money(Decimal(goal.target_amount), goal.currency)}. "
            "The money stays where it is until you move it."
        ),
        entity_type=ReminderEntity.GOAL,
        entity_id=goal.id,
    )


# ------------------------------------------------------------- reconciliation


def shortfalls(db: DbSession) -> list[dict]:
    """Accounts whose goals claim more than the account holds.

    Nothing in the write path can prevent this: the money is the user's to
    spend, and spending it untagged is a normal thing to do. So it is measured
    rather than forbidden — per account, because goals sharing one account
    share its balance too, and only the total tells you whether it is short.
    """
    posting = PostingService(db)
    goals = list(
        db.scalars(select(Goal).where(Goal.status != GoalStatus.ARCHIVED))
    )

    by_account: dict[uuid.UUID, list[Goal]] = {}
    for goal in goals:
        by_account.setdefault(goal.account_id, []).append(goal)

    found = []
    for account_id, account_goals in by_account.items():
        account = db.get(Account, account_id)
        if account is None:
            continue
        claimed = sum((_contributed(db, g) for g in account_goals), ZERO)
        balance = posting.balance_of(account)
        if claimed > balance:
            found.append(
                {
                    "account": account,
                    "claimed": claimed,
                    "balance": balance,
                    "short_by": claimed - balance,
                    "goals": account_goals,
                }
            )
    return found


def notify_shortfalls(db: DbSession) -> int:
    """One notice per account per day, at most.

    The task runs daily and the condition persists until the user acts, so
    without the guard it would say the same thing every morning.
    """
    from datetime import timedelta

    from app.core.money import format_money
    from app.db.base import utcnow
    from app.models.planning import Notification
    from app.services.planning import notify

    since = utcnow() - timedelta(hours=20)
    sent = 0

    for row in shortfalls(db):
        account = row["account"]
        recipient = account.owner_user_id or account.created_by
        already = db.scalar(
            select(Notification.id).where(
                Notification.user_id == recipient,
                Notification.notification_type == NotificationType.GOAL_SHORTFALL,
                Notification.related_entity_id == account.id,
                Notification.created_at >= since,
            )
        )
        if already:
            continue

        names = ", ".join(g.name for g in row["goals"])
        notify(
            db,
            user_id=recipient,
            notification_type=NotificationType.GOAL_SHORTFALL,
            title=f"{account.name} is short of its goals",
            body=(
                f"{names} together account for "
                f"{format_money(row['claimed'], account.currency)}, but {account.name} holds "
                f"{format_money(row['balance'], account.currency)} — "
                f"{format_money(row['short_by'], account.currency)} less. "
                "Money was probably spent from it without being tagged."
            ),
            entity_type=ReminderEntity.GOAL,
            entity_id=account.id,
        )
        sent += 1
    return sent


def refresh_all(db: DbSession) -> int:
    """Bring every goal's status in line with the ledger."""
    goals = list(db.scalars(select(Goal).where(Goal.status != GoalStatus.ARCHIVED)))
    for goal in goals:
        refresh_status(db, goal)
    return len(goals)
