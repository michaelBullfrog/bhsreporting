from datetime import datetime, timezone, timedelta
from ..database import SessionLocal
from ..config import settings
from ..services.voicemail_collector import collect_service_voicemail_window

def main():
    now=datetime.now(timezone.utc); start=now-timedelta(minutes=settings.webex_calling_collector_lookback_minutes)
    db=SessionLocal()
    try: print(collect_service_voicemail_window(db,int(start.timestamp()*1000),int(now.timestamp()*1000)))
    finally: db.close()
if __name__=="__main__": main()
