from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

from backend.app.database import SessionLocal
from backend.app.models import Interaction

TZ = ZoneInfo("America/Detroit")


def to_ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def fmt_ms(value: int | None) -> str:
    if not value:
        return ""
    return datetime.fromtimestamp(value / 1000, TZ).strftime("%Y-%m-%d %I:%M:%S %p")


def is_inbound_queued(r: Interaction) -> bool:
    return bool(
        r.queue_name
        and (r.direction or "").strip().lower() != "outdial"
    )


def is_answered(r: Interaction) -> bool:
    return (r.connected_count or 0) > 0


def is_raw_abandoned(r: Interaction) -> bool:
    return (
        not is_answered(r)
        and (r.termination_type or "").strip().lower() == "abandoned"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit queued unanswered interactions to reconcile dashboard abandoned counts with Analyzer."
    )
    parser.add_argument("--start", required=True, help="Start date YYYY-MM-DD (America/Detroit)")
    parser.add_argument("--end", required=True, help="End date YYYY-MM-DD inclusive (America/Detroit)")
    parser.add_argument("--queue", default="", help="Optional exact queue name")
    args = parser.parse_args()

    start_local = datetime.strptime(args.start, "%Y-%m-%d").replace(tzinfo=TZ)
    end_local_exclusive = (
        datetime.strptime(args.end, "%Y-%m-%d").replace(tzinfo=TZ)
        + timedelta(days=1)
    )

    start_ms = to_ms(start_local)
    end_ms = to_ms(end_local_exclusive)

    with SessionLocal() as db:
        # Created-time population: matches the dashboard's current date-window behavior.
        created_stmt = (
            select(Interaction)
            .where(Interaction.created_time >= start_ms)
            .where(Interaction.created_time < end_ms)
            .where(Interaction.queue_name.is_not(None))
            .where(Interaction.queue_name != "")
            .where((Interaction.direction.is_(None)) | (Interaction.direction != "outdial"))
            .order_by(Interaction.created_time.asc())
        )
        if args.queue:
            created_stmt = created_stmt.where(Interaction.queue_name == args.queue)
        created_rows = list(db.scalars(created_stmt).all())

        # Ended-time population: Analyzer historical reports commonly attribute completed/
        # abandoned contacts to the report interval in which they ended. Compare both grains.
        ended_stmt = (
            select(Interaction)
            .where(Interaction.ended_time >= start_ms)
            .where(Interaction.ended_time < end_ms)
            .where(Interaction.queue_name.is_not(None))
            .where(Interaction.queue_name != "")
            .where((Interaction.direction.is_(None)) | (Interaction.direction != "outdial"))
            .order_by(Interaction.ended_time.asc())
        )
        if args.queue:
            ended_stmt = ended_stmt.where(Interaction.queue_name == args.queue)
        ended_rows = list(db.scalars(ended_stmt).all())

    answered = [r for r in created_rows if is_answered(r)]
    unanswered = [r for r in created_rows if not is_answered(r)]
    raw_abandoned = [r for r in created_rows if is_raw_abandoned(r)]
    other_outcomes = [
        r for r in unanswered
        if (r.termination_type or "").strip().lower() != "abandoned"
    ]

    ended_raw_abandoned = [r for r in ended_rows if is_raw_abandoned(r)]

    created_ids = {r.task_id for r in raw_abandoned}
    ended_ids = {r.task_id for r in ended_raw_abandoned}
    ended_only = [r for r in ended_raw_abandoned if r.task_id not in created_ids]
    created_only = [r for r in raw_abandoned if r.task_id not in ended_ids]

    print()
    print("=== BHS ABANDONED RECONCILIATION AUDIT ===")
    print(f"Period (America/Detroit): {args.start} through {args.end} inclusive")
    if args.queue:
        print(f"Queue: {args.queue}")
    else:
        print("Queue: ALL queued interactions")
    print()
    print("--- CURRENT DASHBOARD GRAIN: CREATED TIME ---")
    print(f"Queued interactions:      {len(created_rows)}")
    print(f"Answered:                 {len(answered)}")
    print(f"Raw abandoned:            {len(raw_abandoned)}")
    print(f"Other unanswered outcomes:{len(other_outcomes):>6}")
    print(f"Reported abandoned:       {len(raw_abandoned) + len(other_outcomes)}")
    print(f"Reconciles:               {len(created_rows) == len(answered) + len(unanswered)}")

    print()
    print("Termination types for ALL unanswered queued interactions:")
    counts = Counter((r.termination_type or "<blank>") for r in unanswered)
    for name, count in counts.most_common():
        print(f"  {name}: {count}")

    print()
    print("--- ANALYZER COMPARISON GRAIN: ENDED TIME ---")
    print(f"Queued interactions ended in period: {len(ended_rows)}")
    print(f"Raw abandoned ended in period:       {len(ended_raw_abandoned)}")
    print(f"Difference vs created-time abandon:  {len(ended_raw_abandoned) - len(raw_abandoned):+d}")

    print()
    print("=== ABANDONED IN ENDED-TIME WINDOW BUT NOT CREATED-TIME WINDOW ===")
    if not ended_only:
        print("None")
    else:
        for idx, r in enumerate(ended_only, 1):
            wait_s = round((r.queue_duration or 0) / 1000, 1)
            print(
                f"{idx:>2}. created={fmt_ms(r.created_time)} | ended={fmt_ms(r.ended_time)} | "
                f"queue={r.queue_name!r} | origin={r.origin!r} | "
                f"termination={r.termination_type!r} | queueWait={wait_s}s | taskId={r.task_id}"
            )

    print()
    print("=== ABANDONED IN CREATED-TIME WINDOW BUT NOT ENDED-TIME WINDOW ===")
    if not created_only:
        print("None")
    else:
        for idx, r in enumerate(created_only, 1):
            wait_s = round((r.queue_duration or 0) / 1000, 1)
            print(
                f"{idx:>2}. created={fmt_ms(r.created_time)} | ended={fmt_ms(r.ended_time)} | "
                f"queue={r.queue_name!r} | origin={r.origin!r} | "
                f"termination={r.termination_type!r} | queueWait={wait_s}s | taskId={r.task_id}"
            )

    print()
    print("=== OTHER UNANSWERED QUEUED OUTCOMES ===")
    if not other_outcomes:
        print("None")
    else:
        for idx, r in enumerate(other_outcomes, 1):
            wait_s = round((r.queue_duration or 0) / 1000, 1)
            print(
                f"{idx:>2}. {fmt_ms(r.created_time)} | "
                f"queue={r.queue_name!r} | "
                f"origin={r.origin!r} | "
                f"termination={r.termination_type!r} | "
                f"status={r.status!r} | "
                f"connectedCount={r.connected_count or 0} | "
                f"queueWait={wait_s}s | "
                f"taskId={r.task_id}"
            )

    print()
    print("=== RAW ABANDONED (CREATED-TIME WINDOW) ===")
    for idx, r in enumerate(raw_abandoned, 1):
        wait_s = round((r.queue_duration or 0) / 1000, 1)
        print(
            f"{idx:>2}. created={fmt_ms(r.created_time)} | ended={fmt_ms(r.ended_time)} | "
            f"queue={r.queue_name!r} | origin={r.origin!r} | "
            f"termination={r.termination_type!r} | status={r.status!r} | "
            f"queueWait={wait_s}s | taskId={r.task_id}"
        )


if __name__ == "__main__":
    main()
