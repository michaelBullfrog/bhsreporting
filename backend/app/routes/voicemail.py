from collections import Counter
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import CallingOutboundCall, CallingVoicemailEvent
from ..services.voicemail_collector import collect_service_voicemail_window
from ..config import settings

router=APIRouter(prefix="/api/voicemail",tags=["voicemail"])
CALLBACK_WINDOW_MS=72*60*60*1000

def _norm_phone(value):
    digits=''.join(ch for ch in str(value or '') if ch.isdigit())
    if len(digits)==11 and digits.startswith('1'):
        digits=digits[1:]
    return digits[-10:] if len(digits)>=10 else digits

def _successful_callback(call):
    return bool(call.answered) and str(call.answer_indicator or '').lower().startswith('yes') and str(call.call_outcome or '').lower()=='success'

def _callback_matches(voicemails, outbound_calls):
    # One outbound call can belong to only one voicemail. If a caller leaves
    # multiple messages, attach the callback to the most recent unresolved one.
    state={v.correlation_id:{"attempt":None,"success":None} for v in voicemails}
    by_number={}
    for v in sorted(voicemails,key=lambda x:x.start_time or 0):
        n=_norm_phone(v.caller_number)
        if n: by_number.setdefault(n,[]).append(v)
    for call in sorted(outbound_calls,key=lambda x:x.start_time or 0):
        n=_norm_phone(call.called_number)
        candidates=[]
        for v in by_number.get(n,[]):
            if not v.start_time or not call.start_time: continue
            st=state[v.correlation_id]
            if st["success"] is not None: continue
            if v.start_time < call.start_time <= v.start_time+CALLBACK_WINDOW_MS:
                candidates.append(v)
        if not candidates: continue
        v=max(candidates,key=lambda x:x.start_time or 0)
        st=state[v.correlation_id]
        if st["attempt"] is None: st["attempt"]=call
        if _successful_callback(call): st["success"]=call
    return state

@router.post("/collector/run")
def run_voicemail_collector(from_ms:int=Query(...),to_ms:int=Query(...),db:Session=Depends(get_db)):
    return collect_service_voicemail_window(db,from_ms,to_ms)

@router.get("/service-after-hours")
def service_after_hours(from_ms:int|None=Query(None),to_ms:int|None=Query(None),timezone_name:str=Query("America/Detroit",alias="timezone"),db:Session=Depends(get_db)):
    q=db.query(CallingVoicemailEvent).filter(CallingVoicemailEvent.voicemail_group_uuid==settings.service_vm_group_uuid)
    if from_ms is not None: q=q.filter(CallingVoicemailEvent.start_time>=from_ms)
    if to_ms is not None: q=q.filter(CallingVoicemailEvent.start_time<to_ms)
    rows=q.order_by(CallingVoicemailEvent.start_time.desc()).all()

    if rows:
        earliest=min((r.start_time or 0) for r in rows)
        latest=max((r.start_time or 0) for r in rows)+CALLBACK_WINDOW_MS
        oq=db.query(CallingOutboundCall).filter(CallingOutboundCall.start_time>earliest,CallingOutboundCall.start_time<=latest)
        outbound=oq.order_by(CallingOutboundCall.start_time.asc()).all()
    else:
        outbound=[]
    callback_state=_callback_matches(rows,outbound)

    tz=ZoneInfo(timezone_name)
    daily=Counter(); hourly=Counter(); callers=set(); total_duration=0; longest=0; success=0
    callback_completed=callback_attempted=outstanding=0; callback_seconds=[]
    details=[]
    for r in rows:
        dur=int(r.duration_seconds or 0); total_duration+=dur; longest=max(longest,dur)
        if str(r.call_outcome or '').lower()=='success': success+=1
        if r.caller_number: callers.add(r.caller_number)
        if r.start_time:
            dt=datetime.fromtimestamp(r.start_time/1000,tz=timezone.utc).astimezone(tz)
            daily[dt.date().isoformat()]+=1; hourly[dt.hour]+=1

        st=callback_state.get(r.correlation_id,{"attempt":None,"success":None})
        attempt=st.get("attempt"); cb=st.get("success")
        if cb:
            cb_status="Called Back"; callback_completed+=1
            delay=max(0,int(((cb.start_time or 0)-(r.start_time or 0))/1000)); callback_seconds.append(delay)
            display_call=cb
        elif attempt:
            cb_status="Callback Attempted"; callback_attempted+=1
            delay=max(0,int(((attempt.start_time or 0)-(r.start_time or 0))/1000)); display_call=attempt
        else:
            cb_status="Outstanding"; outstanding+=1; delay=None; display_call=None

        details.append({
            "correlation_id":r.correlation_id,"interaction_id":r.interaction_id,
            "received_time":r.start_time,"caller_number":r.caller_number,"caller_name":r.caller_name,
            "duration_seconds":dur,"outcome":r.call_outcome,"outcome_reason":r.call_outcome_reason,
            "answer_indicator":r.answer_indicator,"redirect_reason":r.redirect_reason,
            "redirecting_number":r.redirecting_number,"location":r.location,
            "voicemail_group":r.voicemail_group_name,"extension":r.extension,
            "callback_status":cb_status,
            "callback_time":display_call.start_time if display_call else None,
            "callback_by":display_call.user_name if display_call else None,
            "callback_delay_seconds":delay,
            "callback_duration_seconds":int(display_call.duration_seconds or 0) if display_call else None,
            "callback_answered":bool(display_call.answered) if display_call else None,
            "callback_outcome":display_call.call_outcome if display_call else None,
        })
    return {
        "backend_version":"9.2.0",
        "voicemail_group":{"name":settings.service_vm_group_name,"uuid":settings.service_vm_group_uuid,"extension":settings.service_vm_extension,"location":"Knoxville TN"},
        "summary":{
            "voicemail_events":len(rows),"unique_callers":len(callers),"successful_events":success,
            "avg_duration_seconds":round(total_duration/len(rows),1) if rows else 0,
            "longest_duration_seconds":longest,
            "called_back":callback_completed,"callback_attempted":callback_attempted,"outstanding":outstanding,
            "callback_rate_percent":round(callback_completed/len(rows)*100,1) if rows else 0,
            "avg_callback_seconds":round(sum(callback_seconds)/len(callback_seconds),1) if callback_seconds else 0,
        },
        "daily":[{"date":k,"count":daily[k]} for k in sorted(daily)],
        "hourly":[{"hour":h,"count":hourly[h]} for h in range(24)],
        "details":details,
        "definitions":{
            "voicemail_event":"One unique Webex Calling CDR correlation ID whose User type is VoiceMailGroup and User UUID matches Service After Hours Vmail.",
            "callback":"A later Webex Calling CDR record within 72 hours where Direction is ORIGINATING, User type is User, and Called number matches the voicemail caller. Answered successful calls are Called Back; unanswered outbound calls are Callback Attempted.",
            "duration":"Webex Calling CDR Duration for the VoiceMailGroup leg. It can include voicemail treatment and is not guaranteed to equal recorded-message audio length.",
            "external_storage":"This voicemail group stores messages externally by email; CDR confirms the voicemail-group call event, not whether the email was opened or listened to.",
        },
    }
