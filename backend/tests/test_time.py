"""Time-of-day handling.

Timestamps are stored UTC and interpreted against the user's timezone. These
guard the boundary cases where an hours-off bug would be invisible in testing
but wrong on a statement.
"""

from datetime import UTC, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.core.timezone import day_end, day_start, ensure_aware
from app.services.posting import PostingService

KIGALI = "Africa/Kigali"  # UTC+2, no DST
NEW_YORK = "America/New_York"  # UTC-5/-4, observes DST


def test_time_of_day_is_preserved(db, bank_account, user):
    posting = PostingService(db)
    txn = posting.record_expense(
        account=bank_account,
        amount=Decimal("1000"),
        currency="RWF",
        occurred_at=datetime(2026, 8, 24, 14, 37, 12, tzinfo=UTC),
        actor_id=user.id,
    )
    db.commit()
    db.refresh(txn)
    assert txn.occurred_at.hour == 14
    assert txn.occurred_at.minute == 37
    assert txn.occurred_at.second == 12


def test_created_at_is_distinct_from_occurred_at(db, bank_account, user):
    """Recording a past expense today must not stamp it as happening today."""
    posting = PostingService(db)
    txn = posting.record_expense(
        account=bank_account,
        amount=Decimal("1000"),
        currency="RWF",
        occurred_at=datetime(2026, 8, 1, 9, 0, tzinfo=UTC),
        actor_id=user.id,
    )
    db.commit()
    assert txn.occurred_at.date() != txn.created_at.date()


def test_same_day_transactions_order_by_time(db, bank_account, user):
    from app.services.transactions import list_transactions

    posting = PostingService(db)
    for hour in (8, 19, 13):
        posting.record_expense(
            account=bank_account,
            amount=Decimal("1000"),
            currency="RWF",
            occurred_at=datetime(2026, 8, 24, hour, 0, tzinfo=UTC),
            actor_id=user.id,
            description=f"{hour:02d}:00",
        )
    db.commit()

    rows, _ = list_transactions(db, user=user)
    assert [r.description for r in rows] == ["19:00", "13:00", "08:00"]


def test_naive_datetime_is_read_in_the_users_timezone(db):
    """14:30 posted by a Kigali user is 12:30 UTC, not 14:30 UTC."""
    naive = datetime(2026, 8, 24, 14, 30)
    assert ensure_aware(naive, KIGALI) == datetime(2026, 8, 24, 12, 30, tzinfo=UTC)


def test_aware_datetime_passes_through_unchanged(db):
    aware = datetime(2026, 8, 24, 14, 30, tzinfo=ZoneInfo(NEW_YORK))
    assert ensure_aware(aware, KIGALI) == aware.astimezone(UTC)


def test_local_day_boundaries_are_not_utc_boundaries(db):
    """A Kigali day starts at 22:00 UTC the evening before."""
    from datetime import date

    start = day_start(date(2026, 8, 24), KIGALI)
    assert start == datetime(2026, 8, 23, 22, 0, tzinfo=UTC)
    # Exclusive upper bound: the first instant of the next local day.
    assert day_end(date(2026, 8, 24), KIGALI) == datetime(2026, 8, 24, 22, 0, tzinfo=UTC)


def test_late_night_transaction_falls_on_the_local_day(db, bank_account, user):
    """23:30 in Kigali on the 24th is 21:30 UTC on the 24th, and must be
    returned when filtering for the 24th — not the 25th."""
    from datetime import date

    from app.services.transactions import list_transactions

    PostingService(db).record_expense(
        account=bank_account,
        amount=Decimal("1000"),
        currency="RWF",
        occurred_at=ensure_aware(datetime(2026, 8, 24, 23, 30), KIGALI),
        actor_id=user.id,
        description="Late night",
    )
    db.commit()

    on_the_day, _ = list_transactions(
        db, user=user, date_from=date(2026, 8, 24), date_to=date(2026, 8, 24)
    )
    assert [r.description for r in on_the_day] == ["Late night"]

    next_day, _ = list_transactions(
        db, user=user, date_from=date(2026, 8, 25), date_to=date(2026, 8, 25)
    )
    assert next_day == []


def test_date_range_upper_bound_is_inclusive_of_the_whole_day(db, bank_account, user):
    from datetime import date

    from app.services.transactions import list_transactions

    PostingService(db).record_expense(
        account=bank_account,
        amount=Decimal("1000"),
        currency="RWF",
        occurred_at=ensure_aware(datetime(2026, 8, 24, 23, 59, 59), KIGALI),
        actor_id=user.id,
    )
    db.commit()
    rows, _ = list_transactions(
        db, user=user, date_from=date(2026, 8, 1), date_to=date(2026, 8, 24)
    )
    assert len(rows) == 1


def test_balance_as_of_respects_time_not_just_date(db, bank_account, user):
    posting = PostingService(db)
    posting.record_expense(
        account=bank_account,
        amount=Decimal("50000"),
        currency="RWF",
        occurred_at=datetime(2026, 8, 24, 18, 0, tzinfo=UTC),
        actor_id=user.id,
    )
    db.commit()

    # Midday on the same date: the evening expense has not happened yet.
    assert posting.balance_of(
        bank_account, as_of=datetime(2026, 8, 24, 12, 0, tzinfo=UTC)
    ) == Decimal("1000000.0000")
    assert posting.balance_of(
        bank_account, as_of=datetime(2026, 8, 24, 23, 0, tzinfo=UTC)
    ) == Decimal("950000.0000")


def test_pagination_does_not_skip_same_second_transactions(db, bank_account, user):
    """Keyset pagination ties broken by id, so identical instants still page."""
    from app.services.transactions import list_transactions

    instant = datetime(2026, 8, 24, 14, 0, tzinfo=UTC)
    posting = PostingService(db)
    for i in range(6):
        posting.record_expense(
            account=bank_account,
            amount=Decimal("1000"),
            currency="RWF",
            occurred_at=instant,
            actor_id=user.id,
            description=f"txn-{i}",
        )
    db.commit()

    first, cursor = list_transactions(db, user=user, limit=3)
    assert cursor
    second, _ = list_transactions(db, user=user, limit=3, cursor=cursor)
    seen = {r.id for r in first} | {r.id for r in second}
    assert len(seen) == 6


def test_invalid_timezone_is_rejected_at_registration(db):
    import pytest

    from app.core.errors import ValidationFailed
    from app.services.auth import register_user

    with pytest.raises(ValidationFailed):
        register_user(
            db,
            email="bad-tz@example.com",
            password="a-good-passphrase-1",
            display_name="Bad TZ",
            base_currency="RWF",
            timezone="Mars/Olympus_Mons",
        )
