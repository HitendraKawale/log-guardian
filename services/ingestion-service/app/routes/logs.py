"""Log ingestion and retrieval endpoints."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..ai_client import AIClient, get_ai_client
from ..config import settings
from ..database import get_session
from ..models import Log
from ..producer import publish_log
from ..schemas import FeedbackCreate, LogCreate, LogLevel, LogResponse
from ..security import require_api_key
from ..service import FEEDBACK_DISAGREE, FEEDBACK_TOTAL, persist_log

# The whole router is gated by the API key (a no-op when none is configured).
router = APIRouter(prefix="/logs", tags=["Logs"], dependencies=[Depends(require_api_key)])


@router.post("", response_model=LogResponse, status_code=status.HTTP_201_CREATED)
async def ingest_log(
    log: LogCreate,
    session: AsyncSession = Depends(get_session),
    ai: AIClient = Depends(get_ai_client),
) -> Log:
    return await persist_log(session, log, ai)


@router.post("/stream", status_code=status.HTTP_202_ACCEPTED)
async def stream_log(log: LogCreate) -> dict[str, str]:
    """Publish a log to Kafka for asynchronous scoring by the consumer worker."""
    if not settings.kafka_enabled:
        raise HTTPException(status_code=503, detail="Streaming is disabled")
    await publish_log(log)
    return {"status": "queued"}


@router.get("", response_model=list[LogResponse])
async def list_logs(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    service: str | None = Query(None),
    level: LogLevel | None = Query(None),
    anomalous: bool | None = Query(None),
    session: AsyncSession = Depends(get_session),
) -> list[Log]:
    stmt = select(Log)
    if service:
        stmt = stmt.where(Log.service == service)
    if level:
        stmt = stmt.where(Log.level == level.value)
    if anomalous is not None:
        stmt = stmt.where(Log.is_anomaly.is_(anomalous))
    stmt = stmt.order_by(Log.id.desc()).limit(limit).offset(offset)
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.get("/{log_id}", response_model=LogResponse)
async def get_log(
    log_id: int,
    session: AsyncSession = Depends(get_session),
) -> Log:
    record = await session.get(Log, log_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Log not found")
    return record


@router.post("/{log_id}/feedback", response_model=LogResponse)
async def submit_feedback(
    log_id: int,
    feedback: FeedbackCreate,
    session: AsyncSession = Depends(get_session),
) -> Log:
    """Attach a human ground-truth label to a log (used for retraining)."""
    record = await session.get(Log, log_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Log not found")

    disagrees = record.is_anomaly is not None and record.is_anomaly != feedback.is_anomaly
    record.true_label = feedback.is_anomaly
    record.feedback_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(record)

    FEEDBACK_TOTAL.inc()
    if disagrees:
        FEEDBACK_DISAGREE.inc()
    return record
