from sqlalchemy.ext.asyncio import async_sessionmaker

from app.ai_client import AIClient
from app.consumer import process_record
from app.schemas import AIResponse, Severity

RECORD = {
    "service": "gateway",
    "level": "ERROR",
    "message": "upstream service unreachable, request failed",
    "timestamp": "2026-06-18T10:00:00Z",
}


class _FakeAI(AIClient):
    def __init__(self, response):
        self._response = response

    async def analyze(self, log):
        return self._response


async def test_process_record_persists_scored_log(engine):
    factory = async_sessionmaker(engine, expire_on_commit=False)
    ai = _FakeAI(
        AIResponse(anomaly_score=0.91, is_anomaly=True, predicted_severity=Severity.HIGH)
    )
    async with factory() as session:
        record = await process_record(RECORD, session, ai)

    assert record.id >= 1
    assert record.status == "scored"
    assert record.is_anomaly is True
    assert record.predicted_severity == "high"


async def test_process_record_without_ai(engine):
    factory = async_sessionmaker(engine, expire_on_commit=False)
    ai = _FakeAI(None)
    async with factory() as session:
        record = await process_record(RECORD, session, ai)

    assert record.status == "unscored"
    assert record.anomaly_score is None
