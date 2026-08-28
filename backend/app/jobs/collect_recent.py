from datetime import datetime, timezone, timedelta
from ..database import SessionLocal
from ..config import settings
from ..services.collector import collect_window

def main():
    now = datetime.now(timezone.utc)
    end = now
    start = now - timedelta(minutes=settings.collector_lookback_minutes)

    from_ms = int(start.timestamp() * 1000)
    to_ms = int(end.timestamp() * 1000)

    db = SessionLocal()
    try:
        result = collect_window(db, from_ms, to_ms)
        print(result)
    finally:
        db.close()

if __name__ == "__main__":
    main()
