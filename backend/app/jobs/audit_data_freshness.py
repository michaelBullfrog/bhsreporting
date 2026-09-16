from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func

from ..database import Base, SessionLocal, engine
from ..models import (
    AgentSession,
    AgentStateActivity,
    CallingCollectorRun,
    CallingOutboundCall,
    CallingVoicemailEvent,
    CollectorRun,
    Interaction,
    InteractionLeg,
    WxccOAuthToken,
)

TZ = ZoneInfo("America/Detroit")


def fmt_ms(value: int | None) -> str:
    if not value:
        return "—"
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc).astimezone(TZ).strftime(
        "%Y-%m-%d %I:%M:%S %p %Z"
    )


def fmt_dt(value: datetime | None) -> str:
    if not value:
        return "—"
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(TZ).strftime("%Y-%m-%d %I:%M:%S %p %Z")


def day_counts(rows, attr: str, days: int = 8) -> Counter:
    cutoff = datetime.now(TZ).date() - timedelta(days=days - 1)
    counts = Counter()
    for row in rows:
        value = getattr(row, attr, None)
        if not value:
            continue
        d = datetime.fromtimestamp(value / 1000, tz=timezone.utc).astimezone(TZ).date()
        if d >= cutoff:
            counts[d.isoformat()] += 1
    return counts


def print_daily(title: str, counts: Counter, days: int = 8) -> None:
    print(f"\n{title}")
    start = datetime.now(TZ).date() - timedelta(days=days - 1)
    for i in range(days):
        day = start + timedelta(days=i)
        print(f"  {day.isoformat()}: {counts.get(day.isoformat(), 0)}")


def main() -> None:
    now = datetime.now(TZ)
    print("=== BHS DATA FRESHNESS AUDIT ===")
    print(f"Audit time: {now.strftime('%Y-%m-%d %I:%M:%S %p %Z')}")

    # The audit may be run before a collector process after deployment.
    Base.metadata.create_all(bind=engine, tables=[WxccOAuthToken.__table__])

    db = SessionLocal()
    try:
        last_run = (
            db.query(CollectorRun)
            .order_by(CollectorRun.started_at.desc())
            .first()
        )
        last_success = (
            db.query(CollectorRun)
            .filter(CollectorRun.success.is_(True))
            .order_by(CollectorRun.finished_at.desc().nullslast(), CollectorRun.started_at.desc())
            .first()
        )
        last_calling_run = (
            db.query(CallingCollectorRun)
            .order_by(CallingCollectorRun.started_at.desc())
            .first()
        )
        last_calling_success = (
            db.query(CallingCollectorRun)
            .filter(CallingCollectorRun.success.is_(True))
            .order_by(CallingCollectorRun.finished_at.desc().nullslast(), CallingCollectorRun.started_at.desc())
            .first()
        )
        wxcc_token = db.get(WxccOAuthToken, "wxcc")

        newest_interaction = db.query(func.max(Interaction.created_time)).scalar()
        newest_interaction_end = db.query(func.max(Interaction.ended_time)).scalar()
        newest_leg = db.query(func.max(InteractionLeg.created_time)).scalar()
        newest_agent_session = db.query(func.max(AgentSession.start_time)).scalar()
        newest_agent_state = db.query(func.max(AgentStateActivity.start_time)).scalar()
        newest_vm = db.query(func.max(CallingVoicemailEvent.start_time)).scalar()
        newest_vm_collected = db.query(func.max(CallingVoicemailEvent.collected_at)).scalar()
        newest_calling_outbound = db.query(func.max(CallingOutboundCall.start_time)).scalar()
        newest_calling_outbound_collected = db.query(func.max(CallingOutboundCall.collected_at)).scalar()

        print("\n--- FRESHNESS ---")
        print(f"Latest collector run:          {fmt_dt(last_run.started_at if last_run else None)}")
        print(f"Latest collector run success:  {getattr(last_run, 'success', None)}")
        if last_run and last_run.error:
            print(f"Latest collector error:        {last_run.error}")
        print(f"Latest successful collector:   {fmt_dt(last_success.finished_at if last_success else None)}")
        print(f"Newest WxCC interaction start: {fmt_ms(newest_interaction)}")
        print(f"Newest WxCC interaction end:   {fmt_ms(newest_interaction_end)}")
        print(f"Newest WxCC leg:               {fmt_ms(newest_leg)}")
        print(f"Newest agent session:          {fmt_ms(newest_agent_session)}")
        print(f"Newest agent state activity:   {fmt_ms(newest_agent_state)}")

        print("\n--- WxCC OAUTH TOKEN STORE ---")
        print(f"Shared token row present:      {bool(wxcc_token)}")
        print(f"Access token stored:           {bool(wxcc_token and wxcc_token.access_token)}")
        print(f"Refresh token stored:          {bool(wxcc_token and wxcc_token.refresh_token)}")
        print(f"Known access token expiry:     {fmt_dt(wxcc_token.expires_at if wxcc_token else None)}")
        print(f"Token row last updated:        {fmt_dt(wxcc_token.updated_at if wxcc_token else None)}")

        print("\n--- WEBEX CALLING / VOICEMAIL COLLECTOR ---")
        print(f"Latest Calling collector run:  {fmt_dt(last_calling_run.started_at if last_calling_run else None)}")
        print(f"Calling collector success:     {getattr(last_calling_run, 'success', None)}")
        if last_calling_run:
            print(f"Calling collector window end:  {fmt_ms(last_calling_run.to_ms)}")
            print(f"Calling CDR records returned:  {last_calling_run.cdr_records}")
            print(f"Voicemail events in run:       {last_calling_run.voicemail_events}")
            print(f"Outbound calls in run:         {last_calling_run.outbound_calls}")
            if last_calling_run.error:
                print(f"Calling collector error:       {last_calling_run.error}")
        print(f"Latest successful Calling run: {fmt_dt(last_calling_success.finished_at if last_calling_success else None)}")
        print(f"Newest voicemail event:        {fmt_ms(newest_vm)}")
        print(f"Voicemail row collected at:    {fmt_dt(newest_vm_collected)}")
        print(f"Newest Calling outbound call:  {fmt_ms(newest_calling_outbound)}")
        print(f"Outbound row collected at:     {fmt_dt(newest_calling_outbound_collected)}")

        cutoff_ms = int((now - timedelta(days=8)).timestamp() * 1000)
        interactions = db.query(Interaction).filter(Interaction.created_time >= cutoff_ms).all()
        legs = db.query(InteractionLeg).filter(InteractionLeg.created_time >= cutoff_ms).all()
        sessions = db.query(AgentSession).filter(AgentSession.start_time >= cutoff_ms).all()
        states = db.query(AgentStateActivity).filter(AgentStateActivity.start_time >= cutoff_ms).all()
        vm = db.query(CallingVoicemailEvent).filter(CallingVoicemailEvent.start_time >= cutoff_ms).all()
        outbound = db.query(CallingOutboundCall).filter(CallingOutboundCall.start_time >= cutoff_ms).all()

        print_daily("--- DAILY WxCC INTERACTIONS ---", day_counts(interactions, "created_time"))
        print_daily("--- DAILY WxCC LEGS ---", day_counts(legs, "created_time"))
        print_daily("--- DAILY AGENT SESSIONS ---", day_counts(sessions, "start_time"))
        print_daily("--- DAILY AGENT STATE ACTIVITIES ---", day_counts(states, "start_time"))
        print_daily("--- DAILY SERVICE AFTER HOURS VOICEMAIL EVENTS ---", day_counts(vm, "start_time"))
        print_daily("--- DAILY WEBEX CALLING OUTBOUND CDRS ---", day_counts(outbound, "start_time"))

        parked = [
            r for r in interactions
            if str(r.status or "").strip().lower() == "parked"
        ]
        unfinished = [
            r for r in interactions
            if not r.ended_time
        ]

        print("\n--- DATA QUALITY FLAGS (LAST 8 DAYS) ---")
        print(f"Parked interactions still stored: {len(parked)}")
        print(f"Interactions without ended_time:  {len(unfinished)}")
        if parked:
            for r in sorted(parked, key=lambda x: x.created_time or 0)[-10:]:
                print(
                    f"  parked {fmt_ms(r.created_time)} | queue={r.queue_name!r} | "
                    f"taskId={r.task_id}"
                )

        print("\n--- TAB SOURCE CHECK ---")
        print("Executive:           WxCC interactions + staffing data")
        print("Staffing:            agent sessions/state activity + interaction legs")
        print("Call Demand:         WxCC interactions")
        print("Service / SLA:       WxCC interactions + task agent attribution")
        print("Missed & Callbacks:  WxCC interactions + native callback fields")
        print("Call Activity:       WxCC interactions + task agent attribution")
        print("Voicemail:           Webex Calling CDR tables (separate collector)")

    finally:
        db.close()


if __name__ == "__main__":
    main()
