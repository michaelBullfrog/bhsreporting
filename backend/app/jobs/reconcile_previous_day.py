from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from ..database import SessionLocal
from ..services.collector import collect_window
from .utils import local_day_window_ms

TZ = ZoneInfo("America/Detroit")


def main():
    today_local = datetime.now(TZ).date()
    day = today_local - timedelta(days=1)
    from_ms, to_ms = local_day_window_ms(day)

    windows = []
    if to_ms - from_ms <= 86_400_000:
        windows.append((from_ms, to_ms))
    else:
        midpoint = from_ms + 86_400_000
        windows.append((from_ms, midpoint))
        windows.append((midpoint, to_ms))

    db = SessionLocal()
    try:
        for w_from, w_to in windows:
            print(collect_window(db, w_from, w_to))
    finally:
        db.close()


if __name__ == "__main__":
    main()
