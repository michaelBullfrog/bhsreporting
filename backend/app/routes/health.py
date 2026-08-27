from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import CollectorRun

router = APIRouter(prefix="/api", tags=["health"])

@router.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok"}

@router.get("/data-health")
def data_health(db: Session = Depends(get_db)):
    last = db.query(CollectorRun).order_by(CollectorRun.started_at.desc()).first()
    return {
        "database": "ok",
        "last_collection": None if not last else {
            "started_at": last.started_at,
            "finished_at": last.finished_at,
            "success": last.success,
            "from_ms": last.from_ms,
            "to_ms": last.to_ms,
            "tasks": last.task_count,
            "task_details": last.detail_count,
            "task_legs": last.leg_count,
            "error": last.error,
        }
    }
