from __future__ import annotations

from datetime import datetime, date, timedelta, timezone
from zoneinfo import ZoneInfo

DEFAULT_TZ = ZoneInfo("America/Detroit")


def local_day_window_ms(day: date, tz=DEFAULT_TZ) -> tuple[int, int]:
    start_local = datetime(day.year, day.month, day.day, 0, 0, 0, tzinfo=tz)
    next_local = start_local + timedelta(days=1)

    start_utc = start_local.astimezone(timezone.utc)
    end_utc = next_local.astimezone(timezone.utc)

    return (
        int(start_utc.timestamp() * 1000),
        int(end_utc.timestamp() * 1000),
    )


def iter_days(start: date, end: date):
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)
