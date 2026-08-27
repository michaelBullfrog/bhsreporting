from datetime import datetime, timezone
from sqlalchemy.orm import Session
from ..models import RawWxccRecord, Interaction, InteractionAgent, InteractionLeg, CollectorRun, AgentSession, AgentStateActivity
from ..webex.client import WxccClient

def _upsert(db: Session, model, key_name: str, key_value: str, values: dict):
    obj = db.get(model, key_value)
    if obj is None:
        obj = model(**values)
        db.add(obj)
    else:
        for k, v in values.items():
            setattr(obj, k, v)
    return obj

def collect_window(
    db: Session,
    from_ms: int,
    to_ms: int,
    *,
    include_agent_sessions: bool = True,
) -> dict:
    run = CollectorRun(from_ms=from_ms, to_ms=to_ms)
    db.add(run)
    db.commit()
    db.refresh(run)

    client = WxccClient()

    # Always initialize these so error handling can never reference an
    # unassigned local variable.
    tasks = []
    details = []
    legs = []
    agent_sessions = []
    agent_session_error = None

    try:
        # Call/task history is the primary reporting dataset and is fetched
        # independently from staffing history.
        tasks = client.get_tasks(from_ms, to_ms)
        details = client.get_task_details(from_ms, to_ms)
        legs = client.get_task_legs(from_ms, to_ms)

        # Agent-session history is useful for staffing, but an older WxCC
        # agent-session pagination/schema error must not block call-history
        # ingestion.
        if include_agent_sessions:
            try:
                agent_sessions = client.get_agent_sessions(from_ms, to_ms)
            except Exception as exc:
                agent_sessions = []
                agent_session_error = str(exc)

        for item in tasks:
            queue = item.get("lastQueue") or {}
            cb = item.get("callbackData") or {}

            db.add(RawWxccRecord(
                record_type="task",
                webex_id=item.get("id"),
                source_from=from_ms,
                source_to=to_ms,
                payload=item,
            ))

            values = dict(
                task_id=item["id"],
                status=item.get("status"),
                channel_type=item.get("channelType"),
                created_time=item.get("createdTime"),
                ended_time=item.get("endedTime"),
                origin=item.get("origin"),
                destination=item.get("destination"),
                direction=item.get("direction"),
                termination_type=item.get("terminationType"),
                connected_count=item.get("connectedCount"),
                connected_duration=item.get("connectedDuration"),
                hold_count=item.get("holdCount"),
                hold_duration=item.get("holdDuration"),
                total_duration=item.get("totalDuration"),
                wrapup_code=item.get("lastWrapupCodeName"),
                queue_id=queue.get("id"),
                queue_name=queue.get("name"),
                queue_duration=queue.get("duration"),
                callback_request_time=cb.get("callbackRequestTime"),
                callback_connect_time=cb.get("callbackConnectTime"),
                callback_number=cb.get("callbackNumber"),
                callback_status=cb.get("callbackStatus"),
                callback_origin=cb.get("callbackOrigin"),
                callback_type=cb.get("callbackType"),
                callback_queue_name=cb.get("callbackQueueName"),
                callback_agent_name=cb.get("callbackAgentName"),
                callback_team_name=cb.get("callbackTeamName"),
                callback_retry_count=cb.get("callbackRetryCount"),
                raw_payload=item,
            )
            _upsert(db, Interaction, "task_id", item["id"], values)

        for item in details:
            agent = item.get("lastAgent") or {}

            db.add(RawWxccRecord(
                record_type="taskDetails",
                webex_id=item.get("id"),
                source_from=from_ms,
                source_to=to_ms,
                payload=item,
            ))

            values = dict(
                task_id=item["id"],
                agent_id=agent.get("id"),
                agent_name=agent.get("name"),
                sign_in_id=agent.get("signInId"),
                session_id=agent.get("sessionId"),
                raw_payload=item,
            )
            _upsert(db, InteractionAgent, "task_id", item["id"], values)

        for item in legs:
            queue = item.get("queue") or {}
            owner = item.get("owner") or {}

            db.add(RawWxccRecord(
                record_type="taskLegDetails",
                webex_id=item.get("id"),
                source_from=from_ms,
                source_to=to_ms,
                payload=item,
            ))

            values = dict(
                leg_id=item["id"],
                task_id=item.get("taskId"),
                status=item.get("status"),
                contact_state=item.get("contactState"),
                created_time=item.get("createdTime"),
                ended_time=item.get("endedTime"),
                origin=item.get("origin"),
                destination=item.get("destination"),
                channel_type=item.get("channelType"),
                queue_id=queue.get("id"),
                queue_name=queue.get("name"),
                queue_duration=queue.get("duration"),
                ringing_duration=item.get("ringingDuration"),
                agent_id=owner.get("id"),
                agent_name=owner.get("name"),
                sign_in_id=owner.get("signInId"),
                session_id=owner.get("sessionId"),
                connected_duration=item.get("connectedDuration"),
                hold_count=item.get("holdCount"),
                hold_duration=item.get("holdDuration"),
                wrapup_code=item.get("lastWrapupCodeName"),
                wrapup_duration=item.get("wrapupDuration"),
                raw_payload=item,
            )
            _upsert(db, InteractionLeg, "leg_id", item["id"], values)

        for session in agent_sessions:
            session_id = session.get("agentSessionId")
            if not session_id:
                continue

            telephony = next(
                (
                    c for c in (session.get("channelInfo") or [])
                    if (c.get("channelType") or "").lower() == "telephony"
                ),
                {},
            )

            db.add(RawWxccRecord(
                record_type="agentSession",
                webex_id=session_id,
                source_from=from_ms,
                source_to=to_ms,
                payload=session,
            ))

            session_values = dict(
                agent_session_id=session_id,
                agent_id=session.get("agentId"),
                agent_name=session.get("agentName"),
                team_name=session.get("teamName"),
                start_time=session.get("startTime"),
                end_time=session.get("endTime"),
                state=session.get("state"),
                total_duration=telephony.get("totalDuration"),
                connected_duration=telephony.get("connectedDuration"),
                raw_payload=session,
            )
            _upsert(
                db,
                AgentSession,
                "agent_session_id",
                session_id,
                session_values,
            )

            for channel in session.get("channelInfo") or []:
                activities = (
                    (channel.get("activities") or {}).get("nodes") or []
                )
                for activity in activities:
                    activity_id = activity.get("id")
                    if not activity_id:
                        continue

                    start = activity.get("startTime")
                    end = activity.get("endTime")
                    duration_ms = None
                    if (
                        isinstance(start, int)
                        and isinstance(end, int)
                        and end >= start
                        and end != -1
                    ):
                        duration_ms = end - start

                    raw_state = activity.get("state")
                    activity_lower = activity_id.lower()

                    state_detail = None
                    if raw_state == "idle" and "idle-rona" in activity_lower:
                        state_detail = "idle-rona"
                    elif raw_state == "not-responding":
                        state_detail = "rona"

                    activity_values = dict(
                        activity_id=activity_id,
                        agent_session_id=session_id,
                        agent_id=session.get("agentId"),
                        agent_name=session.get("agentName"),
                        team_name=session.get("teamName"),
                        channel_id=channel.get("channelId"),
                        channel_type=channel.get("channelType"),
                        state=raw_state,
                        state_detail=state_detail,
                        start_time=start,
                        end_time=end,
                        duration_ms=duration_ms,
                        raw_payload=activity,
                    )
                    _upsert(
                        db,
                        AgentStateActivity,
                        "activity_id",
                        activity_id,
                        activity_values,
                    )

        run.finished_at = datetime.now(timezone.utc)
        run.success = True
        run.task_count = len(tasks)
        run.detail_count = len(details)
        run.leg_count = len(legs)
        db.commit()

        return {
            "success": True,
            "from": from_ms,
            "to": to_ms,
            "tasks": len(tasks),
            "task_details": len(details),
            "task_legs": len(legs),
            "agent_sessions": len(agent_sessions),
            "agent_sessions_requested": include_agent_sessions,
            "agent_session_error": agent_session_error,
        }

    except Exception as exc:
        db.rollback()
        run = db.get(CollectorRun, run.id)
        if run is not None:
            run.finished_at = datetime.now(timezone.utc)
            run.success = False
            run.error = str(exc)
            db.commit()
        raise
