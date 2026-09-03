from collections import Counter, defaultdict
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import CallingVoicemailEvent
from ..services.voicemail_collector import collect_service_voicemail_window
from ..config import settings

router=APIRouter(prefix="/api/voicemail",tags=["voicemail"])

@router.post("/collector/run")
def run_voicemail_collector(from_ms:int=Query(...),to_ms:int=Query(...),db:Session=Depends(get_db)):
    return collect_service_voicemail_window(db,from_ms,to_ms)

@router.get("/service-after-hours")
def service_after_hours(from_ms:int|None=Query(None),to_ms:int|None=Query(None),timezone_name:str=Query("America/Detroit",alias="timezone"),db:Session=Depends(get_db)):
    q=db.query(CallingVoicemailEvent).filter(CallingVoicemailEvent.voicemail_group_uuid==settings.service_vm_group_uuid)
    if from_ms is not None: q=q.filter(CallingVoicemailEvent.start_time>=from_ms)
    if to_ms is not None: q=q.filter(CallingVoicemailEvent.start_time<to_ms)
    rows=q.order_by(CallingVoicemailEvent.start_time.desc()).all()
    tz=ZoneInfo(timezone_name)
    daily=Counter(); hourly=Counter()
    callers=set(); total_duration=0; longest=0; success=0
    details=[]
    for r in rows:
        dur=int(r.duration_seconds or 0); total_duration+=dur; longest=max(longest,dur)
        if str(r.call_outcome or '').lower()=='success': success+=1
        if r.caller_number: callers.add(r.caller_number)
        if r.start_time:
            dt=datetime.fromtimestamp(r.start_time/1000,tz=timezone.utc).astimezone(tz)
            daily[dt.date().isoformat()]+=1; hourly[dt.hour]+=1
        details.append({
            "correlation_id":r.correlation_id,"interaction_id":r.interaction_id,
            "received_time":r.start_time,"caller_number":r.caller_number,"caller_name":r.caller_name,
            "duration_seconds":dur,"outcome":r.call_outcome,"outcome_reason":r.call_outcome_reason,
            "answer_indicator":r.answer_indicator,"redirect_reason":r.redirect_reason,
            "redirecting_number":r.redirecting_number,"location":r.location,
            "voicemail_group":r.voicemail_group_name,"extension":r.extension,
        })
    return {
        "backend_version":"9.1.0",
        "voicemail_group":{"name":settings.service_vm_group_name,"uuid":settings.service_vm_group_uuid,"extension":settings.service_vm_extension,"location":"Knoxville TN"},
        "summary":{
            "voicemail_events":len(rows),"unique_callers":len(callers),"successful_events":success,
            "avg_duration_seconds":round(total_duration/len(rows),1) if rows else 0,
            "longest_duration_seconds":longest,
        },
        "daily":[{"date":k,"count":daily[k]} for k in sorted(daily)],
        "hourly":[{"hour":h,"count":hourly[h]} for h in range(24)],
        "details":details,
        "definitions":{
            "voicemail_event":"One unique Webex Calling CDR correlation ID whose User type is VoiceMailGroup and User UUID matches Service After Hours Vmail.",
            "duration":"Webex Calling CDR Duration for the VoiceMailGroup leg. It can include voicemail treatment and is not guaranteed to equal recorded-message audio length.",
            "external_storage":"This voicemail group stores messages externally by email; CDR confirms the voicemail-group call event, not whether the email was opened or listened to.",
        },
    }
