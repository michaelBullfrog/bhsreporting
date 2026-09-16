from __future__ import annotations

from datetime import datetime, date, timedelta, timezone
from zoneinfo import ZoneInfo

DEFAULT_TZ = ZoneInfo("America/Detroit")
MAX_WXCC_WINDOW_MS = 86_400_000


def local_day_window_ms(day: date, tz=DEFAULT_TZ) -> tuple[int, int]:
    start_local = datetime(day.year, day.month, day.day, 0, 0, 0, tzinfo=tz)
    next_local = start_local + timedelta(days=1)

    start_utc = start_local.astimezone(timezone.utc)
    end_utc = next_local.astimezone(timezone.utc)

    return (
        int(start_utc.timestamp() * 1000),
        int(end_utc.timestamp() * 1000),
    )


def split_wxcc_windows(from_ms: int, to_ms: int, max_window_ms: int = MAX_WXCC_WINDOW_MS):
    """Split a span into Search API-safe windows of at most 24 hours."""
    current = from_ms
    while current < to_ms:
        end = min(current + max_window_ms, to_ms)
        yield current, end
        current = end


def iter_days(start: date, end: date):
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)
