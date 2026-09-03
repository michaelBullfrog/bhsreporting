from fastapi import APIRouter, Depends, Query
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from ..database import get_db
from ..services.collector import collect_window
from ..models import CollectorRun

router = APIRouter(prefix="/api/collector", tags=["collector"])

@router.post("/run")
def run_collector(
    from_ms: int = Query(...),
    to_ms: int = Query(...),
    db: Session = Depends(get_db),
):
    return collect_window(db, from_ms, to_ms)

@router.post("/refresh")
def refresh_recent_data(
    lookback_minutes: int = Query(120, ge=30, le=1440),
    min_interval_minutes: int = Query(5, ge=0, le=60),
    db: Session = Depends(get_db),
):
    """
    Pull a short recent overlap window from WxCC before dashboard reload.

    A cooldown prevents page-to-page navigation from repeatedly hitting WxCC.
    """
    now = datetime.now(timezone.utc)

    latest_success = (
        db.query(CollectorRun)
        .filter(CollectorRun.success.is_(True))
        .order_by(CollectorRun.finished_at.desc())
        .first()
    )

    if latest_success and latest_success.finished_at:
        finished = latest_success.finished_at
        if finished.tzinfo is None:
            finished = finished.replace(tzinfo=timezone.utc)
        age_seconds = max(0, (now - finished).total_seconds())

        if age_seconds < min_interval_minutes * 60:
            return {
                "success": True,
                "skipped": True,
                "reason": "recent_successful_collection",
                "last_successful_run_ms": int(finished.timestamp() * 1000),
                "age_minutes": round(age_seconds / 60, 1),
            }

    start = now - timedelta(minutes=lookback_minutes)
    from_ms = int(start.timestamp() * 1000)
    to_ms = int(now.timestamp() * 1000)

    result = collect_window(
        db,
        from_ms,
        to_ms,
        include_agent_sessions=True,
    )
    result["skipped"] = False
    result["lookback_minutes"] = lookback_minutes
    return result

