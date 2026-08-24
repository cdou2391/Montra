"""Planned transactions, recurrence and reminders (Phases 11-13).

The governing rule under test: a planned transaction is not a ledger entry
until it is completed.
"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.errors import Conflict, ValidationFailed
from app.db.enums import (
    Frequency,
    PlannedSource,
    PlannedStatus,
    PlannedType,
    RecurringStatus,
    ReminderStatus,
)
from app.models.finance import Transaction
from app.models.planning import Notification, PlannedTransaction, Reminder
from app.services import planning
from app.services.posting import PostingService
from app.services.recurrence import occurrence_after, occurrences_between

SOON = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)


def _make(db, user, account, **kw):
    return planning.create_planned(
        db,
        user=user,
        account_id=account.id,
        planned_type=kw.pop("planned_type", PlannedType.EXPENSE),
        amount=kw.pop("amount", Decimal("450000")),
        expected_at=kw.pop("expected_at", SOON),
        description=kw.pop("description", "School Fees"),
        **kw,
    )


# ------------------------------------------------- planned is not a ledger entry


def test_creating_a_planned_item_moves_no_money(db, bank_account, user):
    _make(db, user, bank_account)
    db.commit()
    assert PostingService(db).balance_of(bank_account) == Decimal("1000000.0000")
    assert db.scalars(select(Transaction)).all() == []


def test_cancelling_writes_no_ledger_entry(db, bank_account, user):
    planned = _make(db, user, bank_account)
    db.commit()
    planning.cancel_planned(db, user=user, planned_id=planned.id)
    db.commit()
    assert planned.status is PlannedStatus.CANCELLED
    assert db.scalars(select(Transaction)).all() == []
    assert PostingService(db).balance_of(bank_account) == Decimal("1000000.0000")


def test_rescheduling_writes_no_ledger_entry(db, bank_account, user):
    planned = _make(db, user, bank_account)
    db.commit()
    planning.reschedule_planned(
        db,
        user=user,
        planned_id=planned.id,
        expected_at=datetime(2026, 9, 15, 9, 0, tzinfo=UTC),
    )
    db.commit()
    assert db.scalars(select(Transaction)).all() == []
    # The original date is kept so a slipped bill is still visible as slipped.
    assert planned.original_expected_at == SOON


# ------------------------------------------------------------------ completion


def test_completion_posts_to_the_ledger(db, bank_account, user):
    planned = _make(db, user, bank_account)
    db.commit()
    planning.complete_planned(db, user=user, planned_id=planned.id)
    db.commit()

    assert planned.status is PlannedStatus.COMPLETED
    assert planned.completed_transaction_id is not None
    assert PostingService(db).balance_of(bank_account) == Decimal("550000.0000")


def test_completed_income_increases_the_balance(db, bank_account, user):
    planned = _make(
        db, user, bank_account, planned_type=PlannedType.INCOME, amount=Decimal("2500000")
    )
    db.commit()
    planning.complete_planned(db, user=user, planned_id=planned.id)
    db.commit()
    assert PostingService(db).balance_of(bank_account) == Decimal("3500000.0000")


def test_completion_on_a_credit_card_raises_debt(db, credit_card, user):
    planned = _make(db, user, credit_card, amount=Decimal("85000"))
    db.commit()
    planning.complete_planned(db, user=user, planned_id=planned.id)
    db.commit()
    # Direction still resolved by the posting engine from account nature.
    assert PostingService(db).balance_of(credit_card) == Decimal("285000.0000")


def test_completion_can_override_amount_and_time(db, bank_account, user):
    planned = _make(db, user, bank_account)
    db.commit()
    planning.complete_planned(
        db,
        user=user,
        planned_id=planned.id,
        actual_amount=Decimal("445000"),
        actual_occurred_at=datetime(2026, 9, 2, 16, 45, tzinfo=UTC),
    )
    db.commit()
    txn = db.get(Transaction, planned.completed_transaction_id)
    assert txn.amount == Decimal("445000.0000")
    assert txn.occurred_at.hour == 16
    # The plan keeps its own expected time; only the actual entry moved.
    assert planned.expected_at == SOON


def test_double_completion_is_refused(db, bank_account, user):
    planned = _make(db, user, bank_account)
    db.commit()
    planning.complete_planned(db, user=user, planned_id=planned.id)
    db.commit()
    with pytest.raises(Conflict) as exc:
        planning.complete_planned(db, user=user, planned_id=planned.id)
    assert exc.value.code == "PLANNED_TRANSACTION_ALREADY_COMPLETED"
    # And critically, no second ledger entry.
    assert len(db.scalars(select(Transaction)).all()) == 1


def test_replaying_the_same_key_does_not_post_twice(db, bank_account, user):
    planned = _make(db, user, bank_account)
    db.commit()
    planning.complete_planned(db, user=user, planned_id=planned.id, idempotency_key="k1")
    db.commit()
    again = planning.complete_planned(db, user=user, planned_id=planned.id, idempotency_key="k1")
    db.commit()
    assert again.id == planned.id
    assert len(db.scalars(select(Transaction)).all()) == 1
    assert PostingService(db).balance_of(bank_account) == Decimal("550000.0000")


def test_cancelled_item_cannot_be_completed(db, bank_account, user):
    planned = _make(db, user, bank_account)
    db.commit()
    planning.cancel_planned(db, user=user, planned_id=planned.id)
    db.commit()
    with pytest.raises(Conflict) as exc:
        planning.complete_planned(db, user=user, planned_id=planned.id)
    assert exc.value.code == "PLANNED_TRANSACTION_CANCELLED"


def test_completion_cancels_the_reminder(db, bank_account, user):
    planned = _make(db, user, bank_account, reminder_days_before=3)
    db.commit()
    assert db.scalars(select(Reminder)).all()[0].status is ReminderStatus.PENDING

    planning.complete_planned(db, user=user, planned_id=planned.id)
    db.commit()
    assert db.scalars(select(Reminder)).all()[0].status is ReminderStatus.CANCELLED


# ------------------------------------------------------------------- reminders


def test_reminder_is_scheduled_before_the_due_moment(db, bank_account, user):
    planned = _make(db, user, bank_account, reminder_days_before=3)
    db.commit()
    reminder = db.scalars(select(Reminder)).all()[0]
    assert reminder.remind_at == planned.expected_at - timedelta(days=3)


def test_rescheduling_recalculates_the_reminder(db, bank_account, user):
    planned = _make(db, user, bank_account, reminder_days_before=3)
    db.commit()
    planning.reschedule_planned(
        db,
        user=user,
        planned_id=planned.id,
        expected_at=datetime(2026, 10, 1, 9, 0, tzinfo=UTC),
        reminder_days_before=1,
    )
    db.commit()
    pending = [r for r in db.scalars(select(Reminder)).all() if r.status is ReminderStatus.PENDING]
    assert len(pending) == 1
    assert pending[0].remind_at == datetime(2026, 9, 30, 9, 0, tzinfo=UTC)


def test_due_reminder_creates_a_notification(db, bank_account, user):
    planned = _make(db, user, bank_account, reminder_days_before=3)
    db.commit()
    sent = planning.process_due_reminders(db, now=planned.expected_at)
    db.commit()
    assert sent == 1
    note = db.scalars(select(Notification)).all()[0]
    assert note.user_id == user.id
    assert "School Fees" in note.title
    assert db.scalars(select(Reminder)).all()[0].status is ReminderStatus.SENT


def test_reminder_not_yet_due_is_left_alone(db, bank_account, user):
    _make(db, user, bank_account, reminder_days_before=3)
    db.commit()
    assert planning.process_due_reminders(db, now=datetime(2026, 8, 1, tzinfo=UTC)) == 0
    assert db.scalars(select(Notification)).all() == []


def test_reminder_for_a_completed_item_is_dropped(db, bank_account, user):
    """Phase 13 revalidation: a reminder for a bill you already paid is worse
    than no reminder at all."""
    planned = _make(db, user, bank_account, reminder_days_before=3)
    db.commit()
    # Complete it without going through the cancel path, as a stale reminder
    # left by an earlier version of the code would look.
    planned.status = PlannedStatus.COMPLETED
    db.commit()

    sent = planning.process_due_reminders(db, now=planned.expected_at)
    db.commit()
    assert sent == 0
    assert db.scalars(select(Notification)).all() == []
    assert db.scalars(select(Reminder)).all()[0].status is ReminderStatus.CANCELLED


def test_reminders_are_not_sent_twice(db, bank_account, user):
    planned = _make(db, user, bank_account, reminder_days_before=3)
    db.commit()
    planning.process_due_reminders(db, now=planned.expected_at)
    db.commit()
    assert planning.process_due_reminders(db, now=planned.expected_at) == 0
    db.commit()
    assert len(db.scalars(select(Notification)).all()) == 1


# ------------------------------------------------------------------ recurrence


@pytest.mark.parametrize(
    ("previous", "freq", "interval", "anchor", "expected"),
    [
        (date(2026, 8, 1), Frequency.DAILY, 1, date(2026, 8, 1), date(2026, 8, 2)),
        (date(2026, 8, 1), Frequency.WEEKLY, 2, date(2026, 8, 1), date(2026, 8, 15)),
        (date(2026, 8, 15), Frequency.MONTHLY, 1, date(2026, 8, 15), date(2026, 9, 15)),
        (date(2026, 8, 15), Frequency.QUARTERLY, 1, date(2026, 8, 15), date(2026, 11, 15)),
        (date(2026, 8, 15), Frequency.YEARLY, 1, date(2026, 8, 15), date(2027, 8, 15)),
    ],
)
def test_occurrence_after(previous, freq, interval, anchor, expected):
    assert (
        occurrence_after(previous=previous, frequency=freq, interval=interval, anchor=anchor)
        == expected
    )


def test_monthly_rule_on_the_31st_does_not_drift():
    """A rule anchored on the 31st clamps in short months, then recovers.

    Stepping from the previous occurrence would pull the series permanently
    earlier after the first February.
    """
    days = occurrences_between(
        start=date(2027, 1, 31),
        frequency=Frequency.MONTHLY,
        interval=1,
        window_start=date(2027, 1, 1),
        window_end=date(2027, 6, 30),
    )
    assert days == [
        date(2027, 1, 31),
        date(2027, 2, 28),
        date(2027, 3, 31),
        date(2027, 4, 30),
        date(2027, 5, 31),
        date(2027, 6, 30),
    ]


def test_occurrences_respect_the_end_date():
    days = occurrences_between(
        start=date(2026, 8, 1),
        frequency=Frequency.MONTHLY,
        interval=1,
        window_start=date(2026, 8, 1),
        window_end=date(2027, 8, 1),
        end_date=date(2026, 10, 15),
    )
    assert days == [date(2026, 8, 1), date(2026, 9, 1), date(2026, 10, 1)]


# --------------------------------------------------------- generation from rules


def _rule(db, user, account, **kw):
    return planning.create_rule(
        db,
        user=user,
        account_id=account.id,
        planned_type=kw.pop("planned_type", PlannedType.EXPENSE),
        amount=kw.pop("amount", Decimal("15000")),
        name=kw.pop("name", "Netflix"),
        frequency=kw.pop("frequency", Frequency.MONTHLY),
        start_date=kw.pop("start_date", date(2026, 8, 26)),
        **kw,
    )


def test_rule_generates_planned_items_not_transactions(db, bank_account, user):
    rule = _rule(db, user, bank_account)
    db.commit()
    created = planning.generate_occurrences(db, rule, owner=user, today=date(2026, 8, 24))
    db.commit()

    assert len(created) >= 3  # 90-day window over a monthly rule
    assert all(p.source is PlannedSource.RECURRING for p in created)
    assert db.scalars(select(Transaction)).all() == []
    assert PostingService(db).balance_of(bank_account) == Decimal("1000000.0000")


def test_generation_is_idempotent(db, bank_account, user):
    rule = _rule(db, user, bank_account)
    db.commit()
    first = planning.generate_occurrences(db, rule, owner=user, today=date(2026, 8, 24))
    db.commit()
    second = planning.generate_occurrences(db, rule, owner=user, today=date(2026, 8, 24))
    db.commit()

    assert len(second) == 0
    assert len(db.scalars(select(PlannedTransaction)).all()) == len(first)


def test_duplicate_occurrence_is_refused_by_the_database(db, bank_account, user):
    """The unique constraint is the real guard; the in-Python check is a
    convenience on top of it."""
    from sqlalchemy.exc import IntegrityError

    rule = _rule(db, user, bank_account)
    db.commit()
    planning.generate_occurrences(db, rule, owner=user, today=date(2026, 8, 24))
    db.commit()

    existing = db.scalars(
        select(PlannedTransaction).where(PlannedTransaction.recurring_rule_id == rule.id)
    ).first()
    db.add(
        PlannedTransaction(
            account_id=bank_account.id,
            planned_type=PlannedType.EXPENSE,
            amount=Decimal("15000"),
            currency="RWF",
            expected_at=existing.expected_at,
            occurrence_date=existing.occurrence_date,
            description="Duplicate",
            status=PlannedStatus.UPCOMING,
            source=PlannedSource.RECURRING,
            recurring_rule_id=rule.id,
            created_by=user.id,
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_generation_stops_at_the_end_date(db, bank_account, user):
    rule = _rule(db, user, bank_account, end_date=date(2026, 9, 30))
    db.commit()
    created = planning.generate_occurrences(db, rule, owner=user, today=date(2026, 8, 24))
    db.commit()
    assert all(p.occurrence_date <= date(2026, 9, 30) for p in created)


def test_pausing_a_rule_clears_its_future_items(db, bank_account, user):
    rule = _rule(db, user, bank_account)
    db.commit()
    planning.generate_occurrences(db, rule, owner=user)
    db.commit()

    planning.set_rule_status(db, user=user, rule_id=rule.id, status=RecurringStatus.PAUSED)
    db.commit()

    remaining = db.scalars(
        select(PlannedTransaction).where(
            PlannedTransaction.recurring_rule_id == rule.id,
            PlannedTransaction.status.in_((PlannedStatus.UPCOMING, PlannedStatus.DUE)),
        )
    ).all()
    assert remaining == []


def test_paused_rule_generates_nothing(db, bank_account, user):
    rule = _rule(db, user, bank_account)
    db.commit()
    planning.set_rule_status(db, user=user, rule_id=rule.id, status=RecurringStatus.PAUSED)
    db.commit()
    assert planning.generate_occurrences(db, rule, owner=user) == []


def test_ended_rule_cannot_be_resumed(db, bank_account, user):
    rule = _rule(db, user, bank_account)
    db.commit()
    planning.set_rule_status(db, user=user, rule_id=rule.id, status=RecurringStatus.ENDED)
    db.commit()
    with pytest.raises(Conflict):
        planning.set_rule_status(db, user=user, rule_id=rule.id, status=RecurringStatus.ACTIVE)


def test_rule_rejects_an_end_before_its_start(db, bank_account, user):
    with pytest.raises(ValidationFailed):
        _rule(db, user, bank_account, end_date=date(2026, 1, 1))


# --------------------------------------------------------------------- buckets


@pytest.mark.parametrize(
    ("offset_days", "expected"),
    [(-3, "OVERDUE"), (0, "TODAY"), (1, "TOMORROW"), (5, "THIS_WEEK"), (40, "LATER")],
)
def test_bucketing(db, bank_account, user, offset_days, expected):
    today = date(2026, 9, 1)
    when = datetime(2026, 9, 1, 9, 0, tzinfo=UTC) + timedelta(days=offset_days)
    planned = _make(db, user, bank_account, expected_at=when)
    db.commit()
    assert planning.bucket_for(planned, today=today, timezone_name="UTC") == expected


def test_upcoming_list_excludes_closed_items_by_default(db, bank_account, user):
    keep = _make(db, user, bank_account, description="Rent")
    drop = _make(db, user, bank_account, description="Old", expected_at=SOON + timedelta(days=1))
    db.commit()
    planning.cancel_planned(db, user=user, planned_id=drop.id)
    db.commit()

    rows = planning.list_planned(db, user=user)
    assert [r.id for r in rows] == [keep.id]


def test_another_user_cannot_see_planned_items(db, bank_account, user, other_user):
    _make(db, user, bank_account)
    db.commit()
    assert planning.list_planned(db, user=other_user) == []
