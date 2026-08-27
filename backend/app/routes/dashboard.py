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


@router.get("/staffing")
def get_staffing(
    from_ms: int | None = Query(None),
    to_ms: int | None = Query(None),
    db: Session = Depends(get_db),
):
    return staffing_summary(db, from_ms, to_ms)
