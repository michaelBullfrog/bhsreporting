from __future__ import annotations

from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo

from ..database import SessionLocal
from ..models import Interaction, InteractionLeg, InteractionAgent
from ..webex.client import WxccClient
from .utils import local_day_window_ms

TZ = ZoneInfo("America/Detroit")


def fmt_ms(value):
    if not value:
        return "—"
    return datetime.fromtimestamp(int(value) / 1000, tz=TZ).strftime("%Y-%m-%d %I:%M:%S %p %Z")


def norm(value):
    return str(value or "").strip()


def count_by(rows, getter):
    return Counter(getter(row) or "(blank)" for row in rows)


def print_counter(title, counter):
    print(f"\n{title}")
    for key, count in sorted(counter.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"  {key}: {count}")


def main():
    today = datetime.now(TZ).date()
    from_ms, day_to_ms = local_day_window_ms(today)
    now_ms = int(datetime.now(TZ).timestamp() * 1000)
    to_ms = min(day_to_ms, now_ms)

    print("=== DIRECT WxCC TODAY SOURCE AUDIT ===")
    print(f"Date:   {today.isoformat()} ({TZ.key})")
    print(f"From:   {fmt_ms(from_ms)}")
    print(f"To:     {fmt_ms(to_ms)}")
    print("This calls WxCC directly first, then compares the result with PostgreSQL.")

    client = WxccClient()

    print("\nPulling task() directly from WxCC...")
    tasks = client.get_tasks(from_ms, to_ms)
    print("Pulling taskDetails() directly from WxCC...")
    details = client.get_task_details(from_ms, to_ms)
    print("Pulling taskLegDetails() directly from WxCC...")
    legs = client.get_task_legs(from_ms, to_ms)

    task_ids = {norm(r.get("id")) for r in tasks if norm(r.get("id"))}
    detail_ids = {norm(r.get("id")) for r in details if norm(r.get("id"))}
    leg_task_ids = {norm(r.get("taskId")) for r in legs if norm(r.get("taskId"))}
    leg_ids = {norm(r.get("id")) for r in legs if norm(r.get("id"))}

    print("\n--- DIRECT WxCC COUNTS ---")
    print(f"task() rows:                    {len(tasks)}")
    print(f"task() unique task IDs:         {len(task_ids)}")
    print(f"taskDetails() rows:             {len(details)}")
    print(f"taskDetails() unique task IDs:  {len(detail_ids)}")
    print(f"taskLegDetails() rows:          {len(legs)}")
    print(f"taskLegDetails() unique leg IDs:{len(leg_ids)}")
    print(f"Legs reference unique task IDs: {len(leg_task_ids)}")

    print_counter(
        "--- DIRECT TASK DIRECTIONS ---",
        count_by(tasks, lambda r: norm(r.get("direction")).lower()),
    )
    print_counter(
        "--- DIRECT TASK FINAL QUEUES ---",
        count_by(tasks, lambda r: norm((r.get("lastQueue") or {}).get("name"))),
    )
    print_counter(
        "--- DIRECT LEG QUEUES ---",
        count_by(legs, lambda r: norm((r.get("queue") or {}).get("name"))),
    )
    print_counter(
        "--- DIRECT LEG OWNERS ---",
        count_by(legs, lambda r: norm((r.get("owner") or {}).get("name"))),
    )

    inbound_tasks = [r for r in tasks if norm(r.get("direction")).lower() == "inbound"]
    outdial_tasks = [r for r in tasks if norm(r.get("direction")).lower() == "outdial"]
    answered_inbound = [r for r in inbound_tasks if int(r.get("connectedCount") or 0) > 0]
    raw_abandoned = [r for r in inbound_tasks if norm(r.get("terminationType")).lower() == "abandoned"]

    print("\n--- DIRECT TASK BUSINESS COUNTS ---")
    print(f"Inbound tasks:                  {len(inbound_tasks)}")
    print(f"Outbound tasks:                 {len(outdial_tasks)}")
    print(f"Answered inbound:               {len(answered_inbound)}")
    print(f"Raw abandoned inbound:          {len(raw_abandoned)}")

    missing_task_from_legs = sorted(leg_task_ids - task_ids)
    tasks_without_details = sorted(task_ids - detail_ids)
    details_without_tasks = sorted(detail_ids - task_ids)

    print("\n--- DIRECT SOURCE CONSISTENCY ---")
    print(f"Leg task IDs missing from task():       {len(missing_task_from_legs)}")
    print(f"task() IDs missing from taskDetails():  {len(tasks_without_details)}")
    print(f"taskDetails() IDs missing from task():  {len(details_without_tasks)}")
    if missing_task_from_legs:
        print("Sample leg task IDs missing from task():")
        for value in missing_task_from_legs[:10]:
            print(f"  {value}")

    db = SessionLocal()
    try:
        db_tasks = (
            db.query(Interaction)
            .filter(Interaction.created_time >= from_ms, Interaction.created_time < to_ms)
            .all()
        )
        db_legs = (
            db.query(InteractionLeg)
            .filter(InteractionLeg.created_time >= from_ms, InteractionLeg.created_time < to_ms)
            .all()
        )
        db_details = (
            db.query(InteractionAgent)
            .join(Interaction, Interaction.task_id == InteractionAgent.task_id)
            .filter(Interaction.created_time >= from_ms, Interaction.created_time < to_ms)
            .all()
        )

        db_task_ids = {norm(r.task_id) for r in db_tasks if norm(r.task_id)}
        db_leg_ids = {norm(r.leg_id) for r in db_legs if norm(r.leg_id)}

        print("\n--- POSTGRESQL COUNTS FOR SAME WINDOW ---")
        print(f"Interactions:                   {len(db_tasks)}")
        print(f"InteractionAgent rows:          {len(db_details)}")
        print(f"Interaction legs:               {len(db_legs)}")

        api_not_db_tasks = sorted(task_ids - db_task_ids)
        db_not_api_tasks = sorted(db_task_ids - task_ids)
        api_not_db_legs = sorted(leg_ids - db_leg_ids)

        print("\n--- API VS DATABASE ---")
        print(f"Direct task IDs not in DB:      {len(api_not_db_tasks)}")
        print(f"DB task IDs not in direct API:  {len(db_not_api_tasks)}")
        print(f"Direct leg IDs not in DB:       {len(api_not_db_legs)}")

        if api_not_db_tasks:
            print("Sample direct task IDs missing from DB:")
            for value in api_not_db_tasks[:10]:
                print(f"  {value}")
        if api_not_db_legs:
            print("Sample direct leg IDs missing from DB:")
            for value in api_not_db_legs[:10]:
                print(f"  {value}")

        print("\n--- INTERPRETATION GUIDE ---")
        print("If direct WxCC counts are much larger than DB counts, ingestion/upsert is losing records.")
        print("If direct task() is small but taskLegDetails() is large, task-level collection is incomplete for this reporting use case.")
        print("If all three direct WxCC datasets are small compared with the Agent Detail Report, we need to inspect Search API pagination/query semantics next.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
