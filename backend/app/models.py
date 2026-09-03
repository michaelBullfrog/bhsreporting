from datetime import datetime
from sqlalchemy import String, BigInteger, Integer, Boolean, DateTime, Text, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base

class RawWxccRecord(Base):
    __tablename__ = "raw_wxcc_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    record_type: Mapped[str] = mapped_column(String(50), index=True)
    webex_id: Mapped[str | None] = mapped_column(String(255), index=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    source_from: Mapped[int] = mapped_column(BigInteger)
    source_to: Mapped[int] = mapped_column(BigInteger)
    payload: Mapped[dict] = mapped_column(JSONB)

class Interaction(Base):
    __tablename__ = "interactions"

    task_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    status: Mapped[str | None] = mapped_column(String(100))
    channel_type: Mapped[str | None] = mapped_column(String(50))
    created_time: Mapped[int | None] = mapped_column(BigInteger, index=True)
    ended_time: Mapped[int | None] = mapped_column(BigInteger, index=True)

    origin: Mapped[str | None] = mapped_column(String(100), index=True)
    destination: Mapped[str | None] = mapped_column(String(100), index=True)
    direction: Mapped[str | None] = mapped_column(String(50), index=True)
    termination_type: Mapped[str | None] = mapped_column(String(100), index=True)

    connected_count: Mapped[int | None] = mapped_column(Integer)
    connected_duration: Mapped[int | None] = mapped_column(BigInteger)
    hold_count: Mapped[int | None] = mapped_column(Integer)
    hold_duration: Mapped[int | None] = mapped_column(BigInteger)
    total_duration: Mapped[int | None] = mapped_column(BigInteger)

    wrapup_code: Mapped[str | None] = mapped_column(String(255))

    queue_id: Mapped[str | None] = mapped_column(String(255), index=True)
    queue_name: Mapped[str | None] = mapped_column(String(255), index=True)
    queue_duration: Mapped[int | None] = mapped_column(BigInteger)

    callback_request_time: Mapped[int | None] = mapped_column(BigInteger)
    callback_connect_time: Mapped[int | None] = mapped_column(BigInteger)
    callback_number: Mapped[str | None] = mapped_column(String(100))
    callback_status: Mapped[str | None] = mapped_column(String(100), index=True)
    callback_origin: Mapped[str | None] = mapped_column(String(100))
    callback_type: Mapped[str | None] = mapped_column(String(100))
    callback_queue_name: Mapped[str | None] = mapped_column(String(255))
    callback_agent_name: Mapped[str | None] = mapped_column(String(255))
    callback_team_name: Mapped[str | None] = mapped_column(String(255))
    callback_retry_count: Mapped[int | None] = mapped_column(Integer)

    raw_payload: Mapped[dict] = mapped_column(JSONB)

Index("ix_interactions_queue_created", Interaction.queue_name, Interaction.created_time)
Index("ix_interactions_direction_created", Interaction.direction, Interaction.created_time)

class InteractionAgent(Base):
    __tablename__ = "interaction_agents"

    task_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    agent_id: Mapped[str | None] = mapped_column(String(255), index=True)
    agent_name: Mapped[str | None] = mapped_column(String(255), index=True)
    sign_in_id: Mapped[str | None] = mapped_column(String(255), index=True)
    session_id: Mapped[str | None] = mapped_column(String(255), index=True)
    raw_payload: Mapped[dict] = mapped_column(JSONB)

class InteractionLeg(Base):
    __tablename__ = "interaction_legs"

    leg_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    task_id: Mapped[str] = mapped_column(String(255), index=True)

    status: Mapped[str | None] = mapped_column(String(100), index=True)
    contact_state: Mapped[str | None] = mapped_column(String(100), index=True)
    created_time: Mapped[int | None] = mapped_column(BigInteger, index=True)
    ended_time: Mapped[int | None] = mapped_column(BigInteger)

    origin: Mapped[str | None] = mapped_column(String(100))
    destination: Mapped[str | None] = mapped_column(String(100))
    channel_type: Mapped[str | None] = mapped_column(String(50))

    queue_id: Mapped[str | None] = mapped_column(String(255), index=True)
    queue_name: Mapped[str | None] = mapped_column(String(255), index=True)
    queue_duration: Mapped[int | None] = mapped_column(BigInteger)

    ringing_duration: Mapped[int | None] = mapped_column(BigInteger)

    agent_id: Mapped[str | None] = mapped_column(String(255), index=True)
    agent_name: Mapped[str | None] = mapped_column(String(255), index=True)
    sign_in_id: Mapped[str | None] = mapped_column(String(255), index=True)
    session_id: Mapped[str | None] = mapped_column(String(255), index=True)

    connected_duration: Mapped[int | None] = mapped_column(BigInteger)
    hold_count: Mapped[int | None] = mapped_column(Integer)
    hold_duration: Mapped[int | None] = mapped_column(BigInteger)
    wrapup_code: Mapped[str | None] = mapped_column(String(255))
    wrapup_duration: Mapped[int | None] = mapped_column(BigInteger)

    raw_payload: Mapped[dict] = mapped_column(JSONB)

Index("ix_legs_task_agent", InteractionLeg.task_id, InteractionLeg.agent_id)
Index("ix_legs_queue_created", InteractionLeg.queue_name, InteractionLeg.created_time)

class CollectorRun(Base):
    __tablename__ = "collector_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    from_ms: Mapped[int] = mapped_column(BigInteger)
    to_ms: Mapped[int] = mapped_column(BigInteger)
    success: Mapped[bool] = mapped_column(Boolean, default=False)
    task_count: Mapped[int] = mapped_column(Integer, default=0)
    detail_count: Mapped[int] = mapped_column(Integer, default=0)
    leg_count: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)

class AgentSession(Base):
    __tablename__ = "agent_sessions"

    agent_session_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    agent_id: Mapped[str | None] = mapped_column(String(255), index=True)
    agent_name: Mapped[str | None] = mapped_column(String(255), index=True)
    team_name: Mapped[str | None] = mapped_column(String(255), index=True)
    start_time: Mapped[int | None] = mapped_column(BigInteger, index=True)
    end_time: Mapped[int | None] = mapped_column(BigInteger, index=True)
    state: Mapped[str | None] = mapped_column(String(100), index=True)
    total_duration: Mapped[int | None] = mapped_column(BigInteger)
    connected_duration: Mapped[int | None] = mapped_column(BigInteger)
    raw_payload: Mapped[dict] = mapped_column(JSONB)

Index("ix_agent_sessions_agent_start", AgentSession.agent_id, AgentSession.start_time)
Index("ix_agent_sessions_team_start", AgentSession.team_name, AgentSession.start_time)

class AgentStateActivity(Base):
    __tablename__ = "agent_state_activities"

    activity_id: Mapped[str] = mapped_column(String(512), primary_key=True)
    agent_session_id: Mapped[str] = mapped_column(String(255), index=True)
    agent_id: Mapped[str | None] = mapped_column(String(255), index=True)
    agent_name: Mapped[str | None] = mapped_column(String(255), index=True)
    team_name: Mapped[str | None] = mapped_column(String(255), index=True)
    channel_id: Mapped[str | None] = mapped_column(String(255), index=True)
    channel_type: Mapped[str | None] = mapped_column(String(50), index=True)
    state: Mapped[str | None] = mapped_column(String(100), index=True)
    state_detail: Mapped[str | None] = mapped_column(String(100), index=True)
    start_time: Mapped[int | None] = mapped_column(BigInteger, index=True)
    end_time: Mapped[int | None] = mapped_column(BigInteger, index=True)
    duration_ms: Mapped[int | None] = mapped_column(BigInteger)
    raw_payload: Mapped[dict] = mapped_column(JSONB)

Index("ix_agent_state_agent_start", AgentStateActivity.agent_id, AgentStateActivity.start_time)
Index("ix_agent_state_team_start", AgentStateActivity.team_name, AgentStateActivity.start_time)
Index("ix_agent_state_state_start", AgentStateActivity.state, AgentStateActivity.start_time)


class CallingVoicemailEvent(Base):
    __tablename__ = "calling_voicemail_events"

    correlation_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    report_id: Mapped[str | None] = mapped_column(String(255), index=True)
    interaction_id: Mapped[str | None] = mapped_column(String(255), index=True)
    voicemail_group_uuid: Mapped[str | None] = mapped_column(String(255), index=True)
    voicemail_group_name: Mapped[str | None] = mapped_column(String(255), index=True)
    extension: Mapped[str | None] = mapped_column(String(50), index=True)
    caller_number: Mapped[str | None] = mapped_column(String(100), index=True)
    caller_name: Mapped[str | None] = mapped_column(String(255))
    location: Mapped[str | None] = mapped_column(String(255), index=True)
    start_time: Mapped[int | None] = mapped_column(BigInteger, index=True)
    answer_time: Mapped[int | None] = mapped_column(BigInteger)
    release_time: Mapped[int | None] = mapped_column(BigInteger, index=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    call_outcome: Mapped[str | None] = mapped_column(String(100), index=True)
    call_outcome_reason: Mapped[str | None] = mapped_column(String(255))
    answer_indicator: Mapped[str | None] = mapped_column(String(100))
    redirect_reason: Mapped[str | None] = mapped_column(String(100))
    redirecting_number: Mapped[str | None] = mapped_column(String(100))
    user_type: Mapped[str | None] = mapped_column(String(100), index=True)
    raw_payload: Mapped[dict] = mapped_column(JSONB)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

Index("ix_vm_group_start", CallingVoicemailEvent.voicemail_group_uuid, CallingVoicemailEvent.start_time)
Index("ix_vm_caller_start", CallingVoicemailEvent.caller_number, CallingVoicemailEvent.start_time)


class CallingOutboundCall(Base):
    __tablename__ = "calling_outbound_calls"

    report_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    correlation_id: Mapped[str | None] = mapped_column(String(255), index=True)
    interaction_id: Mapped[str | None] = mapped_column(String(255), index=True)
    user_uuid: Mapped[str | None] = mapped_column(String(255), index=True)
    user_name: Mapped[str | None] = mapped_column(String(255), index=True)
    user_type: Mapped[str | None] = mapped_column(String(100), index=True)
    called_number: Mapped[str | None] = mapped_column(String(100), index=True)
    calling_number: Mapped[str | None] = mapped_column(String(100))
    location: Mapped[str | None] = mapped_column(String(255), index=True)
    start_time: Mapped[int | None] = mapped_column(BigInteger, index=True)
    answer_time: Mapped[int | None] = mapped_column(BigInteger)
    release_time: Mapped[int | None] = mapped_column(BigInteger, index=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    answered: Mapped[bool | None] = mapped_column(Boolean)
    answer_indicator: Mapped[str | None] = mapped_column(String(100))
    call_outcome: Mapped[str | None] = mapped_column(String(100), index=True)
    call_outcome_reason: Mapped[str | None] = mapped_column(String(255))
    raw_payload: Mapped[dict] = mapped_column(JSONB)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

Index("ix_calling_outbound_called_start", CallingOutboundCall.called_number, CallingOutboundCall.start_time)
Index("ix_calling_outbound_user_start", CallingOutboundCall.user_uuid, CallingOutboundCall.start_time)
