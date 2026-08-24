"""Recurrence date arithmetic.

Kept separate from persistence so the rules can be tested directly, and so the
generation task has nothing to decide for itself.

Month-based recurrence anchors on the rule's start day and clamps to the length
of each target month: a rule starting on the 31st lands on the 30th in April
and the 28th in February, then returns to the 31st in May. Stepping from the
previous occurrence instead would let a rule drift permanently earlier after
one short month.
"""

import calendar
from datetime import date, timedelta

from app.db.enums import Frequency

MONTHS_PER_STEP = {
    Frequency.MONTHLY: 1,
    Frequency.QUARTERLY: 3,
    Frequency.YEARLY: 12,
}


def _add_months(anchor: date, months: int) -> date:
    total = anchor.month - 1 + months
    year = anchor.year + total // 12
    month = total % 12 + 1
    return date(year, month, min(anchor.day, calendar.monthrange(year, month)[1]))


def occurrence_after(
    *,
    previous: date,
    frequency: Frequency,
    interval: int,
    anchor: date,
) -> date:
    """The occurrence that follows `previous` for this rule.

    `anchor` is the rule's start date, which fixes the day-of-month for
    month-based frequencies.
    """
    if interval < 1:
        raise ValueError("interval must be at least 1")

    if frequency is Frequency.DAILY:
        return previous + timedelta(days=interval)
    if frequency is Frequency.WEEKLY:
        return previous + timedelta(weeks=interval)

    months = MONTHS_PER_STEP[frequency] * interval
    # Count whole steps from the anchor so a clamped short month does not
    # permanently pull the series earlier.
    steps = 0
    candidate = anchor
    while candidate <= previous:
        steps += 1
        candidate = _add_months(anchor, months * steps)
    return candidate


def occurrences_between(
    *,
    start: date,
    frequency: Frequency,
    interval: int,
    window_start: date,
    window_end: date,
    end_date: date | None = None,
    limit: int = 500,
) -> list[date]:
    """Every occurrence falling inside the window, inclusive.

    `limit` is a safety valve: a daily rule over a long window should not be
    able to generate an unbounded list.
    """
    results: list[date] = []
    current = start

    # Walk forward to the window without emitting anything before it.
    guard = 0
    while current < window_start:
        if end_date is not None and current > end_date:
            return results
        guard += 1
        if guard > 10_000:
            raise ValueError("recurrence failed to reach the window")
        current = occurrence_after(
            previous=current, frequency=frequency, interval=interval, anchor=start
        )

    while current <= window_end and len(results) < limit:
        if end_date is not None and current > end_date:
            break
        results.append(current)
        current = occurrence_after(
            previous=current, frequency=frequency, interval=interval, anchor=start
        )

    return results
