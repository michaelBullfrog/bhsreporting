from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

from ..database import SessionLocal
from ..models import Interaction, InteractionLeg
from .utils import local_day_window_ms

TZ = ZoneInfo("America/Detroit")


def fmt_ms(value):
    if not value:
        return "—"
    return datetime.fromtimestamp(int(value) / 1000, tz=TZ).strftime("%I:%M:%S %p")


def norm(value):
    return str(value or "").strip()


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
            )
            .all()
        )

        blank = [
            r for r in rows
            if not (r.queue_name and str(r.queue_name).strip())
        ]

        task_ids = [r.task_id for r in blank if r.task_id]
        leg_rows = (
            db.query(InteractionLeg)
            .filter(InteractionLeg.task_id.in_(task_ids))
            .order_by(InteractionLeg.created_time.asc())
            .all()
            if task_ids else []
        )

        legs_by_task = defaultdict(list)
        for leg in leg_rows:
            legs_by_task[leg.task_id].append(leg)

        print("=== BHS BLANK-QUEUE INBOUND AUDIT ===")
        print(f"Date: {today.isoformat()} ({TZ.key})")
        print(f"Inbound interactions:            {len(rows)}")
        print(f"Inbound with blank final queue:  {len(blank)}")

        term_counts = Counter(norm(r.termination_type) or "(blank)" for r in blank)
        connected_counts = Counter("answered" if int(r.connected_count or 0) > 0 else "not_answered" for r in blank)
        destination_counts = Counter(norm(r.destination) or "(blank)" for r in blank)
        origin_counts = Counter(norm(r.origin) or "(blank)" for r in blank)
        callback_counts = Counter(norm(r.callback_status) or "(none)" for r in blank)

        print("\n--- TERMINATION TYPES ---")
        for k, v in term_counts.most_common():
            print(f"  {k}: {v}")

        print("\n--- CONNECTED STATUS ---")
        for k, v in connected_counts.most_common():
            print(f"  {k}: {v}")

        print("\n--- TASK DESTINATIONS ---")
        for k, v in destination_counts.most_common(20):
            print(f"  {k}: {v}")

        print("\n--- TASK ORIGINS ---")
        for k, v in origin_counts.most_common(20):
            print(f"  {k}: {v}")

        print("\n--- CALLBACK STATUS ---")
        for k, v in callback_counts.most_common():
            print(f"  {k}: {v}")

        any_leg_queue = 0
        no_leg_queue = 0
        leg_queue_counts = Counter()
        leg_destination_counts = Counter()
        owner_counts = Counter()

        for r in blank:
            legs = legs_by_task.get(r.task_id, [])
            queues = [norm(l.queue_name) for l in legs if norm(l.queue_name)]
            if queues:
                any_leg_queue += 1
                for q in queues:
                    leg_queue_counts[q] += 1
            else:
                no_leg_queue += 1

            for l in legs:
                if norm(l.destination):
                    leg_destination_counts[norm(l.destination)] += 1
                if norm(l.agent_name):
                    owner_counts[norm(l.agent_name)] += 1

        print("\n--- LEG-LEVEL QUEUE EVIDENCE ---")
        print(f"Blank-final-queue tasks with ANY queued leg: {any_leg_queue}")
        print(f"Blank-final-queue tasks with NO queued leg:  {no_leg_queue}")
        for k, v in leg_queue_counts.most_common():
            print(f"  queue={k}: {v} leg(s)")

        print("\n--- LEG DESTINATIONS ---")
        for k, v in leg_destination_counts.most_common(20):
            print(f"  {k}: {v}")

        print("\n--- LEG OWNERS ---")
        for k, v in owner_counts.most_common(20):
            print(f"  {k}: {v}")

        print("\n--- PER-INTERACTION DETAIL ---")
        for r in sorted(blank, key=lambda x: x.created_time or 0):
            legs = legs_by_task.get(r.task_id, [])
            leg_desc = []
            for l in legs:
                leg_desc.append(
                    "["
                    f"{fmt_ms(l.created_time)} "
                    f"queue={norm(l.queue_name) or '—'} "
                    f"dest={norm(l.destination) or '—'} "
                    f"owner={norm(l.agent_name) or '—'} "
                    f"connected_ms={int(l.connected_duration or 0)}"
                    "]"
                )

            print(
                f"{fmt_ms(r.created_time)} | "
                f"task={r.task_id} | "
                f"origin={norm(r.origin) or '—'} | "
                f"dest={norm(r.destination) or '—'} | "
                f"term={norm(r.termination_type) or '—'} | "
                f"connected_count={int(r.connected_count or 0)} | "
                f"callback={norm(r.callback_status) or '—'}"
            )
            if leg_desc:
                for desc in leg_desc:
                    print(f"    {desc}")
            else:
                print("    [no stored legs]")

        print("\n--- INTERPRETATION ---")
        print("If many blank-final-queue tasks still have a queued leg, lastQueue is not reliable enough for queue attribution.")
        print("If most have no queued legs and are abandoned/normal before connection, they are likely pre-queue/IVR outcomes and should remain separate from queue demand.")
        print("If many are connected with no queue evidence, we should inspect routing/transfer behavior before changing Call Demand logic.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
