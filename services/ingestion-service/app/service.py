"""Core log-handling logic shared by the REST route and the Kafka consumer.

Keeping the "score it, store it, count it" step in one place means the
synchronous API and the streaming worker behave identically.
"""

import logging
from datetime import UTC

from prometheus_client import Counter
from sqlalchemy.exc import IntegrityError

from .ai_client import AIClient
from .config import settings
from .models import InvestigationCandidate, Log
from .schemas import LogCreate
from .trigger import InvestigationTrigger

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
    "ingestion_investigation_candidates_total",
    "Logs selected as worth investigating",
    ["reason"],
)

# Process-wide, because novelty is only meaningful against a history. Each
# replica therefore learns its own vocabulary and will flag a template the
# others have already seen -- acceptable while a candidate is a suggestion and
# not a spend, and the reason this is not a cross-replica rate limiter.
investigation_trigger = InvestigationTrigger(
    candidate_levels=settings.trigger_levels,
    warmup_logs=settings.trigger_warmup_logs,
)


async def persist_log(session, log: LogCreate, ai: AIClient) -> Log:
    """Score a log via the AI service (best-effort) and persist it."""
    result = await ai.analyze(log)

    # SQLite drops offsets on storage. Legacy naive inputs are interpreted as UTC.
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

    # Best-effort, exactly like the AI call: selecting a candidate must never
    # fail or delay a write. A lost candidate costs an investigation someone
    # might have run; a raised exception costs the log itself. The log is
    # committed above, so nothing below can roll it back.
    try:
        candidate = investigation_trigger.consider(
            service=record.service,
            level=record.level,
            message=record.message,
            timestamp=timestamp,
        )
        if candidate is not None:
            await _record_candidate(session, candidate, record.id)
    except Exception:  # pragma: no cover - defensive
        logger.warning("investigation trigger failed; log stored anyway", exc_info=True)

    return record


def _scope_payload(candidate) -> dict:
    """Serialise the candidate's scope to JSON-safe values."""
    scope = candidate.scope()
    return {
        "services": list(scope["services"]),
        "start": scope["start"].isoformat(),
        "end": scope["end"].isoformat(),
    }


async def _record_candidate(session, candidate, log_id: int) -> None:
    """Persist a candidate, tolerating the duplicate another replica already wrote.

    The unique index on (service, template) is the coordination point: rather
    than checking first and racing, the insert is attempted and an
    IntegrityError is read as "another writer already surfaced this family" --
    a success for the queue, even though this writer lost.
    """
    session.add(
        InvestigationCandidate(
            service=candidate.service,
            level=candidate.level,
            message=candidate.message,
            template=candidate.template,
            reason=candidate.reason,
            scope=_scope_payload(candidate),
            log_id=log_id,
            occurred_at=candidate.timestamp,
        )
    )
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        return
    INVESTIGATION_CANDIDATES.labels(reason=candidate.reason).inc()
    logger.info("investigation candidate: %s (%s)", candidate.service, candidate.reason)
