from datetime import datetime, timezone
from sqlalchemy.orm import Session
from ..models import RawWxccRecord, Interaction, InteractionAgent, InteractionLeg, CollectorRun
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

def collect_window(db: Session, from_ms: int, to_ms: int) -> dict:
    run = CollectorRun(from_ms=from_ms, to_ms=to_ms)
    db.add(run)
    db.commit()
    db.refresh(run)

    client = WxccClient()

    try:
        tasks = client.get_tasks(from_ms, to_ms)
        details = client.get_task_details(from_ms, to_ms)
        legs = client.get_task_legs(from_ms, to_ms)

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
        }

    except Exception as exc:
        db.rollback()
        run = db.get(CollectorRun, run.id)
        run.finished_at = datetime.now(timezone.utc)
        run.success = False
        run.error = str(exc)
        db.commit()
        raise
