from sqlalchemy import func, case
from sqlalchemy.orm import Session
from ..models import Interaction, InteractionLeg

def overview(db: Session, from_ms: int | None = None, to_ms: int | None = None):
    q = db.query(Interaction)
    if from_ms is not None:
        q = q.filter(Interaction.created_time >= from_ms)
    if to_ms is not None:
        q = q.filter(Interaction.created_time < to_ms)

    total = q.count()
    inbound = q.filter(Interaction.direction == "inbound").count()
    outbound = q.filter(Interaction.direction == "outdial").count()
    answered = q.filter(Interaction.connected_count > 0).count()
    abandoned = q.filter(Interaction.termination_type == "abandoned").count()
    callbacks = q.filter(Interaction.callback_status == "Success").count()

    avg_queue_ms = q.with_entities(func.avg(Interaction.queue_duration)).scalar() or 0
    max_queue_ms = q.with_entities(func.max(Interaction.queue_duration)).scalar() or 0

    return {
        "total_interactions": total,
        "inbound": inbound,
        "outdial": outbound,
        "answered": answered,
        "abandoned": abandoned,
        "successful_native_callbacks": callbacks,
        "answer_rate": round(answered / inbound * 100, 2) if inbound else 0,
        "abandon_rate": round(abandoned / inbound * 100, 2) if inbound else 0,
        "avg_queue_seconds": round(float(avg_queue_ms) / 1000, 2),
        "max_queue_seconds": round(float(max_queue_ms) / 1000, 2),
    }

def agent_summary(db: Session, from_ms: int | None = None, to_ms: int | None = None):
    q = db.query(
        InteractionLeg.agent_name,
        func.count(InteractionLeg.leg_id).label("legs"),
        func.sum(InteractionLeg.connected_duration).label("connected_ms"),
        func.sum(InteractionLeg.ringing_duration).label("ringing_ms"),
        func.sum(InteractionLeg.wrapup_duration).label("wrapup_ms"),
        func.sum(InteractionLeg.hold_duration).label("hold_ms"),
    ).filter(InteractionLeg.agent_name.isnot(None))

    if from_ms is not None:
        q = q.filter(InteractionLeg.created_time >= from_ms)
    if to_ms is not None:
        q = q.filter(InteractionLeg.created_time < to_ms)

    q = q.group_by(InteractionLeg.agent_name).order_by(func.sum(InteractionLeg.connected_duration).desc())

    rows = []
    for r in q.all():
        rows.append({
            "agent_name": r.agent_name,
            "legs": r.legs,
            "connected_seconds": round((r.connected_ms or 0) / 1000, 2),
            "ringing_seconds": round((r.ringing_ms or 0) / 1000, 2),
            "wrapup_seconds": round((r.wrapup_ms or 0) / 1000, 2),
            "hold_seconds": round((r.hold_ms or 0) / 1000, 2),
        })
    return rows

def staffing_summary(db: Session, from_ms: int | None = None, to_ms: int | None = None):
    """
    Agent staffing summary using stored WxCC agent sessions/state activities.

    Definitions:
      - Idle: explicit WxCC state == "idle", including activity IDs containing
        "idle-rona". The ID detail is preserved, but the duration remains idle.
      - RONA time: explicit WxCC state == "not-responding".
      - RONA events: count of explicit "not-responding" activity records.
      - Utilization: (connected + wrap-up) / logged-in time.
      - Occupancy: (connected + wrap-up) /
                   (available + connected + wrap-up).
      - Availability: available / logged-in time.

    Date-window clipping is intentionally not applied yet. When from_ms/to_ms
    are supplied, records are selected by their start timestamp. The next
    reporting-hardening step is interval clipping for sessions/activities that
    cross a reporting boundary.
    """
    from ..models import AgentSession, AgentStateActivity

    session_q = db.query(
        AgentSession.agent_id,
        AgentSession.agent_name,
        AgentSession.team_name,
        func.sum(
            case(
                (
                    (AgentSession.end_time.isnot(None)) &
                    (AgentSession.end_time >= AgentSession.start_time),
                    AgentSession.end_time - AgentSession.start_time,
                ),
                else_=0,
            )
        ).label("logged_in_ms"),
    )

    activity_q = db.query(
        AgentStateActivity.agent_id,
        AgentStateActivity.agent_name,
        AgentStateActivity.team_name,
        AgentStateActivity.state,
        AgentStateActivity.state_detail,
        func.sum(AgentStateActivity.duration_ms).label("duration_ms"),
        func.count(AgentStateActivity.activity_id).label("activity_count"),
    )

    if from_ms is not None:
        session_q = session_q.filter(AgentSession.start_time >= from_ms)
        activity_q = activity_q.filter(AgentStateActivity.start_time >= from_ms)
    if to_ms is not None:
        session_q = session_q.filter(AgentSession.start_time < to_ms)
        activity_q = activity_q.filter(AgentStateActivity.start_time < to_ms)

    session_rows = session_q.group_by(
        AgentSession.agent_id,
        AgentSession.agent_name,
        AgentSession.team_name,
    ).all()

    activity_rows = activity_q.group_by(
        AgentStateActivity.agent_id,
        AgentStateActivity.agent_name,
        AgentStateActivity.team_name,
        AgentStateActivity.state,
        AgentStateActivity.state_detail,
    ).all()

    def empty_agent(agent_id=None, agent_name=None, team_name=None):
        return {
            "agent_id": agent_id,
            "agent_name": agent_name,
            "team_name": team_name,
            "logged_in_ms": 0,
            "available_ms": 0,
            "idle_ms": 0,
            "rona_ms": 0,
            "rona_events": 0,
            "connected_ms": 0,
            "wrapup_ms": 0,
            "ringing_ms": 0,
            "inbound_reserved_ms": 0,
            "outdial_reserved_ms": 0,
        }

    agents = {}
    for r in session_rows:
        key = r.agent_id or r.agent_name
        row = empty_agent(r.agent_id, r.agent_name, r.team_name)
        row["logged_in_ms"] = int(r.logged_in_ms or 0)
        agents[key] = row

    for r in activity_rows:
        key = r.agent_id or r.agent_name
        row = agents.setdefault(
            key,
            empty_agent(r.agent_id, r.agent_name, r.team_name),
        )

        # Keep the most useful known team/name if an activity fills a gap.
        row["agent_name"] = row["agent_name"] or r.agent_name
        row["team_name"] = row["team_name"] or r.team_name

        ms = int(r.duration_ms or 0)
        count = int(r.activity_count or 0)
        state = (r.state or "").strip().lower()

        if state == "available":
            row["available_ms"] += ms
        elif state == "idle":
            # "idle-rona" in the activity ID is retained in state_detail as
            # metadata, but its duration is still an idle interval.
            row["idle_ms"] += ms
        elif state == "not-responding":
            row["rona_ms"] += ms
            row["rona_events"] += count
        elif state == "connected":
            row["connected_ms"] += ms
        elif state in {"wrapup", "wrap-up"}:
            row["wrapup_ms"] += ms
        elif state == "ringing":
            row["ringing_ms"] += ms
        elif state == "inbound-reserved":
            row["inbound_reserved_ms"] += ms
        elif state == "outdial-reserved":
            row["outdial_reserved_ms"] += ms

    output = []
    for row in agents.values():
        logged = row["logged_in_ms"]
        productive = row["connected_ms"] + row["wrapup_ms"]
        occupancy_denominator = (
            row["available_ms"] +
            row["connected_ms"] +
            row["wrapup_ms"]
        )

        accounted_ms = (
            row["available_ms"]
            + row["idle_ms"]
            + row["rona_ms"]
            + row["connected_ms"]
            + row["wrapup_ms"]
            + row["ringing_ms"]
            + row["inbound_reserved_ms"]
            + row["outdial_reserved_ms"]
        )
        unaccounted_ms = max(logged - accounted_ms, 0)

        row.update({
            "accounted_ms": accounted_ms,
            "unaccounted_ms": unaccounted_ms,
            "accounted_percent": (
                round(accounted_ms / logged * 100, 2)
                if logged else 0
            ),
            # Staffing percentages should only be treated as complete when
            # nearly all logged-in time is represented by known activity
            # intervals. Small millisecond-level overlaps/gaps are expected.
            "staffing_data_complete": (
                (accounted_ms / logged) >= 0.99
                if logged else False
            ),
            "logged_in_hours": round(logged / 3_600_000, 2),
            "available_hours": round(row["available_ms"] / 3_600_000, 2),
            "idle_hours": round(row["idle_ms"] / 3_600_000, 2),
            "rona_hours": round(row["rona_ms"] / 3_600_000, 2),
            "connected_hours": round(row["connected_ms"] / 3_600_000, 2),
            "wrapup_hours": round(row["wrapup_ms"] / 3_600_000, 2),
            "ringing_hours": round(row["ringing_ms"] / 3_600_000, 2),

            # Whole-session active-work measure.
            "utilization_percent": (
                round(productive / logged * 100, 2)
                if logged else 0
            ),

            # Contact-center occupancy measure that excludes idle/not-ready.
            "occupancy_percent": (
                round(productive / occupancy_denominator * 100, 2)
                if occupancy_denominator else 0
            ),

            "availability_percent": (
                round(row["available_ms"] / logged * 100, 2)
                if logged else 0
            ),
        })
        output.append(row)

    output.sort(key=lambda x: x["logged_in_ms"], reverse=True)
    return output

