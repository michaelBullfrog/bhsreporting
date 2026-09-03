import argparse
import time
from datetime import datetime, timezone, timedelta
from ..database import SessionLocal
from ..services.voicemail_collector import collect_service_voicemail_window


def parse_day(v):
    return datetime.strptime(v, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--delay", type=float, default=10.0,
                    help="Seconds to wait between 12-hour CDR requests (default: 10)")
    args = ap.parse_args()

    cur = parse_day(args.start)
    requested_end = parse_day(args.end) + timedelta(days=1)

    # cdr_feed rejects a request whose endTime is newer than 5 minutes ago.
    # Keep a one-minute safety margin so clock skew / request latency cannot
    # turn an otherwise valid historical backfill into HTTP 400.
    api_safe_end = datetime.now(timezone.utc) - timedelta(minutes=6)
    end = min(requested_end, api_safe_end)

    if end <= cur:
        print({
            "success": True,
            "message": "Nothing eligible to backfill yet; Webex CDR endTime must be older than 5 minutes.",
            "requested_start": args.start,
            "requested_end": args.end,
            "safe_end_utc": api_safe_end.isoformat(),
        }, flush=True)
        return

    if requested_end > api_safe_end:
        print({
            "notice": "Backfill end was clamped to the newest Webex CDR-safe time",
            "requested_end_utc": requested_end.isoformat(),
            "effective_end_utc": end.isoformat(),
        }, flush=True)

    db = SessionLocal()
    try:
        while cur < end:
            nxt = min(cur + timedelta(hours=12), end)
            print(collect_service_voicemail_window(
                db,
                int(cur.timestamp() * 1000),
                int(nxt.timestamp() * 1000),
            ), flush=True)
            cur = nxt
            if cur < end and args.delay > 0:
                time.sleep(args.delay)
    finally:
        db.close()


if __name__ == "__main__":
    main()
