from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from ..database import get_db
from ..services.metrics import overview, agent_summary, staffing_summary, call_demand_summary, service_sla_summary, missed_callbacks_summary, inbound_outbound_summary, executive_overview_summary, dashboard_health_summary, data_coverage_summary
from ..models import Interaction, InteractionLeg

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

@router.get("/data-coverage")
def get_data_coverage(
    db: Session = Depends(get_db),
):
    result = data_coverage_summary(db)
    result["backend_version"] = BACKEND_VERSION
    return result


@router.get("/health-status")
def get_dashboard_health(
    db: Session = Depends(get_db),
):
    result = dashboard_health_summary(db)
    result["backend_version"] = BACKEND_VERSION
    return result


@router.get("/overview")
def get_overview(
    from_ms: int | None = Query(None),
    to_ms: int | None = Query(None),
    db: Session = Depends(get_db),
):
    return overview(db, from_ms, to_ms)

@router.get("/agents")
def get_agents(
    from_ms: int | None = Query(None),
    to_ms: int | None = Query(None),
    db: Session = Depends(get_db),
):
    return agent_summary(db, from_ms, to_ms)



@router.get("/queues")
def get_queues(
    from_ms: int | None = Query(None),
    to_ms: int | None = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(Interaction.queue_name).filter(
        Interaction.queue_name.isnot(None),
        Interaction.queue_name != "",
    )
    if from_ms is not None:
        q = q.filter(Interaction.created_time >= from_ms)
    if to_ms is not None:
        q = q.filter(Interaction.created_time < to_ms)
    values = sorted({
        str(row[0]).strip()
        for row in q.distinct().all()
        if row[0] and str(row[0]).strip()
    })
    return {"queues": values, "backend_version": BACKEND_VERSION}


@router.get("/executive-overview")
def get_executive_overview(
    from_ms: int | None = Query(None),
    to_ms: int | None = Query(None),
    timezone_name: str = Query("America/Detroit", alias="timezone"),
    queue_name: str | None = Query(None),
    db: Session = Depends(get_db),
):
    result = executive_overview_summary(
        db,
        from_ms=from_ms,
        to_ms=to_ms,
        timezone_name=timezone_name,
        queue_name=queue_name,
    )
    result["backend_version"] = BACKEND_VERSION
    return result


@router.get("/inbound-outbound")
def get_inbound_outbound(
    from_ms: int | None = Query(None),
    to_ms: int | None = Query(None),
    timezone_name: str = Query("America/Detroit", alias="timezone"),
    queue_name: str | None = Query(None),
    db: Session = Depends(get_db),
):
    result = inbound_outbound_summary(
        db,
        from_ms=from_ms,
        to_ms=to_ms,
        timezone_name=timezone_name,
        queue_name=queue_name,
    )
    result["backend_version"] = BACKEND_VERSION
    return result


@router.get("/missed-callbacks")
def get_missed_callbacks(
    from_ms: int | None = Query(None),
    to_ms: int | None = Query(None),
    timezone_name: str = Query("America/Detroit", alias="timezone"),
    queue_name: str | None = Query(None),
    db: Session = Depends(get_db),
):
    result = missed_callbacks_summary(
        db,
        from_ms=from_ms,
        to_ms=to_ms,
        unresolved_after_hours=24,
        timezone_name=timezone_name,
        queue_name=queue_name,
    )
    result["backend_version"] = BACKEND_VERSION
    return result


@router.get("/service-sla")
def get_service_sla(
    from_ms: int | None = Query(None),
    to_ms: int | None = Query(None),
    timezone_name: str = Query("America/Detroit", alias="timezone"),
    queue_name: str | None = Query(None),
    db: Session = Depends(get_db),
):
    result = service_sla_summary(
        db,
        from_ms=from_ms,
        to_ms=to_ms,
        sla_seconds=15,
        long_wait_seconds=300,
        short_abandon_seconds=0,
        timezone_name=timezone_name,
        queue_name=queue_name,
    )
    result["backend_version"] = BACKEND_VERSION
    return result


@router.get("/call-demand")
def get_call_demand(
    from_ms: int | None = Query(None),
    to_ms: int | None = Query(None),
    timezone_name: str = Query("America/Detroit", alias="timezone"),
    queue_name: str | None = Query(None),
    db: Session = Depends(get_db),
):
    result = call_demand_summary(
        db,
        from_ms=from_ms,
        to_ms=to_ms,
        timezone_name=timezone_name,
        queue_name=queue_name,
    )
    result["backend_version"] = BACKEND_VERSION
    return result


BACKEND_VERSION = "8.8.1"

@router.get("/version")
def get_version():
    return {
        "backend_version": BACKEND_VERSION,
        "staffing_route": "v8.8.1-strict-queue-sla-agent-attribution",
    }


@router.get("/staffing")
def get_staffing(
    from_ms: int | None = Query(None),
    to_ms: int | None = Query(None),
    queue_name: str | None = Query(None),
    db: Session = Depends(get_db),
):
    rows = staffing_summary(db, from_ms, to_ms)

    # Final API-boundary safety guard. One row per agent_id; normalized
    # agent_name is used only when agent_id is missing.
    unique = {}

    for row in rows:
        agent_id = str(row.get("agent_id") or "").strip()
        agent_name = str(row.get("agent_name") or "unknown").strip().casefold()

        key = f"id:{agent_id}" if agent_id else f"name:{agent_name}"

        # staffing_summary should already guarantee uniqueness. If a duplicate
        # somehow reaches the route, prefer the row with the smaller
        # unaccounted time, then the larger accounted percentage.
        current = unique.get(key)
        if current is None:
            unique[key] = row
            continue

        current_gap = int(current.get("unaccounted_ms") or 0)
        incoming_gap = int(row.get("unaccounted_ms") or 0)
        current_pct = float(current.get("accounted_percent") or 0)
        incoming_pct = float(row.get("accounted_percent") or 0)

        if (
            incoming_gap < current_gap
            or (
                incoming_gap == current_gap
                and incoming_pct > current_pct
            )
        ):
            unique[key] = row

    result = list(unique.values())

    if queue_name:
        leg_q = db.query(InteractionLeg).filter(InteractionLeg.queue_name == queue_name)
        if from_ms is not None:
            leg_q = leg_q.filter(InteractionLeg.created_time >= from_ms)
        if to_ms is not None:
            leg_q = leg_q.filter(InteractionLeg.created_time < to_ms)
        legs = leg_q.all()
        allowed_ids = {leg.agent_id.strip() for leg in legs if leg.agent_id and leg.agent_id.strip()}
        allowed_names = {leg.agent_name.strip().casefold() for leg in legs if leg.agent_name and leg.agent_name.strip()}
        result = [
            row for row in result
            if (
                (row.get("agent_id") and str(row.get("agent_id")).strip() in allowed_ids)
                or str(row.get("agent_name") or "").strip().casefold() in allowed_names
            )
        ]

    result.sort(key=lambda x: int(x.get("logged_in_ms") or 0), reverse=True)

    # Visible build marker for validation in the browser response.
    for row in result:
        row["backend_version"] = BACKEND_VERSION

    return result
