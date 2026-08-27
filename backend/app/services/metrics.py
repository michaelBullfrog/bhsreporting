from sqlalchemy import func, case
from sqlalchemy.orm import Session
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from ..models import Interaction, InteractionLeg

def overview(db: Session, from_ms: int | None = None, to_ms: int | None = None):
    q = db.query(Interaction)
    if from_ms is not None:
        q = q.filter(Interaction.created_time >= from_ms)
    if to_ms is not None:
        q = q.filter(Interaction.created_time < to_ms)

    total = q.count()
    inbound = q.filter(Interaction.direction == "inbound").count()
    outbound = q.filter(Interaction.direction == "outdial").count()
    answered = q.filter(
        Interaction.direction == "inbound",
        Interaction.connected_count > 0,
    ).count()
    abandoned = q.filter(
        Interaction.direction == "inbound",
        Interaction.termination_type == "abandoned",
    ).count()
    callbacks = q.filter(Interaction.callback_status == "Success").count()

    avg_queue_ms = q.with_entities(func.avg(Interaction.queue_duration)).scalar() or 0
    max_queue_ms = q.with_entities(func.max(Interaction.queue_duration)).scalar() or 0

    return {
        "total_interactions": total,
        "inbound": inbound,
        "outdial": outbound,
        "answered": answered,
        "abandoned": abandoned,
        "successful_native_callbacks": callbacks,
        "answer_rate": round(answered / inbound * 100, 2) if inbound else 0,
        "abandon_rate": round(abandoned / inbound * 100, 2) if inbound else 0,
        "avg_queue_seconds": round(float(avg_queue_ms) / 1000, 2),
        "max_queue_seconds": round(float(max_queue_ms) / 1000, 2),
    }

def agent_summary(db: Session, from_ms: int | None = None, to_ms: int | None = None):
    q = db.query(
        InteractionLeg.agent_name,
        func.count(InteractionLeg.leg_id).label("legs"),
        func.sum(InteractionLeg.connected_duration).label("connected_ms"),
        func.sum(InteractionLeg.ringing_duration).label("ringing_ms"),
        func.sum(InteractionLeg.wrapup_duration).label("wrapup_ms"),
        func.sum(InteractionLeg.hold_duration).label("hold_ms"),
    ).filter(InteractionLeg.agent_name.isnot(None))

    if from_ms is not None:
        q = q.filter(InteractionLeg.created_time >= from_ms)
    if to_ms is not None:
        q = q.filter(InteractionLeg.created_time < to_ms)

    q = q.group_by(InteractionLeg.agent_name).order_by(func.sum(InteractionLeg.connected_duration).desc())

    rows = []
    for r in q.all():
        rows.append({
            "agent_name": r.agent_name,
            "legs": r.legs,
            "connected_seconds": round((r.connected_ms or 0) / 1000, 2),
            "ringing_seconds": round((r.ringing_ms or 0) / 1000, 2),
            "wrapup_seconds": round((r.wrapup_ms or 0) / 1000, 2),
            "hold_seconds": round((r.hold_ms or 0) / 1000, 2),
        })
    return rows



def _normalize_token(value: str | None) -> str:
    return "".join(ch for ch in str(value or "").lower() if ch.isalnum())


def _classify_nonqueued_interaction(row: Interaction, legs: list[InteractionLeg]) -> tuple[str, str]:
    """
    Classify inbound interactions that do not have a stored task-level queue.

    Classification intentionally uses only signals present in the collected
    WxCC task/task-leg data. Strong explicit outcomes win over inferred ones.
    """
    termination = (row.termination_type or "").strip()
    term_token = _normalize_token(termination)

    # Strongest explicit task-level outcome.
    if "transfertodn" in term_token:
        return (
            "Transferred to DN",
            "Task termination type indicates TransferToDN.",
        )

    # Native callback metadata is explicit and should be preserved before
    # generic answered/abandoned handling.
    callback_present = any([
        row.callback_status,
        row.callback_type,
        row.callback_request_time,
        row.callback_connect_time,
        row.callback_number,
    ])
    if callback_present:
        status = (row.callback_status or "callback metadata present").strip()
        return (
            "Callback",
            f"Native callback data present ({status}).",
        )

    # Connected without a task-level queue.
    if int(row.connected_count or 0) > 0:
        return (
            "Answered Without Queue",
            "Interaction connected even though no task-level queue was stored.",
        )

    # Explicit abandon.
    if term_token == "abandoned":
        return (
            "Abandoned Before Queue",
            "Task terminated as abandoned before a task-level queue was stored.",
        )

    # Preserve any other explicit termination value instead of inventing a
    # business meaning for it.
    if termination:
        return (
            f"Other: {termination}",
            f"Unmapped Webex termination type: {termination}.",
        )

    # If there is useful leg routing evidence, expose that without claiming a
    # stronger business outcome than the data supports.
    routed_legs = [
        leg for leg in legs
        if (leg.destination or "").strip()
    ]
    if routed_legs:
        return (
            "Non-Queue Leg Route",
            "Task has routed leg destination data but no mapped task termination or queue.",
        )

    return (
        "Unknown / No Outcome Signal",
        "No queue, connection, callback, termination type, or routed destination was available.",
    )

def call_demand_summary(
    db: Session,
    from_ms: int | None = None,
    to_ms: int | None = None,
    timezone_name: str = "America/Detroit",
):
    """
    Interaction-level Call Demand metrics.

    Core definitions:
      - Inbound: direction == "inbound"
      - Outbound: direction == "outdial"
      - Answered inbound: inbound interaction with connected_count > 0
      - Abandoned inbound: inbound interaction with termination_type == "abandoned"
      - Queue wait: Interaction.queue_duration
      - Queue/group: Interaction.queue_name (the task-level last/final queue)
      - Native callback success: callback_status == "Success"

    Notes:
      - Answer/abandon rates are intentionally inbound-only.
      - Queue breakdown is task-level and uses the stored final/last queue so
        one interaction is not double-counted across transfer legs.
      - Hour/day groupings use the requested reporting timezone.
    """
    try:
        tz = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        tz = ZoneInfo("America/Detroit")
        timezone_name = "America/Detroit"

    q = db.query(Interaction)

    if from_ms is not None:
        q = q.filter(Interaction.created_time >= from_ms)
    if to_ms is not None:
        q = q.filter(Interaction.created_time < to_ms)

    interactions = q.all()

    def is_inbound(row):
        return (row.direction or "").strip().lower() == "inbound"

    def is_outbound(row):
        return (row.direction or "").strip().lower() == "outdial"

    def is_answered(row):
        return is_inbound(row) and int(row.connected_count or 0) > 0

    def is_abandoned(row):
        return (
            is_inbound(row)
            and (row.termination_type or "").strip().lower() == "abandoned"
        )

    def queue_ms(row):
        value = row.queue_duration
        return int(value) if isinstance(value, int) and value >= 0 else 0

    inbound_rows = [row for row in interactions if is_inbound(row)]
    outbound_rows = [row for row in interactions if is_outbound(row)]
    answered_rows = [row for row in inbound_rows if is_answered(row)]
    abandoned_rows = [row for row in inbound_rows if is_abandoned(row)]

    inbound = len(inbound_rows)
    outbound = len(outbound_rows)
    answered = len(answered_rows)
    abandoned = len(abandoned_rows)

    queued_inbound_rows = [
        row for row in inbound_rows
        if row.queue_name and str(row.queue_name).strip()
    ]
    queued_inbound = len(queued_inbound_rows)
    queued_answered = sum(1 for row in queued_inbound_rows if is_answered(row))
    queued_abandoned = sum(1 for row in queued_inbound_rows if is_abandoned(row))
    nonqueued_rows = [
        row for row in inbound_rows
        if not (row.queue_name and str(row.queue_name).strip())
    ]
    no_queue_inbound = len(nonqueued_rows)

    nonqueued_task_ids = [row.task_id for row in nonqueued_rows if row.task_id]
    legs_by_task: dict[str, list[InteractionLeg]] = {}
    if nonqueued_task_ids:
        leg_rows = (
            db.query(InteractionLeg)
            .filter(InteractionLeg.task_id.in_(nonqueued_task_ids))
            .all()
        )
        for leg in leg_rows:
            legs_by_task.setdefault(leg.task_id, []).append(leg)

    nonqueued_buckets: dict[str, dict] = {}
    nonqueued_details = []

    for row in nonqueued_rows:
        task_legs = legs_by_task.get(row.task_id, [])
        category, reason = _classify_nonqueued_interaction(row, task_legs)

        bucket = nonqueued_buckets.setdefault(
            category,
            {
                "category": category,
                "count": 0,
                "termination_types": set(),
                "destination_samples": [],
            },
        )
        bucket["count"] += 1

        if row.termination_type:
            bucket["termination_types"].add(row.termination_type)

        destinations = []
        if row.destination:
            destinations.append(row.destination)
        destinations.extend(
            leg.destination
            for leg in task_legs
            if leg.destination
        )
        for destination in destinations:
            if destination not in bucket["destination_samples"]:
                bucket["destination_samples"].append(destination)
            if len(bucket["destination_samples"]) >= 5:
                break

        nonqueued_details.append({
            "task_id": row.task_id,
            "category": category,
            "reason": reason,
            "termination_type": row.termination_type,
            "connected_count": int(row.connected_count or 0),
            "callback_status": row.callback_status,
            "origin": row.origin,
            "destination": row.destination,
            "leg_destinations": list(dict.fromkeys(
                leg.destination for leg in task_legs if leg.destination
            )),
        })

    nonqueued_breakdown = []
    for bucket in nonqueued_buckets.values():
        nonqueued_breakdown.append({
            "category": bucket["category"],
            "count": bucket["count"],
            "percent": (
                round(bucket["count"] / no_queue_inbound * 100, 2)
                if no_queue_inbound else 0
            ),
            "termination_types": sorted(bucket["termination_types"]),
            "destination_samples": bucket["destination_samples"],
        })

    nonqueued_breakdown.sort(
        key=lambda item: (item["count"], item["category"]),
        reverse=True,
    )

    inbound_queue_values = [
        queue_ms(row)
        for row in inbound_rows
        if row.queue_duration is not None and int(row.queue_duration or 0) >= 0
    ]
    queued_wait_values = [
        queue_ms(row)
        for row in queued_inbound_rows
        if row.queue_duration is not None and int(row.queue_duration or 0) >= 0
    ]

    avg_queue_ms = (
        sum(inbound_queue_values) / len(inbound_queue_values)
        if inbound_queue_values else 0
    )
    max_queue_ms = max(inbound_queue_values) if inbound_queue_values else 0

    avg_queued_wait_ms = (
        sum(queued_wait_values) / len(queued_wait_values)
        if queued_wait_values else 0
    )
    max_queued_wait_ms = max(queued_wait_values) if queued_wait_values else 0

    successful_native_callbacks = sum(
        1 for row in interactions
        if (row.callback_status or "").strip().lower() == "success"
    )

    # Queue/group breakdown. We use Interaction.queue_name rather than legs so
    # each interaction appears once, avoiding transfer-leg double counting.
    queue_buckets: dict[str, dict] = {}

    for row in inbound_rows:
        queue_name = (row.queue_name or "Unassigned / No Queue").strip()
        bucket = queue_buckets.setdefault(
            queue_name,
            {
                "queue_name": queue_name,
                "offered": 0,
                "answered": 0,
                "abandoned": 0,
                "queue_wait_total_ms": 0,
                "queue_wait_samples": 0,
                "max_queue_wait_ms": 0,
            },
        )

        bucket["offered"] += 1

        if is_answered(row):
            bucket["answered"] += 1
        if is_abandoned(row):
            bucket["abandoned"] += 1

        if row.queue_duration is not None:
            wait = queue_ms(row)
            bucket["queue_wait_total_ms"] += wait
            bucket["queue_wait_samples"] += 1
            bucket["max_queue_wait_ms"] = max(
                bucket["max_queue_wait_ms"],
                wait,
            )

    queues = []

    for bucket in queue_buckets.values():
        offered = bucket["offered"]
        samples = bucket["queue_wait_samples"]

        queues.append({
            "queue_name": bucket["queue_name"],
            "offered": offered,
            "answered": bucket["answered"],
            "abandoned": bucket["abandoned"],
            "answer_rate": (
                round(bucket["answered"] / offered * 100, 2)
                if offered else 0
            ),
            "abandon_rate": (
                round(bucket["abandoned"] / offered * 100, 2)
                if offered else 0
            ),
            "avg_queue_seconds": (
                round(
                    bucket["queue_wait_total_ms"] / samples / 1000,
                    2,
                )
                if samples else 0
            ),
            "max_queue_seconds": round(
                bucket["max_queue_wait_ms"] / 1000,
                2,
            ),
        })

    queues.sort(
        key=lambda row: (row["offered"], row["queue_name"]),
        reverse=True,
    )

    # Hour-of-day profile across the selected range.
    hourly_buckets = {
        hour: {
            "hour": hour,
            "label": datetime(2000, 1, 1, hour).strftime("%-I %p"),
            "inbound": 0,
            "answered": 0,
            "abandoned": 0,
            "outbound": 0,
        }
        for hour in range(24)
    }

    # Date profile for trend/chart use.
    daily_buckets: dict[str, dict] = {}

    for row in interactions:
        if row.created_time is None:
            continue

        dt = datetime.fromtimestamp(row.created_time / 1000, tz=tz)
        hour_bucket = hourly_buckets[dt.hour]

        date_key = dt.strftime("%Y-%m-%d")
        daily = daily_buckets.setdefault(
            date_key,
            {
                "date": date_key,
                "day_name": dt.strftime("%A"),
                "inbound": 0,
                "queued_inbound": 0,
                "answered": 0,
                "abandoned": 0,
                "queued_answered": 0,
                "queued_abandoned": 0,
                "outbound": 0,
            },
        )

        if is_inbound(row):
            hour_bucket["inbound"] += 1
            daily["inbound"] += 1

            queued = bool(row.queue_name and str(row.queue_name).strip())
            if queued:
                daily["queued_inbound"] += 1

            if is_answered(row):
                hour_bucket["answered"] += 1
                daily["answered"] += 1
                if queued:
                    daily["queued_answered"] += 1

            if is_abandoned(row):
                hour_bucket["abandoned"] += 1
                daily["abandoned"] += 1
                if queued:
                    daily["queued_abandoned"] += 1

        elif is_outbound(row):
            hour_bucket["outbound"] += 1
            daily["outbound"] += 1

    hourly = list(hourly_buckets.values())
    daily = [daily_buckets[key] for key in sorted(daily_buckets)]

    for row in daily:
        row["answer_rate"] = (
            round(row["answered"] / row["inbound"] * 100, 2)
            if row["inbound"] else 0
        )
        row["abandon_rate"] = (
            round(row["abandoned"] / row["inbound"] * 100, 2)
            if row["inbound"] else 0
        )
        row["queued_answer_rate"] = (
            round(row["queued_answered"] / row["queued_inbound"] * 100, 2)
            if row["queued_inbound"] else 0
        )
        row["queued_abandon_rate"] = (
            round(row["queued_abandoned"] / row["queued_inbound"] * 100, 2)
            if row["queued_inbound"] else 0
        )

    peak_hour = max(
        hourly,
        key=lambda row: row["inbound"],
        default=None,
    )
    peak_day = max(
        daily,
        key=lambda row: row["inbound"],
        default=None,
    )

    direction_total = inbound + outbound

    return {
        "timezone": timezone_name,
        "definitions": {
            "answered": "Inbound interaction with connected_count > 0",
            "abandoned": "Inbound interaction with termination_type == abandoned",
            "queue_wait": "Interaction.queue_duration",
            "queue_grouping": "Interaction.queue_name (task-level final/last queue)",
        },
        "overview": {
            "total_interactions": len(interactions),
            "inbound": inbound,
            "outbound": outbound,
            "queued_inbound": queued_inbound,
            "no_queue_inbound": no_queue_inbound,
            "answered": answered,
            "abandoned": abandoned,
            "queued_answered": queued_answered,
            "queued_abandoned": queued_abandoned,
            "successful_native_callbacks": successful_native_callbacks,
            "answer_rate": (
                round(answered / inbound * 100, 2)
                if inbound else 0
            ),
            "abandon_rate": (
                round(abandoned / inbound * 100, 2)
                if inbound else 0
            ),
            "queued_answer_rate": (
                round(queued_answered / queued_inbound * 100, 2)
                if queued_inbound else 0
            ),
            "queued_abandon_rate": (
                round(queued_abandoned / queued_inbound * 100, 2)
                if queued_inbound else 0
            ),
            "avg_queue_seconds": round(avg_queue_ms / 1000, 2),
            "max_queue_seconds": round(max_queue_ms / 1000, 2),
            "avg_queued_wait_seconds": round(avg_queued_wait_ms / 1000, 2),
            "max_queued_wait_seconds": round(max_queued_wait_ms / 1000, 2),
            "inbound_percent": (
                round(inbound / direction_total * 100, 2)
                if direction_total else 0
            ),
            "outbound_percent": (
                round(outbound / direction_total * 100, 2)
                if direction_total else 0
            ),
            "inbound_outbound_ratio": (
                round(inbound / outbound, 2)
                if outbound else None
            ),
            "peak_hour": (
                {
                    "hour": peak_hour["hour"],
                    "label": peak_hour["label"],
                    "inbound": peak_hour["inbound"],
                }
                if peak_hour else None
            ),
            "peak_day": (
                {
                    "date": peak_day["date"],
                    "day_name": peak_day["day_name"],
                    "inbound": peak_day["inbound"],
                }
                if peak_day else None
            ),
        },
        "queues": queues,
        "nonqueued": {
            "total": no_queue_inbound,
            "breakdown": nonqueued_breakdown,
            "details": nonqueued_details,
        },
        "hourly": hourly,
        "daily": daily,
    }


def service_sla_summary(
    db: Session,
    from_ms: int | None = None,
    to_ms: int | None = None,
    sla_seconds: int = 15,
    long_wait_seconds: int = 300,
    short_abandon_seconds: int = 0,
    timezone_name: str = "America/Detroit",
):
    """
    Queue-focused service/SLA reporting.

    Eligibility:
      - inbound interactions only
      - a stored task-level queue name is required

    Important:
      Webex/customer SLA policy can differ by tenant. This function exposes
      transparent counts and multiple rates rather than pretending one formula
      universally matches Control Hub/Analyzer configuration.

    Default thresholds:
      - SLA target: 15 seconds
      - long wait: 300 seconds / 5 minutes
      - short abandon exclusion: disabled (0 seconds)
    """
    try:
        tz = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        tz = ZoneInfo("America/Detroit")
        timezone_name = "America/Detroit"

    sla_ms = max(0, int(sla_seconds)) * 1000
    long_wait_ms = max(0, int(long_wait_seconds)) * 1000
    short_abandon_ms = max(0, int(short_abandon_seconds)) * 1000

    q = db.query(Interaction).filter(
        Interaction.direction == "inbound",
        Interaction.queue_name.isnot(None),
        Interaction.queue_name != "",
    )
    if from_ms is not None:
        q = q.filter(Interaction.created_time >= from_ms)
    if to_ms is not None:
        q = q.filter(Interaction.created_time < to_ms)

    rows = q.all()

    def wait_ms(row):
        value = row.queue_duration
        if isinstance(value, int) and value >= 0:
            return value
        try:
            value = int(value or 0)
            return value if value >= 0 else 0
        except (TypeError, ValueError):
            return 0

    def answered(row):
        return int(row.connected_count or 0) > 0

    def abandoned(row):
        return (row.termination_type or "").strip().lower() == "abandoned"

    def make_bucket(name):
        return {
            "queue_name": name,
            "queued_inbound": 0,
            "answered": 0,
            "abandoned": 0,
            "answered_within_sla": 0,
            "answered_over_sla": 0,
            "abandoned_within_sla": 0,
            "abandoned_over_sla": 0,
            "short_abandons": 0,
            "long_wait_breaches": 0,
            "wait_total_ms": 0,
            "wait_samples": 0,
            "max_wait_ms": 0,
        }

    total = make_bucket("All Queues")
    queue_buckets = {}

    hourly = {
        hour: {
            "hour": hour,
            "label": datetime(2000, 1, 1, hour).strftime("%-I %p"),
            "queued_inbound": 0,
            "answered": 0,
            "abandoned": 0,
            "answered_within_sla": 0,
            "long_wait_breaches": 0,
        }
        for hour in range(24)
    }

    def apply(bucket, row):
        wait = wait_ms(row)
        is_answered = answered(row)
        is_abandoned = abandoned(row)

        bucket["queued_inbound"] += 1
        bucket["wait_total_ms"] += wait
        bucket["wait_samples"] += 1
        bucket["max_wait_ms"] = max(bucket["max_wait_ms"], wait)

        if wait > long_wait_ms:
            bucket["long_wait_breaches"] += 1

        if is_answered:
            bucket["answered"] += 1
            if wait <= sla_ms:
                bucket["answered_within_sla"] += 1
            else:
                bucket["answered_over_sla"] += 1

        if is_abandoned:
            bucket["abandoned"] += 1
            if wait <= sla_ms:
                bucket["abandoned_within_sla"] += 1
            else:
                bucket["abandoned_over_sla"] += 1
            if short_abandon_ms > 0 and wait <= short_abandon_ms:
                bucket["short_abandons"] += 1

    for row in rows:
        queue_name = (row.queue_name or "Unknown Queue").strip()
        bucket = queue_buckets.setdefault(queue_name, make_bucket(queue_name))
        apply(total, row)
        apply(bucket, row)

        if row.created_time is not None:
            dt = datetime.fromtimestamp(row.created_time / 1000, tz=tz)
            hb = hourly[dt.hour]
            hb["queued_inbound"] += 1
            if answered(row):
                hb["answered"] += 1
                if wait_ms(row) <= sla_ms:
                    hb["answered_within_sla"] += 1
            if abandoned(row):
                hb["abandoned"] += 1
            if wait_ms(row) > long_wait_ms:
                hb["long_wait_breaches"] += 1

    def finalize(bucket):
        queued = bucket["queued_inbound"]
        ans = bucket["answered"]
        aband = bucket["abandoned"]

        adjusted_denominator = queued
        if short_abandon_ms > 0:
            adjusted_denominator = max(0, queued - bucket["short_abandons"])

        return {
            "queue_name": bucket["queue_name"],
            "queued_inbound": queued,
            "answered": ans,
            "abandoned": aband,
            "answer_rate": round(ans / queued * 100, 2) if queued else 0,
            "abandon_rate": round(aband / queued * 100, 2) if queued else 0,
            "answered_within_sla": bucket["answered_within_sla"],
            "answered_over_sla": bucket["answered_over_sla"],
            "abandoned_within_sla": bucket["abandoned_within_sla"],
            "abandoned_over_sla": bucket["abandoned_over_sla"],
            "short_abandons": bucket["short_abandons"],
            # Strict queue SLA: answered within target divided by all queued.
            "strict_sla_percent": (
                round(bucket["answered_within_sla"] / queued * 100, 2)
                if queued else 0
            ),
            # Answered-only speed measure: of calls that were answered, how many
            # were answered within the target?
            "answered_within_sla_percent": (
                round(bucket["answered_within_sla"] / ans * 100, 2)
                if ans else 0
            ),
            # Optional adjusted SLA, excluding configured short abandons.
            "adjusted_sla_percent": (
                round(bucket["answered_within_sla"] / adjusted_denominator * 100, 2)
                if adjusted_denominator else 0
            ),
            "long_wait_breaches": bucket["long_wait_breaches"],
            "long_wait_breach_percent": (
                round(bucket["long_wait_breaches"] / queued * 100, 2)
                if queued else 0
            ),
            "avg_wait_seconds": (
                round(bucket["wait_total_ms"] / bucket["wait_samples"] / 1000, 2)
                if bucket["wait_samples"] else 0
            ),
            "max_wait_seconds": round(bucket["max_wait_ms"] / 1000, 2),
        }

    overview = finalize(total)
    queues = [finalize(bucket) for bucket in queue_buckets.values()]
    queues.sort(
        key=lambda item: (
            item["strict_sla_percent"],
            -item["abandon_rate"],
            -item["queued_inbound"],
        )
    )

    hourly_rows = []
    for hour in range(24):
        row = hourly[hour]
        queued = row["queued_inbound"]
        ans = row["answered"]
        hourly_rows.append({
            **row,
            "strict_sla_percent": (
                round(row["answered_within_sla"] / queued * 100, 2)
                if queued else 0
            ),
            "answered_within_sla_percent": (
                round(row["answered_within_sla"] / ans * 100, 2)
                if ans else 0
            ),
            "abandon_rate": (
                round(row["abandoned"] / queued * 100, 2)
                if queued else 0
            ),
            "long_wait_breach_percent": (
                round(row["long_wait_breaches"] / queued * 100, 2)
                if queued else 0
            ),
        })

    worst_sla_queue = min(
        queues,
        key=lambda item: item["strict_sla_percent"],
        default=None,
    )
    highest_abandon_queue = max(
        queues,
        key=lambda item: item["abandon_rate"],
        default=None,
    )
    longest_wait_queue = max(
        queues,
        key=lambda item: item["max_wait_seconds"],
        default=None,
    )

    return {
        "timezone": timezone_name,
        "thresholds": {
            "sla_seconds": int(sla_seconds),
            "long_wait_seconds": int(long_wait_seconds),
            "short_abandon_seconds": int(short_abandon_seconds),
        },
        "definitions": {
            "eligible": "Inbound interaction with a stored task-level queue name",
            "strict_sla": "Answered within SLA threshold / all queued inbound",
            "answered_within_sla": "Answered within SLA threshold / answered queued inbound",
            "adjusted_sla": "Answered within SLA threshold / queued inbound excluding configured short abandons",
            "long_wait_breach": "Queue wait greater than the configured long-wait threshold",
        },
        "overview": {
            **overview,
            "worst_sla_queue": (
                {
                    "queue_name": worst_sla_queue["queue_name"],
                    "strict_sla_percent": worst_sla_queue["strict_sla_percent"],
                }
                if worst_sla_queue else None
            ),
            "highest_abandon_queue": (
                {
                    "queue_name": highest_abandon_queue["queue_name"],
                    "abandon_rate": highest_abandon_queue["abandon_rate"],
                }
                if highest_abandon_queue else None
            ),
            "longest_wait_queue": (
                {
                    "queue_name": longest_wait_queue["queue_name"],
                    "max_wait_seconds": longest_wait_queue["max_wait_seconds"],
                }
                if longest_wait_queue else None
            ),
        },
        "queues": queues,
        "hourly": hourly_rows,
    }

def staffing_summary(db: Session, from_ms: int | None = None, to_ms: int | None = None):
    """
    Agent staffing summary using stored WxCC agent sessions/state activities.

    Definitions:
      - Idle: explicit WxCC state == "idle".
      - RONA time: explicit WxCC state == "not-responding".
      - RONA events: count of explicit "not-responding" activity records.
      - Utilization: (connected + wrap-up) / logged-in time.
      - Occupancy: (connected + wrap-up) /
                   (available + connected + wrap-up).
      - Availability: available / logged-in time.

    Reporting-window behavior:
      - Without from_ms/to_ms, full stored interval durations are used.
      - With a reporting window, each session/activity contributes only the
        overlap between [start_time, end_time) and [from_ms, to_ms).
      - Records that merely overlap the requested window are included, even if
        they started before the window.
    """
    from ..models import AgentSession, AgentStateActivity

    def clipped_duration(start, end):
        if start is None or end is None or end < start:
            return 0

        clip_start = start
        clip_end = end

        if from_ms is not None:
            clip_start = max(clip_start, from_ms)
        if to_ms is not None:
            clip_end = min(clip_end, to_ms)

        return max(0, clip_end - clip_start)

    # Pull only intervals that can overlap the requested window.
    session_q = db.query(AgentSession)
    activity_q = db.query(AgentStateActivity)

    if to_ms is not None:
        session_q = session_q.filter(AgentSession.start_time < to_ms)
        activity_q = activity_q.filter(AgentStateActivity.start_time < to_ms)

    if from_ms is not None:
        session_q = session_q.filter(AgentSession.end_time > from_ms)
        activity_q = activity_q.filter(AgentStateActivity.end_time > from_ms)

    session_rows = session_q.all()
    activity_rows = activity_q.all()

    def empty_agent(agent_id=None, agent_name=None, team_name=None):
        return {
            "agent_id": agent_id,
            "agent_name": agent_name,
            "team_name": team_name,
            "logged_in_ms": 0,
            "available_ms": 0,
            "idle_ms": 0,
            "rona_ms": 0,
            "rona_events": 0,
            "connected_ms": 0,
            "wrapup_ms": 0,
            "ringing_ms": 0,
            "inbound_reserved_ms": 0,
            "outdial_reserved_ms": 0,
        }

    agents = {}

    for session in session_rows:
        key = (
            f"id:{session.agent_id.strip()}"
            if session.agent_id and session.agent_id.strip()
            else f"name:{(session.agent_name or 'unknown').strip().casefold()}"
        )
        row = agents.setdefault(
            key,
            empty_agent(session.agent_id, session.agent_name, session.team_name),
        )
        row["agent_name"] = row["agent_name"] or session.agent_name
        row["team_name"] = row["team_name"] or session.team_name
        row["logged_in_ms"] += clipped_duration(
            session.start_time,
            session.end_time,
        )

    for activity in activity_rows:
        key = (
            f"id:{activity.agent_id.strip()}"
            if activity.agent_id and activity.agent_id.strip()
            else f"name:{(activity.agent_name or 'unknown').strip().casefold()}"
        )
        row = agents.setdefault(
            key,
            empty_agent(activity.agent_id, activity.agent_name, activity.team_name),
        )

        row["agent_name"] = row["agent_name"] or activity.agent_name
        row["team_name"] = row["team_name"] or activity.team_name

        ms = clipped_duration(activity.start_time, activity.end_time)
        state = (activity.state or "").strip().lower()

        if state == "available":
            row["available_ms"] += ms
        elif state == "idle":
            row["idle_ms"] += ms
        elif state == "not-responding":
            row["rona_ms"] += ms
            # Count the event if its interval overlaps the reporting window.
            if ms > 0 or (
                activity.start_time is not None
                and activity.end_time is not None
                and activity.start_time == activity.end_time
                and (from_ms is None or activity.start_time >= from_ms)
                and (to_ms is None or activity.start_time < to_ms)
            ):
                row["rona_events"] += 1
        elif state == "connected":
            row["connected_ms"] += ms
        elif state in {"wrapup", "wrap-up"}:
            row["wrapup_ms"] += ms
        elif state == "ringing":
            row["ringing_ms"] += ms
        elif state == "inbound-reserved":
            row["inbound_reserved_ms"] += ms
        elif state == "outdial-reserved":
            row["outdial_reserved_ms"] += ms

    output = []

    for row in agents.values():
        logged = row["logged_in_ms"]
        productive = row["connected_ms"] + row["wrapup_ms"]

        occupancy_denominator = (
            row["available_ms"]
            + row["connected_ms"]
            + row["wrapup_ms"]
        )

        accounted_ms = (
            row["available_ms"]
            + row["idle_ms"]
            + row["rona_ms"]
            + row["connected_ms"]
            + row["wrapup_ms"]
            + row["ringing_ms"]
            + row["inbound_reserved_ms"]
            + row["outdial_reserved_ms"]
        )

        # Small overlaps between state transitions can make accounted slightly
        # exceed logged-in duration, so expose both values but only count a
        # positive gap as unaccounted time.
        unaccounted_ms = max(logged - accounted_ms, 0)

        row.update({
            "accounted_ms": accounted_ms,
            "unaccounted_ms": unaccounted_ms,
            "accounted_percent": (
                round(accounted_ms / logged * 100, 2)
                if logged else 0
            ),
            "staffing_data_complete": (
                (accounted_ms / logged) >= 0.99
                if logged else False
            ),
            "logged_in_hours": round(logged / 3_600_000, 2),
            "available_hours": round(row["available_ms"] / 3_600_000, 2),
            "idle_hours": round(row["idle_ms"] / 3_600_000, 2),
            "rona_hours": round(row["rona_ms"] / 3_600_000, 2),
            "connected_hours": round(row["connected_ms"] / 3_600_000, 2),
            "wrapup_hours": round(row["wrapup_ms"] / 3_600_000, 2),
            "ringing_hours": round(row["ringing_ms"] / 3_600_000, 2),
            "utilization_percent": (
                round(productive / logged * 100, 2)
                if logged else 0
            ),
            "occupancy_percent": (
                round(productive / occupancy_denominator * 100, 2)
                if occupancy_denominator else 0
            ),
            "availability_percent": (
                round(row["available_ms"] / logged * 100, 2)
                if logged else 0
            ),
        })

        output.append(row)

    # Final safety pass: one response row per normalized agent identity.
    # This should normally be unnecessary because session/activity aggregation
    # already uses the same normalized key, but it prevents duplicate agent
    # rows if a future source record contains inconsistent whitespace/casing.
    deduped = {}

    for row in output:
        if row.get("agent_id"):
            dedupe_key = f"id:{str(row['agent_id']).strip()}"
        else:
            dedupe_key = (
                f"name:{str(row.get('agent_name') or 'unknown').strip().casefold()}"
            )

        existing = deduped.get(dedupe_key)
        if existing is None:
            deduped[dedupe_key] = row
            continue

        # Merge additive duration/count fields.
        for field in (
            "logged_in_ms",
            "available_ms",
            "idle_ms",
            "rona_ms",
            "rona_events",
            "connected_ms",
            "wrapup_ms",
            "ringing_ms",
            "inbound_reserved_ms",
            "outdial_reserved_ms",
        ):
            existing[field] = int(existing.get(field) or 0) + int(row.get(field) or 0)

        existing["agent_name"] = existing.get("agent_name") or row.get("agent_name")
        existing["team_name"] = existing.get("team_name") or row.get("team_name")

    final_output = []

    for row in deduped.values():
        logged = row["logged_in_ms"]
        productive = row["connected_ms"] + row["wrapup_ms"]
        occupancy_denominator = (
            row["available_ms"]
            + row["connected_ms"]
            + row["wrapup_ms"]
        )
        accounted_ms = (
            row["available_ms"]
            + row["idle_ms"]
            + row["rona_ms"]
            + row["connected_ms"]
            + row["wrapup_ms"]
            + row["ringing_ms"]
            + row["inbound_reserved_ms"]
            + row["outdial_reserved_ms"]
        )
        unaccounted_ms = max(logged - accounted_ms, 0)

        row.update({
            "accounted_ms": accounted_ms,
            "unaccounted_ms": unaccounted_ms,
            "accounted_percent": (
                round(accounted_ms / logged * 100, 2)
                if logged else 0
            ),
            "staffing_data_complete": (
                (accounted_ms / logged) >= 0.99
                if logged else False
            ),
            "logged_in_hours": round(logged / 3_600_000, 2),
            "available_hours": round(row["available_ms"] / 3_600_000, 2),
            "idle_hours": round(row["idle_ms"] / 3_600_000, 2),
            "rona_hours": round(row["rona_ms"] / 3_600_000, 2),
            "connected_hours": round(row["connected_ms"] / 3_600_000, 2),
            "wrapup_hours": round(row["wrapup_ms"] / 3_600_000, 2),
            "ringing_hours": round(row["ringing_ms"] / 3_600_000, 2),
            "utilization_percent": (
                round(productive / logged * 100, 2)
                if logged else 0
            ),
            "occupancy_percent": (
                round(productive / occupancy_denominator * 100, 2)
                if occupancy_denominator else 0
            ),
            "availability_percent": (
                round(row["available_ms"] / logged * 100, 2)
                if logged else 0
            ),
        })
        final_output.append(row)

    final_output.sort(key=lambda x: x["logged_in_ms"], reverse=True)
    return final_output

