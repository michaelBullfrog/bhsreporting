from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from ..database import get_db
from ..services.metrics import overview, agent_summary, staffing_summary

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


BACKEND_VERSION = "3.8"

@router.get("/version")
def get_version():
    return {
        "backend_version": BACKEND_VERSION,
        "staffing_route": "v3.8-metric-definitions",
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
