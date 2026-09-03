import argparse
import time
from datetime import datetime, timezone, timedelta
from ..database import SessionLocal
from ..services.voicemail_collector import collect_service_voicemail_window

def parse_day(v): return datetime.strptime(v,"%Y-%m-%d").replace(tzinfo=timezone.utc)
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--start",required=True)
    ap.add_argument("--end",required=True)
    ap.add_argument("--delay",type=float,default=10.0,help="Seconds to wait between 12-hour CDR requests (default: 10)")
    args=ap.parse_args()

    cur=parse_day(args.start)
    end=parse_day(args.end)+timedelta(days=1)
    db=SessionLocal()
    try:
        while cur<end:
            nxt=min(cur+timedelta(hours=12),end)
            print(collect_service_voicemail_window(db,int(cur.timestamp()*1000),int(nxt.timestamp()*1000)), flush=True)
            cur=nxt
            if cur<end and args.delay>0:
                time.sleep(args.delay)
    finally:
        db.close()

if __name__=="__main__": main()
