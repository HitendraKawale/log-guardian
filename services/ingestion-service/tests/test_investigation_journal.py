"""Verify committed intent from another connection, not from a shared in-memory session."""

import json
from contextlib import asynccontextmanager

import pytest
from app.investigation_schemas import InvestigationScope
from app.investigation_tools import EvidenceTools
from app.investigator import RecordingTools
from app.models import Base, Investigation, InvestigationEvent
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

SCOPE = {"services": ["checkout"], "start": "2026-01-01T10:00:00Z", "end": "2026-01-01T10:10:00Z"}


@asynccontextmanager
async def database(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path}/journal.db"
    writer, reader = create_async_engine(url), create_async_engine(url)
    factory, observer = (
        async_sessionmaker(writer, expire_on_commit=False),
        async_sessionmaker(reader),
    )
    try:
        async with writer.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with factory() as session:
            run = Investigation(
                question="Journal test",
                system="C",
                scope=SCOPE,
                request_sha256="0" * 64,
                status="running",
            )
            session.add(run)
            await session.commit()
            run_id = run.id
        yield factory, observer, run_id
    finally:
        await reader.dispose()
        await writer.dispose()


async def test_request_is_committed_and_redacted_before_tool_body(tmp_path, monkeypatch):
    original = EvidenceTools.query_logs
    async with database(tmp_path) as (factory, observer, run_id):

        async def check(self, **arguments):
            assert arguments["text"] == "password=PRIVATE_CANARY"
            async with observer() as session:
                rows = (await session.scalars(select(InvestigationEvent))).all()
                assert len(rows) == 1 and rows[0].kind == "tool_request"
                assert rows[0].payload["arguments_redacted"] is True
                assert "PRIVATE_CANARY" not in json.dumps(rows[0].payload)
            return await original(self, **arguments)

        monkeypatch.setattr(EvidenceTools, "query_logs", check)
        async with factory() as session:
            tools = RecordingTools(InvestigationScope(**SCOPE), factory, run_id, session=session)
            await tools.query_logs(**SCOPE, text="password=PRIVATE_CANARY")
        async with observer() as session:
            rows = (
                await session.scalars(
                    select(InvestigationEvent).order_by(InvestigationEvent.sequence)
                )
            ).all()
            assert len(rows) == 2 and rows[1].payload["request_sequence"] == rows[0].sequence
            assert "PRIVATE_CANARY" not in json.dumps([row.payload for row in rows])


@pytest.mark.parametrize(
    "failing_kind,executions,expected_kinds",
    [
        ("tool_request", 0, []),
        ("tool_call", 1, ["tool_request"]),
    ],
)
async def test_failed_commit_never_fabricates_execution_or_completion(
    tmp_path, monkeypatch, failing_kind, executions, expected_kinds
):
    original_record, original_tool = RecordingTools._record, EvidenceTools.query_logs
    invoked = []

    async def record(self, kind, payload):
        if kind == failing_kind:
            raise OSError("synthetic write failure")
        return await original_record(self, kind, payload)

    async def tool(self, **arguments):
        invoked.append(True)
        return await original_tool(self, **arguments)

    monkeypatch.setattr(RecordingTools, "_record", record)
    monkeypatch.setattr(EvidenceTools, "query_logs", tool)
    async with database(tmp_path) as (factory, observer, run_id):
        async with factory() as session:
            tools = RecordingTools(InvestigationScope(**SCOPE), factory, run_id, session=session)
            with pytest.raises(OSError):
                await tools.query_logs(**SCOPE)
        assert len(invoked) == executions
        async with observer() as session:
            rows = (await session.scalars(select(InvestigationEvent))).all()
            assert [row.kind for row in rows] == expected_kinds


async def test_uncommitted_request_rolls_back_without_executing(tmp_path, monkeypatch):
    original_commit = AsyncSession.commit

    async def fail_after_flush(self):
        if any(
            isinstance(row, InvestigationEvent) and row.kind == "tool_request" for row in self.new
        ):
            await self.flush()
            raise OSError("synthetic commit failure after insert")
        return await original_commit(self)

    async def forbidden(self, **arguments):
        raise AssertionError("tool ran without a committed request")

    monkeypatch.setattr(AsyncSession, "commit", fail_after_flush)
    monkeypatch.setattr(EvidenceTools, "query_logs", forbidden)
    async with database(tmp_path) as (factory, observer, run_id):
        async with factory() as session:
            tools = RecordingTools(InvestigationScope(**SCOPE), factory, run_id, session=session)
            with pytest.raises(OSError):
                await tools.query_logs(**SCOPE)
        async with observer() as session:
            assert await session.scalar(select(InvestigationEvent)) is None
