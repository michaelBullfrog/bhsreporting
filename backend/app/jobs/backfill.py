from __future__ import annotations

import argparse
from datetime import date, datetime

from ..database import SessionLocal
from ..services.collector import collect_window
from .utils import iter_days, local_day_window_ms


def parse_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"Invalid date '{value}'. Use YYYY-MM-DD."
        ) from exc


def main():
    parser = argparse.ArgumentParser(
        description="Backfill WxCC analytics one local calendar day at a time."
    )
    parser.add_argument("--start", required=True, type=parse_date)
    parser.add_argument("--end", required=True, type=parse_date)
    args = parser.parse_args()

    if args.end < args.start:
        raise SystemExit("--end must be on or after --start")

    db = SessionLocal()
    total_tasks = 0
    total_details = 0
    total_legs = 0

    try:
        for day in iter_days(args.start, args.end):
            from_ms, to_ms = local_day_window_ms(day)

            # DST can create 23/25-hour local days. Search API max is 24h, so
            # split a >24h day into two safe windows.
            windows = []
            if to_ms - from_ms <= 86_400_000:
                windows.append((from_ms, to_ms))
            else:
                midpoint = from_ms + 86_400_000
                windows.append((from_ms, midpoint))
                windows.append((midpoint, to_ms))

            print(f"Collecting {day.isoformat()} ({len(windows)} window(s))")

            for w_from, w_to in windows:
                result = collect_window(db, w_from, w_to)
                total_tasks += result["tasks"]
                total_details += result["task_details"]
                total_legs += result["task_legs"]
                print(
                    f"  OK {w_from} -> {w_to}: "
                    f"{result['tasks']} tasks, "
                    f"{result['task_details']} details, "
                    f"{result['task_legs']} legs"
                )

        print(
            "Backfill complete: "
            f"{total_tasks} task pulls, "
            f"{total_details} detail pulls, "
            f"{total_legs} leg pulls"
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
