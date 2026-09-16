from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

from ..database import SessionLocal
from ..models import Interaction, InteractionLeg, InteractionAgent
from .utils import local_day_window_ms

TZ = ZoneInfo("America/Detroit")


def fmt_ms(value):
    if not value:
        return "—"
    return datetime.fromtimestamp(int(value) / 1000, tz=TZ).strftime("%I:%M:%S %p")


def norm(value):
    return str(value or "").strip()


def is_answered(row):
    return int(row.connected_count or 0) > 0


def main():
    today = datetime.now(TZ).date()
    from_ms, day_to_ms = local_day_window_ms(today)
    now_ms = int(datetime.now(TZ).timestamp() * 1000)
    to_ms = min(day_to_ms, now_ms)

    db = SessionLocal()
    try:
        queued = (
            db.query(Interaction)
            .filter(
                Interaction.created_time >= from_ms,
                Interaction.created_time < to_ms,
                Interaction.direction == "inbound",
                Interaction.queue_name.isnot(None),
                Interaction.queue_name != "",
            )
            .order_by(Interaction.created_time.asc())
            .all()
        )

        task_ids = [r.task_id for r in queued if r.task_id]

        legs = (
            db.query(InteractionLeg)
            .filter(InteractionLeg.task_id.in_(task_ids))
            .order_by(InteractionLeg.created_time.asc())
            .all()
            if task_ids else []
        )
        legs_by_task = defaultdict(list)
        for leg in legs:
            legs_by_task[leg.task_id].append(leg)

        agent_rows = (
            db.query(InteractionAgent)
            .filter(InteractionAgent.task_id.in_(task_ids))
            .all()
            if task_ids else []
        )
        agent_by_task = {r.task_id: r for r in agent_rows}

        answered = [r for r in queued if is_answered(r)]
        unanswered = [r for r in queued if not is_answered(r)]
        raw_abandoned = [
            r for r in unanswered
            if norm(r.termination_type).lower() == "abandoned"
        ]
        other_unanswered = [
            r for r in unanswered
            if norm(r.termination_type).lower() != "abandoned"
        ]

        print("=== BHS QUEUED INBOUND AUDIT ===")
        print(f"Date: {today.isoformat()} ({TZ.key})")
        print(f"Queued inbound interactions: {len(queued)}")
        print(f"Answered:                    {len(answered)}")
        print(f"Raw abandoned:               {len(raw_abandoned)}")
        print(f"Other unanswered:            {len(other_unanswered)}")
        print(f"Unanswered total:            {len(unanswered)}")

        print("\n--- BY QUEUE ---")
        by_queue = defaultdict(lambda: {"offered": 0, "answered": 0, "raw_abandoned": 0, "other_unanswered": 0})
        for r in queued:
            q = norm(r.queue_name) or "(blank)"
            bucket = by_queue[q]
            bucket["offered"] += 1
            if is_answered(r):
                bucket["answered"] += 1
            elif norm(r.termination_type).lower() == "abandoned":
                bucket["raw_abandoned"] += 1
            else:
                bucket["other_unanswered"] += 1

        for q in sorted(by_queue):
            b = by_queue[q]
            print(
                f"  {q}: offered={b['offered']} answered={b['answered']} "
                f"raw_abandoned={b['raw_abandoned']} other_unanswered={b['other_unanswered']}"
            )

        print("\n--- TERMINATION TYPES FOR UNANSWERED ---")
        term_counts = Counter(norm(r.termination_type) or "(blank)" for r in unanswered)
        for k, v in term_counts.most_common():
            print(f"  {k}: {v}")

        print("\n--- AGENT ATTRIBUTION ON ANSWERED ---")
        answered_with_agent = 0
        answered_without_agent = 0
        agent_counts = Counter()
        for r in answered:
            a = agent_by_task.get(r.task_id)
            agent_name = norm(getattr(a, "agent_name", None)) if a else ""
            if agent_name:
                answered_with_agent += 1
                agent_counts[agent_name] += 1
            else:
                answered_without_agent += 1
        print(f"Answered with taskDetails agent:    {answered_with_agent}")
        print(f"Answered without taskDetails agent: {answered_without_agent}")
        for k, v in agent_counts.most_common():
            print(f"  {k}: {v}")

        print("\n--- ANSWERED LEG VALIDATION ---")
        answered_with_connected_leg = 0
        answered_without_connected_leg = 0
        connected_leg_agent_counts = Counter()
        multiple_connected_leg_tasks = 0
        for r in answered:
            task_legs = legs_by_task.get(r.task_id, [])
            connected_legs = [l for l in task_legs if int(l.connected_duration or 0) > 0]
            if connected_legs:
                answered_with_connected_leg += 1
                if len(connected_legs) > 1:
                    multiple_connected_leg_tasks += 1
                for l in connected_legs:
                    if norm(l.agent_name):
                        connected_leg_agent_counts[norm(l.agent_name)] += 1
            else:
                answered_without_connected_leg += 1
        print(f"Answered tasks with connected leg:    {answered_with_connected_leg}")
        print(f"Answered tasks without connected leg: {answered_without_connected_leg}")
        print(f"Answered tasks with >1 connected leg: {multiple_connected_leg_tasks}")
        for k, v in connected_leg_agent_counts.most_common():
            print(f"  connected leg owner {k}: {v}")

        print("\n--- PER-INTERACTION DETAIL ---")
        for r in queued:
            outcome = "answered" if is_answered(r) else (
                "raw_abandoned" if norm(r.termination_type).lower() == "abandoned" else "other_unanswered"
            )
            a = agent_by_task.get(r.task_id)
            task_agent = norm(getattr(a, "agent_name", None)) if a else ""
            task_legs = legs_by_task.get(r.task_id, [])
            queued_legs = [l for l in task_legs if norm(l.queue_name)]
            connected_legs = [l for l in task_legs if int(l.connected_duration or 0) > 0]

            print(
                f"{fmt_ms(r.created_time)} | queue={norm(r.queue_name)} | outcome={outcome} | "
                f"term={norm(r.termination_type) or '—'} | connected_count={int(r.connected_count or 0)} | "
                f"task_agent={task_agent or '—'} | origin={norm(r.origin) or '—'}"
            )
            print(
                f"    task_queue_ms={int(r.queue_duration or 0)} | "
                f"legs={len(task_legs)} | queued_legs={len(queued_legs)} | connected_legs={len(connected_legs)}"
            )
            for l in task_legs:
                print(
                    f"    [{fmt_ms(l.created_time)} queue={norm(l.queue_name) or '—'} "
                    f"owner={norm(l.agent_name) or '—'} ring_ms={int(l.ringing_duration or 0)} "
                    f"connected_ms={int(l.connected_duration or 0)} hold_ms={int(l.hold_duration or 0)} "
                    f"wrapup_ms={int(l.wrapup_duration or 0)}]"
                )

        print("\n--- INTERPRETATION ---")
        print("Compare answered counts and agent names with the Agent Detail Report.")
        print("If answered tasks line up but row counts differ, the report is likely agent-leg/session-grain rather than unique-interaction-grain.")
        print("If many answered tasks lack a connected leg or agent attribution, we need to revisit answer classification or task/leg joins.")
        print("If raw abandoned plus other unanswered diverges from Analyzer, inspect those unanswered records before changing the dashboard KPI.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
