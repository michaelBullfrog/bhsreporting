from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from ..database import SessionLocal
from ..models import Interaction, InteractionLeg, InteractionAgent, AgentSession, AgentStateActivity
from ..services.metrics import (
    call_demand_summary,
    service_sla_summary,
    missed_callbacks_summary,
    inbound_outbound_summary,
    staffing_summary,
)
from .utils import local_day_window_ms

TZ = ZoneInfo("America/Detroit")


def fmt_ms(value):
    if not value:
        return "—"
    return datetime.fromtimestamp(value / 1000, tz=TZ).strftime("%Y-%m-%d %I:%M:%S %p %Z")


def main():
    today = datetime.now(TZ).date()
    from_ms, to_ms = local_day_window_ms(today)

    db = SessionLocal()
    try:
        interactions = (
            db.query(Interaction)
            .filter(Interaction.created_time >= from_ms, Interaction.created_time < to_ms)
            .all()
        )
        legs = (
            db.query(InteractionLeg)
            .filter(InteractionLeg.created_time >= from_ms, InteractionLeg.created_time < to_ms)
            .all()
        )
        sessions = (
            db.query(AgentSession)
            .filter(AgentSession.start_time >= from_ms, AgentSession.start_time < to_ms)
            .all()
        )
        states = (
            db.query(AgentStateActivity)
            .filter(AgentStateActivity.start_time >= from_ms, AgentStateActivity.start_time < to_ms)
            .all()
        )

        print("=== BHS TODAY DASHBOARD AUDIT ===")
        print(f"Date: {today.isoformat()} ({TZ.key})")
        print(f"Window: {fmt_ms(from_ms)} through {fmt_ms(to_ms - 1)}")

        print("\n--- NORMALIZED SOURCE ROWS ---")
        print(f"Interactions:           {len(interactions)}")
        print(f"Interaction legs:       {len(legs)}")
        print(f"Agent sessions:         {len(sessions)}")
        print(f"Agent state activities: {len(states)}")
        print(f"Newest interaction:     {fmt_ms(max((r.created_time or 0 for r in interactions), default=0))}")
        print(f"Newest leg:             {fmt_ms(max((r.created_time or 0 for r in legs), default=0))}")
        print(f"Newest agent session:   {fmt_ms(max((r.start_time or 0 for r in sessions), default=0))}")
        print(f"Newest agent state:     {fmt_ms(max((r.start_time or 0 for r in states), default=0))}")

        cd = call_demand_summary(
            db,
            from_ms=from_ms,
            to_ms=to_ms,
            timezone_name=TZ.key,
        )
        o = cd.get("overview", {})
        print("\n--- CALL DEMAND (SAME LOGIC AS DASHBOARD API) ---")
        print(f"Inbound:                {o.get('inbound', 0)}")
        print(f"Queued inbound:         {o.get('queued_inbound', 0)}")
        print(f"Queued answered:        {o.get('queued_answered', 0)}")
        print(f"Queued abandoned:       {o.get('queued_abandoned', 0)}")
        print(f"Non-queued inbound:     {o.get('no_queue_inbound', 0)}")
        print(f"Outbound:               {o.get('outbound', 0)}")
        print(f"Queue groups:           {len(cd.get('queues', []) or [])}")
        print(f"Daily rows:             {len(cd.get('daily', []) or [])}")
        for row in cd.get("daily", []) or []:
            print(
                f"  {row.get('date')}: inbound={row.get('inbound', 0)} "
                f"answered={row.get('queued_answered', 0)} "
                f"abandoned={row.get('queued_abandoned', 0)}"
            )

        sla = service_sla_summary(
            db,
            from_ms=from_ms,
            to_ms=to_ms,
            sla_seconds=15,
            long_wait_seconds=300,
            short_abandon_seconds=0,
            timezone_name=TZ.key,
        )
        so = sla.get("overview", {})
        print("\n--- SERVICE / SLA ---")
        print(f"Offered:                {so.get('offered', so.get('queued_inbound', 0))}")
        print(f"Answered:               {so.get('answered', so.get('queued_answered', 0))}")
        print(f"Abandoned:              {so.get('abandoned', so.get('queued_abandoned', 0))}")

        mc = missed_callbacks_summary(
            db,
            from_ms=from_ms,
            to_ms=to_ms,
            unresolved_after_hours=24,
            timezone_name=TZ.key,
        )
        mo = mc.get("overview", mc.get("summary", {}))
        print("\n--- MISSED & CALLBACKS ---")
        for key in ("missed", "missed_calls", "native_callbacks", "successful_callbacks", "outstanding"):
            if key in mo:
                print(f"{key}: {mo.get(key)}")

        activity = inbound_outbound_summary(
            db,
            from_ms=from_ms,
            to_ms=to_ms,
            timezone_name=TZ.key,
        )
        ao = activity.get("overview", activity.get("summary", {}))
        print("\n--- CALL ACTIVITY ---")
        for key in ("inbound", "outbound", "total", "total_interactions"):
            if key in ao:
                print(f"{key}: {ao.get(key)}")

        staffing = staffing_summary(db, from_ms, to_ms)
        print("\n--- STAFFING ---")
        print(f"Agents returned:        {len(staffing)}")

        print("\nIf Call Demand above has today data but the browser page does not, the collector is current and the remaining issue is in the page request/filter/render path.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
