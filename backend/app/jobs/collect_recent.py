from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

from ..database import SessionLocal
from ..config import settings
from ..services.collector import collect_window
from .utils import local_day_window_ms, split_wxcc_windows

TZ = ZoneInfo("America/Detroit")


def main():
    now = datetime.now(timezone.utc)
    now_ms = int(now.timestamp() * 1000)

    # Re-pull the current local day on every run. WxCC search records can be
    # finalized or updated after the interaction first appears, so a very
    # short rolling window can leave today's dashboard incomplete until the
    # nightly reconciliation. Upserts make this safe to repeat.
    today_local = datetime.now(TZ).date()
    day_start_ms, _ = local_day_window_ms(today_local, TZ)

    # Agent sessions need their own rolling window because the Search API
    # matches sessions by start time. Keep the existing 24-hour default.
    agent_start = now - timedelta(hours=settings.collector_agent_lookback_hours)
    agent_from_ms = int(agent_start.timestamp() * 1000)
    agent_to_ms = now_ms

    db = SessionLocal()
    try:
        totals = {
            "tasks": 0,
            "task_details": 0,
            "task_legs": 0,
            "agent_sessions": 0,
        }
        errors = []
        windows = list(split_wxcc_windows(day_start_ms, now_ms))

        for index, (from_ms, to_ms) in enumerate(windows):
            # Agent data only needs to be fetched once per cron execution.
            result = collect_window(
                db,
                from_ms,
                to_ms,
                include_agent_sessions=(index == len(windows) - 1),
                agent_from_ms=agent_from_ms if index == len(windows) - 1 else None,
                agent_to_ms=agent_to_ms if index == len(windows) - 1 else None,
            )
            totals["tasks"] += result.get("tasks", 0)
            totals["task_details"] += result.get("task_details", 0)
            totals["task_legs"] += result.get("task_legs", 0)
            totals["agent_sessions"] += result.get("agent_sessions", 0)
            if result.get("agent_session_error"):
                errors.append(result["agent_session_error"])

        print({
            "success": True,
            "mode": "current_day_reconcile",
            "from": day_start_ms,
            "to": now_ms,
            "windows": len(windows),
            "tasks": totals["tasks"],
            "task_details": totals["task_details"],
            "task_legs": totals["task_legs"],
            "agent_sessions": totals["agent_sessions"],
            "agent_sessions_requested": True,
            "agent_from": agent_from_ms,
            "agent_to": agent_to_ms,
            "agent_session_error": errors[0] if errors else None,
        })
    finally:
        db.close()


if __name__ == "__main__":
    main()
