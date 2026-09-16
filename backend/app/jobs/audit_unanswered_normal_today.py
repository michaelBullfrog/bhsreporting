from __future__ import annotations

import json
from datetime import datetime
from zoneinfo import ZoneInfo

from ..database import SessionLocal
from ..models import Interaction, InteractionLeg, InteractionAgent, RawWxccRecord
from .utils import local_day_window_ms

TZ = ZoneInfo("America/Detroit")


def fmt_ms(value):
    if not value:
        return "—"
    return datetime.fromtimestamp(int(value) / 1000, tz=TZ).strftime("%Y-%m-%d %I:%M:%S %p %Z")


def pretty(obj):
    return json.dumps(obj, indent=2, sort_keys=True, default=str)


def main():
    today = datetime.now(TZ).date()
    from_ms, day_to_ms = local_day_window_ms(today)
    now_ms = int(datetime.now(TZ).timestamp() * 1000)
    to_ms = min(day_to_ms, now_ms)

    db = SessionLocal()
    try:
        rows = (
            db.query(Interaction)
            .filter(
                Interaction.created_time >= from_ms,
                Interaction.created_time < to_ms,
                Interaction.direction == "inbound",
                Interaction.queue_name.isnot(None),
                Interaction.queue_name != "",
                Interaction.connected_count == 0,
                Interaction.termination_type == "normal",
            )
            .order_by(Interaction.created_time.asc())
            .all()
        )

        print("=== BHS NORMAL + UNANSWERED QUEUED DEEP AUDIT ===")
        print(f"Date: {today.isoformat()} ({TZ.key})")
        print(f"Matches: {len(rows)}")

        if not rows:
            print("No queued inbound calls matched connected_count=0 and termination_type=normal.")
            return

        for row in rows:
            print("\n" + "=" * 100)
            print(f"TASK {row.task_id}")
            print("=" * 100)
            print(f"Created:           {fmt_ms(row.created_time)}")
            print(f"Ended:             {fmt_ms(row.ended_time)}")
            print(f"Status:            {row.status or '—'}")
            print(f"Termination type:  {row.termination_type or '—'}")
            print(f"Origin:            {row.origin or '—'}")
            print(f"Destination:       {row.destination or '—'}")
            print(f"Queue:             {row.queue_name or '—'}")
            print(f"Queue duration ms: {int(row.queue_duration or 0)}")
            print(f"Connected count:   {int(row.connected_count or 0)}")
            print(f"Connected ms:      {int(row.connected_duration or 0)}")
            print(f"Total duration ms: {int(row.total_duration or 0)}")
            print(f"Hold count:        {int(row.hold_count or 0)}")
            print(f"Hold ms:           {int(row.hold_duration or 0)}")
            print(f"Wrapup code:       {row.wrapup_code or '—'}")

            agent = db.get(InteractionAgent, row.task_id)
            print("\n--- TASKDETAILS AGENT ---")
            if agent:
                print(f"Agent name: {agent.agent_name or '—'}")
                print(f"Agent id:   {agent.agent_id or '—'}")
                print(f"Sign-in id: {agent.sign_in_id or '—'}")
                print(f"Session id: {agent.session_id or '—'}")
                print("Raw taskDetails payload:")
                print(pretty(agent.raw_payload))
            else:
                print("No InteractionAgent row.")

            legs = (
                db.query(InteractionLeg)
                .filter(InteractionLeg.task_id == row.task_id)
                .order_by(InteractionLeg.created_time.asc())
                .all()
            )
            print("\n--- LEGS ---")
            print(f"Leg count: {len(legs)}")
            for i, leg in enumerate(legs, start=1):
                print(f"\nLeg {i}: {leg.leg_id}")
                print(f"  Created:           {fmt_ms(leg.created_time)}")
                print(f"  Ended:             {fmt_ms(leg.ended_time)}")
                print(f"  Status:            {leg.status or '—'}")
                print(f"  Contact state:     {leg.contact_state or '—'}")
                print(f"  Origin:            {leg.origin or '—'}")
                print(f"  Destination:       {leg.destination or '—'}")
                print(f"  Queue:             {leg.queue_name or '—'}")
                print(f"  Queue duration ms: {int(leg.queue_duration or 0)}")
                print(f"  Agent:             {leg.agent_name or '—'}")
                print(f"  Ringing ms:        {int(leg.ringing_duration or 0)}")
                print(f"  Connected ms:      {int(leg.connected_duration or 0)}")
                print(f"  Hold ms:           {int(leg.hold_duration or 0)}")
                print(f"  Wrapup ms:         {int(leg.wrapup_duration or 0)}")
                print("  Raw leg payload:")
                print(pretty(leg.raw_payload))

            print("\n--- RAW TASK PAYLOAD ---")
            print(pretty(row.raw_payload))

            raw_rows = (
                db.query(RawWxccRecord)
                .filter(RawWxccRecord.webex_id == row.task_id)
                .order_by(RawWxccRecord.collected_at.desc())
                .all()
            )
            print("\n--- RAW WXCC RECORD HISTORY FOR TASK ID ---")
            print(f"Raw rows: {len(raw_rows)}")
            for raw in raw_rows[:10]:
                print(
                    f"record_type={raw.record_type} collected_at={raw.collected_at} "
                    f"source_from={raw.source_from} source_to={raw.source_to}"
                )
                print(pretty(raw.payload))

        print("\n--- WHAT TO LOOK FOR ---")
        print("status/contactState values such as queued, parked, terminated, transferred, or completed")
        print("whether endedTime exists and whether the task/leg had any owner")
        print("whether raw payloads contain a stronger outcome signal than terminationType=normal")
    finally:
        db.close()


if __name__ == "__main__":
    main()
