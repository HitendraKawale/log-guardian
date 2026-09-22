"""Commit bounded detector state separately so detection cannot roll back logs."""

import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .investigation_schemas import InvestigationScope
from .models import DetectorState, InvestigationCandidate
from .templates import normalize_message
from .trigger import advance_detector


def evidence_scope(service, timestamp):
    at = timestamp.replace(tzinfo=timestamp.tzinfo or UTC)
    return InvestigationScope(
        services=(service,), start=at - timedelta(minutes=10), end=at + timedelta(seconds=1)
    ).model_dump(mode="json")


async def observe_log(session, record, *, received_at=None):
    """Observe an already committed log once; caller records failures, never retries.

    A separate session owns the detector transaction and cannot expire the
    caller's log on rollback. Database locks, not process memory, coordinate
    replicas. SQLite's database-wide writer lock limits local throughput.
    """
    now = received_at or datetime.now(UTC)
    arguments = {
        "level": record.level,
        "message": record.message,
        "timestamp": record.timestamp,
        "received_at": now,
        "levels": settings.trigger_levels,
        "warmup_logs": settings.trigger_warmup_logs,
    }
    # Excluded history must not create empty service state or acquire a write lock.
    preliminary = advance_detector({}, **arguments)
    if preliminary.excluded:
        return preliminary
    async with (
        asyncio.timeout(0.25),
        session.bind.connect() as connection,
        AsyncSession(bind=connection, expire_on_commit=False) as detector,
    ):
        dialect = detector.bind.dialect.name
        if dialect not in {"sqlite", "postgresql"}:
            raise ValueError("detector requires SQLite or PostgreSQL")
        previous_timeout = None
        try:
            async with detector.begin():
                if dialect == "sqlite":
                    previous_timeout = await detector.scalar(text("PRAGMA busy_timeout"))
                    await detector.execute(text("PRAGMA busy_timeout=200"))
                    # ponytail: SQLite serializes all services; use PostgreSQL row locks for throughput.
                    await detector.execute(text("BEGIN IMMEDIATE"))
                else:
                    await detector.execute(text("SET LOCAL lock_timeout = '200ms'"))
                    await detector.execute(text("SET LOCAL statement_timeout = '200ms'"))
                insert = sqlite_insert if dialect == "sqlite" else pg_insert
                await detector.execute(
                    insert(DetectorState)
                    .values(service=record.service, data={})
                    .on_conflict_do_nothing(index_elements=["service"])
                )
                state = await detector.scalar(
                    select(DetectorState)
                    .where(DetectorState.service == record.service)
                    .with_for_update()
                )
                transition = advance_detector(state.data, **arguments)
                candidate = None
                if state.data.get("active_candidate_id"):
                    candidate = await detector.scalar(
                        select(InvestigationCandidate)
                        .where(InvestigationCandidate.id == state.data["active_candidate_id"])
                        .with_for_update()
                    )
                if candidate is not None and transition.quiet:
                    candidate.active_service = None
                    await detector.flush()
                    candidate = None
                    transition.state.pop("active_candidate_id", None)
                if candidate is None and transition.signal:
                    candidate = InvestigationCandidate(
                        service=record.service,
                        active_service=record.service,
                        level=record.level,
                        message=record.message,
                        template=normalize_message(record.message),
                        reason=transition.signal["reasons"][0],
                        scope=evidence_scope(record.service, record.timestamp),
                        log_id=record.id,
                        occurred_at=record.timestamp,
                        last_seen_at=now,
                        occurrence_count=1,
                        signal_details=transition.signal,
                    )
                    detector.add(candidate)
                    await detector.flush()
                    transition.state["active_candidate_id"] = candidate.id
                elif candidate is not None and transition.eligible:
                    candidate.occurrence_count += 1
                    candidate.last_seen_at = datetime.fromtimestamp(
                        transition.state["last_eligible"], UTC
                    )
                    if candidate.status != "promoted":
                        candidate.scope = evidence_scope(record.service, record.timestamp)
                    if transition.signal:
                        reasons = sorted(
                            set(candidate.signal_details.get("reasons", []))
                            | set(transition.signal["reasons"])
                        )
                        candidate.signal_details = {**transition.signal, "reasons": reasons}
                state.data = transition.state
                await detector.commit()
                return transition
        finally:
            await detector.rollback()
            if previous_timeout is not None:
                await detector.execute(text(f"PRAGMA busy_timeout={int(previous_timeout)}"))
                await detector.rollback()
