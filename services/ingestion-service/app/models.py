"""Database models."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Log(Base):
    __tablename__ = "logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    service: Mapped[str] = mapped_column(String(128), index=True)
    level: Mapped[str] = mapped_column(String(16), index=True)
    message: Mapped[str] = mapped_column(String)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    # "scored" once the AI service has rated it, "unscored" if AI was unavailable.
    status: Mapped[str] = mapped_column(String(16), default="unscored")
    anomaly_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_anomaly: Mapped[bool | None] = mapped_column(nullable=True)
    predicted_severity: Mapped[str | None] = mapped_column(String(16), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    # Human-supplied ground truth, captured from the dashboard. Feeds retraining.
    true_label: Mapped[bool | None] = mapped_column(nullable=True)
    feedback_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


def _new_id() -> str:
    return str(uuid.uuid4())


class Investigation(Base):
    """A queued or executed investigation run. The HTTP process never runs the model;
    a separate worker claims queued rows and appends ordered events."""

    __tablename__ = "investigations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    question: Mapped[str] = mapped_column(String(2048))
    system: Mapped[str] = mapped_column(String(1))  # A, B or C
    scope: Mapped[dict] = mapped_column(JSON)  # validated InvestigationScope dump
    # queued -> running -> completed | failed | cancelled (terminal states are final)
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    error: Mapped[str | None] = mapped_column(String(64), nullable=True)
    report: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True, unique=True)
    request_sha256: Mapped[str] = mapped_column(String(64))
    model_requested: Mapped[str | None] = mapped_column(String(64), nullable=True)
    prompt_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    code_revision: Mapped[str | None] = mapped_column(String(64), nullable=True)
    usage: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    estimated_cost_usd: Mapped[str | None] = mapped_column(String(32), nullable=True)
    elapsed_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    worker_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class InvestigationEvent(Base):
    """Ordered per-run activity: tool calls, model requests, terminal transitions."""

    __tablename__ = "investigation_events"
    __table_args__ = (
        Index("ix_investigation_events_run_seq", "investigation_id", "sequence", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    investigation_id: Mapped[str] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE")
    )
    sequence: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(32))  # tool_call, model_request, status
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class InvestigationCandidate(Base):
    """A log the trigger selected as worth investigating.

    A candidate is a suggestion, never a commitment: nothing in this table
    spends money, and promoting one into an ``Investigation`` is a separate,
    key-gated, human action. Keeping the two tables apart is what stops log
    volume from driving paid execution.

    ``(service, template)`` is unique because the trigger's memory is
    per-process: a restart, or a second replica, re-fires a family the first
    one already surfaced. The constraint absorbs that, so a family yields one
    reviewable row however many workers see it.
    """

    __tablename__ = "investigation_candidates"
    __table_args__ = (
        Index("ix_candidates_service_template", "service", "template", unique=True),
        Index("ix_candidates_status_created", "status", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    service: Mapped[str] = mapped_column(String(128))
    level: Mapped[str] = mapped_column(String(16))
    message: Mapped[str] = mapped_column(String)
    template: Mapped[str] = mapped_column(String)
    reason: Mapped[str] = mapped_column(String(32))
    # Validated InvestigationScope dump, so a reviewer can act without
    # reconstructing the window the candidate refers to.
    scope: Mapped[dict] = mapped_column(JSON)
    # "new" -> "dismissed" | "promoted". Terminal states stay terminal.
    status: Mapped[str] = mapped_column(String(16), default="new")
    log_id: Mapped[int | None] = mapped_column(ForeignKey("logs.id", ondelete="SET NULL"))
    # Set when a human promotes this candidate into a paid run. The link is the
    # idempotency record: promoting twice returns the first investigation rather
    # than queueing a second one.
    investigation_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("investigations.id", ondelete="SET NULL"), nullable=True
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
