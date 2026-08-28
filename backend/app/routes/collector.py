from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from ..database import get_db
from ..services.collector import collect_window

router = APIRouter(prefix="/api/collector", tags=["collector"])

@router.post("/run")
def run_collector(
    from_ms: int = Query(...),
    to_ms: int = Query(...),
    db: Session = Depends(get_db),
):
    return collect_window(db, from_ms, to_ms)
