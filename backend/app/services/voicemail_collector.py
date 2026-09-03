from __future__ import annotations

from datetime import datetime, timezone
import time
import httpx
from sqlalchemy.orm import Session
from ..config import settings
from ..models import CallingOutboundCall, CallingVoicemailEvent
from ..webex.calling_token_manager import calling_token_manager


def _iso(ms:int)->str:
    return datetime.fromtimestamp(ms/1000,tz=timezone.utc).isoformat(timespec="milliseconds").replace("+00:00","Z")

def _epoch(value):
    if not value:
        return None
    try:
        return int(datetime.fromisoformat(str(value).replace("Z","+00:00")).timestamp()*1000)
    except Exception:
        return None

def _is_service_vm(row:dict)->bool:
    return (
        str(row.get("User type") or "").strip() == "VoiceMailGroup"
        and str(row.get("User UUID") or "").strip() == settings.service_vm_group_uuid
    )


def _is_outbound_user_call(row:dict)->bool:
    return (
        str(row.get("Direction") or "").strip().upper() == "ORIGINATING"
        and str(row.get("User type") or "").strip() == "User"
        and bool(str(row.get("Called number") or "").strip())
        and bool(str(row.get("Report ID") or "").strip())
    )

def _bool(value):
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"true","yes","1"}

def collect_service_voicemail_window(db:Session, from_ms:int, to_ms:int)->dict:
    if to_ms <= from_ms:
        raise ValueError("to_ms must be greater than from_ms")
    if to_ms-from_ms > 12*60*60*1000:
        raise ValueError("Webex Calling CDR windows cannot exceed 12 hours")

    token=calling_token_manager.get_access_token()
    url=f"{settings.webex_calling_cdr_base_url.rstrip('/')}/v1/cdr_feed"
    params={"startTime":_iso(from_ms),"endTime":_iso(to_ms),"max":5000}
    # The Calling CDR feed enforces a fairly small request-rate threshold.
    # Retry 429 responses instead of aborting a historical backfill.
    max_attempts = 6
    with httpx.Client(timeout=60) as client:
        for attempt in range(1, max_attempts + 1):
            resp=client.get(url,params=params,headers={"Authorization":f"Bearer {token}","Accept":"application/json"})
            if resp.status_code != 429:
                break

            retry_after = resp.headers.get("Retry-After")
            try:
                wait_seconds = max(1, int(float(retry_after))) if retry_after else min(15 * attempt, 60)
            except (TypeError, ValueError):
                wait_seconds = min(15 * attempt, 60)

            if attempt >= max_attempts:
                raise RuntimeError(f"Calling CDR HTTP 429 after {max_attempts} attempts: {resp.text}")

            print({
                "warning": "Calling CDR rate limited",
                "status": 429,
                "attempt": attempt,
                "retry_in_seconds": wait_seconds,
                "from": from_ms,
                "to": to_ms,
            }, flush=True)
            time.sleep(wait_seconds)

    if resp.status_code >= 400:
        raise RuntimeError(f"Calling CDR HTTP {resp.status_code}: {resp.text}")
    body=resp.json()
    rows=body.get("items") or []

    matched=[r for r in rows if _is_service_vm(r)]
    # One voicemail-group event per correlation ID. Prefer the record whose
    # Called number is the actual group extension when duplicate CDR legs exist.
    chosen={}
    for row in matched:
        corr=str(row.get("Correlation ID") or "").strip()
        if not corr:
            continue
        current=chosen.get(corr)
        if current is None or (str(row.get("Called number") or "") == settings.service_vm_extension and str(current.get("Called number") or "") != settings.service_vm_extension):
            chosen[corr]=row

    inserted=updated=0
    for corr,row in chosen.items():
        obj=db.get(CallingVoicemailEvent,corr)
        is_new=obj is None
        if obj is None:
            obj=CallingVoicemailEvent(correlation_id=corr)
            db.add(obj)
        obj.report_id=str(row.get("Report ID") or "") or None
        obj.interaction_id=str(row.get("Interaction ID") or "") or None
        obj.voicemail_group_uuid=str(row.get("User UUID") or "") or None
        obj.voicemail_group_name=str(row.get("User") or "") or settings.service_vm_group_name
        obj.extension=str(row.get("User number") or row.get("Called number") or "") or settings.service_vm_extension
        obj.caller_number=str(row.get("Calling number") or row.get("Caller ID number") or "") or None
        obj.caller_name=str(row.get("Calling line ID") or "") or None
        obj.location=str(row.get("Location") or "") or None
        obj.start_time=_epoch(row.get("Start time"))
        obj.answer_time=_epoch(row.get("Answer time"))
        obj.release_time=_epoch(row.get("Release time"))
        try: obj.duration_seconds=int(row.get("Duration") or 0)
        except Exception: obj.duration_seconds=0
        obj.call_outcome=str(row.get("Call outcome") or "") or None
        obj.call_outcome_reason=str(row.get("Call outcome reason") or "") or None
        obj.answer_indicator=str(row.get("Answer indicator") or "") or None
        obj.redirect_reason=str(row.get("Redirect reason") or "") or None
        obj.redirecting_number=str(row.get("Redirecting number") or "") or None
        obj.user_type=str(row.get("User type") or "") or None
        obj.raw_payload=row
        inserted += 1 if is_new else 0
        updated += 0 if is_new else 1

    outbound_rows=[r for r in rows if _is_outbound_user_call(r)]

    # Webex can return the same outbound CDR Report ID more than once in a
    # single feed window.  Deduplicate the current response before adding ORM
    # objects.  Session.get() cannot reliably find another *pending* object
    # with the same primary key before the session is flushed, which otherwise
    # results in a duplicate-key failure at commit time.
    outbound_by_report_id={}
    for row in outbound_rows:
        report_id=str(row.get("Report ID") or "").strip()
        if report_id:
            outbound_by_report_id[report_id]=row

    outbound_inserted=outbound_updated=0
    for report_id,row in outbound_by_report_id.items():
        obj=db.get(CallingOutboundCall,report_id)
        is_new=obj is None
        if obj is None:
            obj=CallingOutboundCall(report_id=report_id)
            db.add(obj)
        obj.correlation_id=str(row.get("Correlation ID") or "") or None
        obj.interaction_id=str(row.get("Interaction ID") or "") or None
        obj.user_uuid=str(row.get("User UUID") or "") or None
        obj.user_name=str(row.get("User") or "") or None
        obj.user_type=str(row.get("User type") or "") or None
        obj.called_number=str(row.get("Called number") or "") or None
        obj.calling_number=str(row.get("Calling number") or "") or None
        obj.location=str(row.get("Location") or "") or None
        obj.start_time=_epoch(row.get("Start time"))
        obj.answer_time=_epoch(row.get("Answer time"))
        obj.release_time=_epoch(row.get("Release time"))
        try: obj.duration_seconds=int(row.get("Duration") or 0)
        except Exception: obj.duration_seconds=0
        obj.answered=_bool(row.get("Answered"))
        obj.answer_indicator=str(row.get("Answer indicator") or "") or None
        obj.call_outcome=str(row.get("Call outcome") or "") or None
        obj.call_outcome_reason=str(row.get("Call outcome reason") or "") or None
        obj.raw_payload=row
        outbound_inserted += 1 if is_new else 0
        outbound_updated += 0 if is_new else 1

    db.commit()
    return {
        "success":True,"from":from_ms,"to":to_ms,"cdr_records":len(rows),
        "matched_cdr_legs":len(matched),"unique_voicemail_events":len(chosen),
        "inserted":inserted,"updated":updated,
        "outbound_user_calls":len(outbound_rows),
        "unique_outbound_cdrs":len(outbound_by_report_id),
        "outbound_duplicate_cdrs_skipped":len(outbound_rows)-len(outbound_by_report_id),
        "outbound_inserted":outbound_inserted,"outbound_updated":outbound_updated,
        "voicemail_group":settings.service_vm_group_name,
        "voicemail_group_uuid":settings.service_vm_group_uuid,
        "extension":settings.service_vm_extension,
    }
