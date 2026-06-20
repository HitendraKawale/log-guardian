"""Log ingestion and retrieval endpoints."""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..ai_client import AIClient, get_ai_client
from ..config import settings
from ..database import get_session
from ..models import Log
from ..producer import publish_log
from ..schemas import LogCreate, LogResponse
from ..service import persist_log

router = APIRouter(prefix="/logs", tags=["Logs"])


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
    session: AsyncSession = Depends(get_session),
) -> list[Log]:
    stmt = select(Log).order_by(Log.id.desc()).limit(limit).offset(offset)
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
