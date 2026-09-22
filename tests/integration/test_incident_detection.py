"""PostgreSQL migration and coordination checks in a fresh disposable database."""

import asyncio
import os
import subprocess
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

SERVICE = Path(__file__).resolve().parents[2] / "services/ingestion-service"


@pytest.fixture(scope="session", autouse=True)
def require_stack():
    """This test needs only an explicitly supplied disposable PostgreSQL server."""
    if not os.environ.get("LG_TEST_POSTGRES_URL"):
        pytest.skip("set LG_TEST_POSTGRES_URL to a task-owned PostgreSQL server")


def test_postgres_upgrade_concurrency_recurrence_and_deadline(monkeypatch):
    async def exercise():
        import asyncpg

        admin_url = os.environ["LG_TEST_POSTGRES_URL"].replace("postgresql+asyncpg:", "postgresql:")
        name = "lg_detector_" + uuid.uuid4().hex
        admin = await asyncpg.connect(admin_url)
        try:
            await admin.execute(f'CREATE DATABASE "{name}"')
        finally:
            await admin.close()
        # The task container owns cleanup; never drop an existing user database.
        url = admin_url.rsplit("/", 1)[0] + "/" + name
        env = {**os.environ, "DATABASE_URL": url.replace("postgresql:", "postgresql+asyncpg:")}

        def migrate(direction, revision):
            result = subprocess.run(
                [sys.executable, "-m", "alembic", direction, revision],
                cwd=SERVICE,
                env=env,
                capture_output=True,
                text=True,
            )
            assert result.returncode == 0, result.stderr

        migrate("upgrade", "0005")
        conn = await asyncpg.connect(url)
        await conn.execute("""INSERT INTO investigation_candidates
            (id,service,level,message,template,reason,scope,status,occurred_at,created_at)
            VALUES ('legacy','old','ERROR','timeout','timeout','unseen-template',
            '{"services":["old"],"start":"2026-01-01T00:00:00Z","end":"2026-01-01T00:10:00Z"}',
            'dismissed',now(),now())""")
        await conn.close()
        migrate("upgrade", "0006")
        sys.path.insert(0, str(SERVICE))
        from app import incident_detection
        from app.config import settings
        from app.incident_detection import observe_log
        from app.models import DetectorState, Investigation, InvestigationCandidate, Log
        from sqlalchemy import func, select, text
        from sqlalchemy.exc import DBAPIError
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        engine = create_async_engine(env["DATABASE_URL"])
        factory = async_sessionmaker(engine, expire_on_commit=False)
        warmup = settings.trigger_warmup_logs
        settings.trigger_warmup_logs = 0
        at = datetime.now(UTC)

        async def store(at):
            async with factory() as session:
                row = Log(
                    service="checkout",
                    level="ERROR",
                    message="same timeout",
                    timestamp=at,
                    status="unscored",
                )
                session.add(row)
                await session.commit()
                return row

        async def observe(row, at):
            async with factory() as session:
                await observe_log(session, row, received_at=at)

        try:
            async with factory() as session:
                legacy = await session.get(InvestigationCandidate, "legacy")
                assert legacy.status == "dismissed" and legacy.occurrence_count == 1
                assert legacy.last_seen_at == legacy.occurred_at
            records = [await store(at) for _ in range(10)]
            # Serialization has its own test budget; production deadlines are
            # restored before the blocked-row check below.
            with monkeypatch.context() as budget:
                budget.setattr(incident_detection, "TRANSACTION_TIMEOUT_SECONDS", 10)
                budget.setattr(incident_detection, "SQL_TIMEOUT_MS", 5000)
                outcomes = await asyncio.gather(
                    *(observe(row, at) for row in records), return_exceptions=True
                )
            assert not [result for result in outcomes if isinstance(result, BaseException)]
            await engine.dispose()
            async with factory() as session:
                state = await session.get(DetectorState, "checkout")
                assert state.data["observed"] == 10
                first_id = state.data["active_candidate_id"]
                candidate = await session.get(InvestigationCandidate, first_id)
                assert candidate.occurrence_count == 10
                candidate.status = "dismissed"
                await session.commit()
            later = at + timedelta(minutes=10)
            for _ in range(5):
                await observe(await store(later), later)
            async with factory() as session:
                old = await session.get(InvestigationCandidate, first_id)
                assert old.active_service is None and old.status == "dismissed"
                assert (
                    await session.scalar(
                        select(func.count())
                        .select_from(InvestigationCandidate)
                        .where(InvestigationCandidate.service == "checkout")
                    )
                    == 2
                )
                assert await session.scalar(select(func.count()).select_from(Investigation)) == 0
            row = await store(later)
            assert incident_detection.TRANSACTION_TIMEOUT_SECONDS == 0.25
            assert incident_detection.SQL_TIMEOUT_MS == 200
            async with factory() as blocker, factory() as caller:
                await blocker.execute(
                    text("SELECT service FROM detector_states WHERE service='checkout' FOR UPDATE")
                )
                started = asyncio.get_running_loop().time()
                with pytest.raises((TimeoutError, DBAPIError)):
                    await observe_log(caller, row, received_at=later)
                assert asyncio.get_running_loop().time() - started < 1
                assert await caller.get(Log, row.id) is not None
                await blocker.rollback()
            from app.routes.investigations import promote_candidate

            async with factory() as session:
                active = await session.scalar(
                    select(InvestigationCandidate).where(
                        InvestigationCandidate.active_service == "checkout"
                    )
                )
                active_id = active.id

            async def promote():
                async with factory() as session:
                    return await promote_candidate(active_id, session=session)

            first, second = await asyncio.gather(promote(), promote())
            assert first["id"] == second["id"]
            async with factory() as session:
                active = await session.get(InvestigationCandidate, active_id)
                frozen_scope = dict(active.scope)
                assert active.investigation_id == first["id"]
                assert await session.scalar(select(func.count()).select_from(Investigation)) == 1
            await observe(await store(later + timedelta(seconds=1)), later + timedelta(seconds=1))
            async with factory() as session:
                active = await session.get(InvestigationCandidate, active_id)
                assert active.scope == frozen_scope and active.investigation_id == first["id"]
            result = subprocess.run(
                [sys.executable, "-m", "alembic", "downgrade", "0005"],
                cwd=SERVICE,
                env=env,
                capture_output=True,
                text=True,
            )
            assert result.returncode != 0 and "recurring candidate history" in result.stderr
        finally:
            settings.trigger_warmup_logs = warmup
            await engine.dispose()

    asyncio.run(exercise())
