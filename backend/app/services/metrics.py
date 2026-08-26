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
