"""Log ingestion and retrieval endpoints."""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from prometheus_client import Counter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..ai_client import AIClient, get_ai_client
from ..database import get_session
from ..models import Log
from ..schemas import LogCreate, LogResponse

router = APIRouter(prefix="/logs", tags=["Logs"])

LOGS_INGESTED = Counter("ingestion_logs_total", "Total number of logs ingested")
LOGS_ANOMALOUS = Counter(
    "ingestion_anomalous_logs_total", "Total number of logs flagged as anomalies"
)


@router.post("", response_model=LogResponse, status_code=status.HTTP_201_CREATED)
async def ingest_log(
    log: LogCreate,
    session: AsyncSession = Depends(get_session),
    ai: AIClient = Depends(get_ai_client),
) -> Log:
    result = await ai.analyze(log)

    record = Log(
        service=log.service,
        level=log.level.value,
        message=log.message,
        timestamp=log.timestamp,
        status="scored" if result else "unscored",
        anomaly_score=result.anomaly_score if result else None,
        is_anomaly=result.is_anomaly if result else None,
        predicted_severity=result.predicted_severity.value if result else None,
    )
    session.add(record)
    await session.commit()
    await session.refresh(record)

    LOGS_INGESTED.inc()
    if result and result.is_anomaly:
        LOGS_ANOMALOUS.inc()

    return record


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
