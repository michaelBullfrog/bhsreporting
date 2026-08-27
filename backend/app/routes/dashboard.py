from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from ..database import get_db
from ..services.metrics import overview, agent_summary, staffing_summary, call_demand_summary, service_sla_summary, missed_callbacks_summary, inbound_outbound_summary, executive_overview_summary

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

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


@router.get("/executive-overview")
def get_executive_overview(
    from_ms: int | None = Query(None),
    to_ms: int | None = Query(None),
    timezone_name: str = Query("America/Detroit", alias="timezone"),
    db: Session = Depends(get_db),
):
    result = executive_overview_summary(
        db,
        from_ms=from_ms,
        to_ms=to_ms,
        timezone_name=timezone_name,
    )
    result["backend_version"] = BACKEND_VERSION
    return result


@router.get("/inbound-outbound")
def get_inbound_outbound(
    from_ms: int | None = Query(None),
    to_ms: int | None = Query(None),
    timezone_name: str = Query("America/Detroit", alias="timezone"),
    db: Session = Depends(get_db),
):
    result = inbound_outbound_summary(
        db,
        from_ms=from_ms,
        to_ms=to_ms,
        timezone_name=timezone_name,
    )
    result["backend_version"] = BACKEND_VERSION
    return result


@router.get("/missed-callbacks")
def get_missed_callbacks(
    from_ms: int | None = Query(None),
    to_ms: int | None = Query(None),
    timezone_name: str = Query("America/Detroit", alias="timezone"),
    db: Session = Depends(get_db),
):
    result = missed_callbacks_summary(
        db,
        from_ms=from_ms,
        to_ms=to_ms,
        unresolved_after_hours=24,
        timezone_name=timezone_name,
    )
    result["backend_version"] = BACKEND_VERSION
    return result


@router.get("/service-sla")
def get_service_sla(
    from_ms: int | None = Query(None),
    to_ms: int | None = Query(None),
    timezone_name: str = Query("America/Detroit", alias="timezone"),
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
    )
    result["backend_version"] = BACKEND_VERSION
    return result


@router.get("/call-demand")
def get_call_demand(
    from_ms: int | None = Query(None),
    to_ms: int | None = Query(None),
    timezone_name: str = Query("America/Detroit", alias="timezone"),
    db: Session = Depends(get_db),
):
    result = call_demand_summary(
        db,
        from_ms=from_ms,
        to_ms=to_ms,
        timezone_name=timezone_name,
    )
    result["backend_version"] = BACKEND_VERSION
    return result


BACKEND_VERSION = "8.4"

@router.get("/version")
def get_version():
    return {
        "backend_version": BACKEND_VERSION,
        "staffing_route": "v8.4-bhs-official-logo",
    }


@router.get("/staffing")
def get_staffing(
    from_ms: int | None = Query(None),
    to_ms: int | None = Query(None),
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
    result.sort(key=lambda x: int(x.get("logged_in_ms") or 0), reverse=True)

    # Visible build marker for validation in the browser response.
    for row in result:
        row["backend_version"] = BACKEND_VERSION

    return result
