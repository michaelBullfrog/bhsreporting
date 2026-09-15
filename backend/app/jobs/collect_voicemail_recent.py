from datetime import datetime, timezone, timedelta

from ..config import settings
from ..database import Base, SessionLocal, engine
from ..models import CallingCollectorRun
from ..services.voicemail_collector import collect_service_voicemail_window


def main():
    # Ensure the run-tracking table exists even if this cron deploys before
    # the web service has restarted and executed Base.metadata.create_all().
    Base.metadata.create_all(bind=engine)

    # CDR feed rejects end times newer than five minutes. Keep a six-minute
    # safety margin and collect a rolling overlap ending at the safe point.
    safe_end = datetime.now(timezone.utc) - timedelta(minutes=6)
    start = safe_end - timedelta(minutes=settings.webex_calling_collector_lookback_minutes)
    from_ms = int(start.timestamp() * 1000)
    to_ms = int(safe_end.timestamp() * 1000)

    db = SessionLocal()
    run = CallingCollectorRun(
        started_at=datetime.now(timezone.utc),
        from_ms=from_ms,
        to_ms=to_ms,
        success=False,
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    try:
        result = collect_service_voicemail_window(db, from_ms, to_ms)
        run.finished_at = datetime.now(timezone.utc)
        run.success = True
        run.cdr_records = int(result.get("cdr_records") or 0)
        run.voicemail_events = int(result.get("unique_voicemail_events") or 0)
        run.outbound_calls = int(result.get("unique_outbound_cdrs") or 0)
        run.error = None
        db.commit()
        print(result, flush=True)
    except Exception as exc:
        db.rollback()
        run = db.get(CallingCollectorRun, run.id)
        if run is not None:
            run.finished_at = datetime.now(timezone.utc)
            run.success = False
            run.error = str(exc)[:4000]
            db.commit()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
