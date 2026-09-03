import argparse
from datetime import datetime, timezone, timedelta
from ..database import SessionLocal
from ..services.voicemail_collector import collect_service_voicemail_window

def parse_day(v): return datetime.strptime(v,"%Y-%m-%d").replace(tzinfo=timezone.utc)
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--start",required=True); ap.add_argument("--end",required=True); args=ap.parse_args()
    cur=parse_day(args.start); end=parse_day(args.end)+timedelta(days=1); db=SessionLocal()
    try:
        while cur<end:
            nxt=min(cur+timedelta(hours=12),end)
            print(collect_service_voicemail_window(db,int(cur.timestamp()*1000),int(nxt.timestamp()*1000)))
            cur=nxt
    finally: db.close()
if __name__=="__main__": main()
