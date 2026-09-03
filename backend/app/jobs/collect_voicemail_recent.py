from datetime import datetime, timezone, timedelta
from ..database import SessionLocal
from ..config import settings
from ..services.voicemail_collector import collect_service_voicemail_window

def main():
    # CDR feed rejects end times newer than five minutes. Keep a six-minute
    # safety margin and collect a rolling overlap ending at the safe point.
    safe_end=datetime.now(timezone.utc)-timedelta(minutes=6)
    start=safe_end-timedelta(minutes=settings.webex_calling_collector_lookback_minutes)
    db=SessionLocal()
    try:
        print(collect_service_voicemail_window(db,int(start.timestamp()*1000),int(safe_end.timestamp()*1000)),flush=True)
    finally:
        db.close()
if __name__=="__main__": main()
