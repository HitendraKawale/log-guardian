"""Exercise durable detector transactions on independent SQLite connections."""

import asyncio
import importlib
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from app.config import settings
from app.database import Base
from app.models import Investigation, InvestigationCandidate, Log
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

AT = datetime(2026, 9, 22, 10, tzinfo=UTC)


@pytest_asyncio.fixture
async def db(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'detector.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    monkeypatch.setattr(settings, "trigger_warmup_logs", 0)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def stored(db, at=AT):
    async with db() as session:
        log = Log(
            service="checkout",
            level="ERROR",
            message="familiar timeout",
            timestamp=at,
            status="unscored",
        )
        session.add(log)
        await session.commit()
        return log


async def observe(db, log, at=AT):
    module = importlib.import_module("app.incident_detection")
    async with db() as session:
        return await module.observe_log(session, log, received_at=at)


async def test_concurrent_observations_group_and_survive_new_sessions(db, monkeypatch):
    module = importlib.import_module("app.incident_detection")
    # Check serialization, not whether a shared runner can finish ten writes in 250 ms.
    # Deadline behavior is covered separately with the unchanged production budgets.
    with monkeypatch.context() as budget:
        budget.setattr(module, "TRANSACTION_TIMEOUT_SECONDS", 10)
        budget.setattr(module, "SQL_TIMEOUT_MS", 5000)
        logs = [await stored(db) for _ in range(10)]
        outcomes = await asyncio.gather(*(observe(db, log) for log in logs), return_exceptions=True)
    assert not [result for result in outcomes if isinstance(result, BaseException)]
    assert module.TRANSACTION_TIMEOUT_SECONDS == 0.25
    assert module.SQL_TIMEOUT_MS == 200
    from app.models import DetectorState

    async with db() as session:
        candidates = (await session.scalars(select(InvestigationCandidate))).all()
        assert len(candidates) == 1
        assert candidates[0].occurrence_count == 10
        state = await session.get(DetectorState, "checkout")
        assert state.data["observed"] == 10
        assert await session.scalar(select(func.count()).select_from(Investigation)) == 0
    later = await stored(db, AT + timedelta(seconds=1))
    await observe(db, later, AT + timedelta(seconds=1))
    async with db() as session:
        assert (await session.get(DetectorState, "checkout")).data["observed"] == 11


@pytest.mark.parametrize("status", ["dismissed", "promoted"])
async def test_quiet_recurrence_preserves_old_review_state_and_link(db, status):
    first = await stored(db)
    await observe(db, first)
    async with db() as session:
        candidate = await session.scalar(select(InvestigationCandidate))
        original_id = candidate.id
        candidate.status = status
        # A real investigation link must remain unchanged, including its scope.
        run = Investigation(
            question="owner question",
            system="B",
            scope=dict(candidate.scope),
            request_sha256="a" * 64,
        )
        session.add(run)
        await session.flush()
        if status == "promoted":
            candidate.investigation_id = run.id
        original_scope = dict(candidate.scope)
        original_link = candidate.investigation_id
        await session.commit()
    at = AT + timedelta(seconds=1)
    await observe(db, await stored(db, at), at)
    async with db() as session:
        old = await session.get(InvestigationCandidate, original_id)
        assert old.occurrence_count == 2 and old.status == status
        if status == "promoted":
            assert old.scope == original_scope
    # A known template needs a burst, not novelty, to open the next episode.
    at += timedelta(minutes=10)
    for _ in range(5):
        await observe(db, await stored(db, at), at)
    async with db() as session:
        candidates = (await session.scalars(select(InvestigationCandidate))).all()
        assert len(candidates) == 2
        old = await session.get(InvestigationCandidate, original_id)
        assert old.active_service is None and old.status == status
        assert old.investigation_id == original_link
        new = next(row for row in candidates if row.id != original_id)
        assert new.status == "new" and new.active_service == "checkout"


async def test_failed_candidate_insert_rolls_back_learning_not_log(db):
    log = await stored(db)
    async with db() as session:
        await session.execute(
            text(
                "CREATE TRIGGER reject_candidate BEFORE INSERT ON investigation_candidates BEGIN SELECT RAISE(ABORT, 'test failure'); END"
            )
        )
        await session.commit()
    with pytest.raises(IntegrityError, match="test failure"):
        await observe(db, log)
    from app.models import DetectorState

    async with db() as session:
        assert await session.get(Log, log.id) is not None
        assert await session.get(DetectorState, "checkout") is None
        assert await session.scalar(select(func.count()).select_from(InvestigationCandidate)) == 0


async def test_lock_deadline_leaves_session_and_stored_log_usable(db):
    log = await stored(db)
    module = importlib.import_module("app.incident_detection")
    assert module.TRANSACTION_TIMEOUT_SECONDS == 0.25
    assert module.SQL_TIMEOUT_MS == 200
    async with db() as blocker, db() as caller:
        await blocker.execute(text("BEGIN IMMEDIATE"))
        started = asyncio.get_running_loop().time()
        with pytest.raises((TimeoutError, DBAPIError)):
            await module.observe_log(caller, log, received_at=AT)
        assert asyncio.get_running_loop().time() - started < 1
        assert await caller.get(Log, log.id) is not None
        await blocker.rollback()
    await observe(db, log)


async def test_sqlite_busy_timeout_is_restored_before_pool_checkin(db):
    from sqlalchemy import event

    values = []
    engine = db.kw["bind"]

    def checked_in(connection, record):
        if connection is not None:
            cursor = connection.cursor()
            cursor.execute("PRAGMA busy_timeout")
            values.append(cursor.fetchone()[0])
            cursor.close()

    event.listen(engine.sync_engine, "checkin", checked_in)
    try:
        await observe(db, await stored(db))
    finally:
        event.remove(engine.sync_engine, "checkin", checked_in)
    assert values and all(value == 5000 for value in values), values


async def test_detector_deadline_includes_waiting_for_a_pool_connection(db):
    log = await stored(db)
    from sqlalchemy.pool import AsyncAdaptedQueuePool

    engine = create_async_engine(
        db.kw["bind"].url, poolclass=AsyncAdaptedQueuePool, pool_size=1, max_overflow=0
    )
    module = importlib.import_module("app.incident_detection")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.connect(), factory() as caller:
            started = asyncio.get_running_loop().time()
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(module.observe_log(caller, log, received_at=AT), 0.75)
            assert asyncio.get_running_loop().time() - started < 0.5
    finally:
        await engine.dispose()
