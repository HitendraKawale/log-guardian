"""Core log-handling logic shared by the REST route and the Kafka consumer.

Keeping the "score it, store it, count it" step in one place means the
synchronous API and the streaming worker behave identically.
"""

from prometheus_client import Counter

from .ai_client import AIClient
from .models import Log
from .schemas import LogCreate

LOGS_INGESTED = Counter("ingestion_logs_total", "Total number of logs ingested")
LOGS_ANOMALOUS = Counter(
    "ingestion_anomalous_logs_total", "Total number of logs flagged as anomalies"
)
FEEDBACK_TOTAL = Counter("ingestion_feedback_total", "Total human feedback labels submitted")
FEEDBACK_DISAGREE = Counter(
    "ingestion_feedback_disagreements_total",
    "Feedback labels that disagreed with the model's prediction",
)


async def persist_log(session, log: LogCreate, ai: AIClient) -> Log:
    """Score a log via the AI service (best-effort) and persist it."""
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
