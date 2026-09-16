from datetime import datetime, timezone, timedelta
from ..database import SessionLocal
from ..config import settings
from ..services.collector import collect_window

def main():
    now = datetime.now(timezone.utc)

    # Call/task history keeps the short rolling overlap window.
    call_end = now
    call_start = now - timedelta(minutes=settings.collector_lookback_minutes)

    # Agent sessions are keyed by session start time, so use a wider rolling
    # window to keep agents who signed in earlier in the day visible to the
    # live staffing collector.
    agent_end = now
    agent_start = now - timedelta(hours=settings.collector_agent_lookback_hours)

    from_ms = int(call_start.timestamp() * 1000)
    to_ms = int(call_end.timestamp() * 1000)
    agent_from_ms = int(agent_start.timestamp() * 1000)
    agent_to_ms = int(agent_end.timestamp() * 1000)

    db = SessionLocal()
    try:
        result = collect_window(
            db,
            from_ms,
            to_ms,
            agent_from_ms=agent_from_ms,
            agent_to_ms=agent_to_ms,
        )
        print(result)
    finally:
        db.close()

if __name__ == "__main__":
    main()
