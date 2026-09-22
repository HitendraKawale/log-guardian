"""Shared ingestion commits logs before best-effort scoring-independent detection."""

import logging
from datetime import UTC

from prometheus_client import Counter

from .ai_client import AIClient
from .incident_detection import observe_log
from .models import Log
from .schemas import LogCreate

logger = logging.getLogger(__name__)

LOGS_INGESTED = Counter("ingestion_logs_total", "Total number of logs ingested")
LOGS_ANOMALOUS = Counter(
    "ingestion_anomalous_logs_total", "Total number of logs flagged as anomalies"
)
FEEDBACK_TOTAL = Counter("ingestion_feedback_total", "Total human feedback labels submitted")
FEEDBACK_DISAGREE = Counter(
    "ingestion_feedback_disagreements_total",
    "Feedback labels that disagreed with the model's prediction",
)
INVESTIGATION_CANDIDATES = Counter(
    "ingestion_investigation_candidates_total", "Logs selected as worth investigating", ["reason"]
)
DETECTOR_FAILURES = Counter(
    "ingestion_detector_failures_total", "Stored logs whose detector transaction failed"
)
DETECTOR_EXCLUDED = Counter(
    "ingestion_detector_excluded_total", "Stored logs excluded from detection by event timestamp"
)


async def persist_log(session, log: LogCreate, ai: AIClient) -> Log:
    """Store a scored or unscored log even when subsequent detection fails."""
    result = await ai.analyze(log)
    timestamp = log.timestamp.replace(tzinfo=log.timestamp.tzinfo or UTC).astimezone(UTC)
    record = Log(
        service=log.service,
        level=log.level.value,
        message=log.message,
        timestamp=timestamp,
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

    # Detection owns a separate transaction and a bounded deadline. It cannot
    # undo this committed record. Failure is visible but never retried here.
    try:
        transition = await observe_log(session, record)
        if transition.excluded:
            DETECTOR_EXCLUDED.inc()
        if transition.signal:
            for reason in transition.signal["reasons"]:
                INVESTIGATION_CANDIDATES.labels(reason=reason).inc()
    except Exception:
        DETECTOR_FAILURES.inc()
        logger.warning("incident detector failed; log stored anyway", exc_info=True)
    return record
