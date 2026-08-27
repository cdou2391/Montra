"""Timezone handling for user-facing date boundaries.

Timestamps are stored UTC. "August transactions" means August where the user
lives, so date filters widen into UTC instants using their own timezone.
"""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.errors import ValidationFailed

UTC = ZoneInfo("UTC")


def zone_for(timezone_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError):
        return UTC


def validate_timezone(timezone_name: str) -> str:
    try:
        ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValidationFailed(
            details=[{"field": "timezone", "message": "Not a recognised timezone."}]
        ) from exc
    return timezone_name


def ensure_aware(value: datetime, timezone_name: str) -> datetime:
    """Attach the user's timezone to a naive datetime, then normalise to UTC.

    "2026-08-24T14:30" with no offset means half past two where they are.
    """
    if value.tzinfo is None:
        value = value.replace(tzinfo=zone_for(timezone_name))
    return value.astimezone(UTC)


def day_start(day: date, timezone_name: str) -> datetime:
    """First instant of that local day, as UTC."""
    return datetime.combine(day, time.min, tzinfo=zone_for(timezone_name)).astimezone(UTC)


def day_end(day: date, timezone_name: str) -> datetime:
    """First instant of the following local day, as UTC. An exclusive upper
    bound, so 23:59:59.999 on the last day is still included."""
    return day_start(day + timedelta(days=1), timezone_name)


def to_local(value: datetime, timezone_name: str) -> datetime:
    return value.astimezone(zone_for(timezone_name))
