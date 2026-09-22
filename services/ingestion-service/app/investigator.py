"""Investigation worker: a separate process from the HTTP API (`python -m app.investigator`).

Claims queued runs atomically, records ordered events, enforces deadlines, and
preserves terminal states. Usage and timings are stored on the run row because
this process does not share the API's /metrics registry.
"""

import asyncio
import contextlib
import logging
import os
import socket
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from .investigation_agent import MODEL, BaselineConfig, run_investigation
from .investigation_loop import TOOL_SCHEMAS
from .investigation_schemas import InvestigationScope
from .investigation_tools import EvidenceTools, redact
from .models import Investigation, InvestigationEvent

logger = logging.getLogger(__name__)
POLL_SECONDS = 1.0
# A running claim older than this is abandoned (crashed worker) and fails closed.
STALE_CLAIM = timedelta(minutes=10)
TERMINAL = {"completed", "failed", "cancelled"}


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _code_revision() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=Path(__file__).parent, text=True, timeout=10
        ).strip()
    except (OSError, subprocess.SubprocessError):
        return None


class RecordingTools(EvidenceTools):
    """Commit intent before execution; a missing completion leaves outcome unknown."""

    def __init__(self, scope, session_factory, run_id, **kwargs):
        super().__init__(scope, **kwargs)
        self._factory = session_factory
        self._run_id = run_id
        self._sequence = 0

    async def _record(self, kind: str, payload: dict) -> int:
        self._sequence += 1
        sequence = self._sequence
        async with self._factory() as session:
            session.add(
                InvestigationEvent(
                    investigation_id=self._run_id,
                    sequence=sequence,
                    kind=kind,
                    payload=payload,
                )
            )
            await session.commit()
        return sequence

    async def _cancelling(self) -> bool:
        async with self._factory() as session:
            status = await session.scalar(
                select(Investigation.status).where(Investigation.id == self._run_id)
            )
        return status == "cancelling"

    async def _initial_logs(self, arguments):
        return await self._wrap("query_logs", origin="server_initial")(**arguments)

    def _wrap(self, name, *, origin=None):
        async def call(**arguments):
            if await self._cancelling():
                raise asyncio.CancelledError
            recorded_arguments = redact(arguments)
            audit = {"tool": name, "arguments": recorded_arguments}
            if origin is not None:
                audit["origin"] = origin
            if recorded_arguments != arguments:
                audit["arguments_redacted"] = True
            request_sequence = await self._record("tool_request", audit)
            batch = await getattr(super(RecordingTools, self), name)(**arguments)
            await self._record(
                "tool_call",
                {
                    **audit,
                    "request_sequence": request_sequence,
                    "result": batch.model_dump(mode="json"),
                },
            )
            return batch

        return call

    def __getattribute__(self, name):
        if name in TOOL_SCHEMAS:
            return object.__getattribute__(self, "_wrap")(name)
        return object.__getattribute__(self, name)


async def claim_next(session_factory, worker_id: str) -> str | None:
    """Atomic claim: only one worker's UPDATE matches the queued row."""
    async with session_factory() as session:
        run_id = await session.scalar(
            select(Investigation.id)
            .where(Investigation.status == "queued")
            .order_by(Investigation.created_at)
            .limit(1)
        )
        if run_id is None:
            return None
        result = await session.execute(
            update(Investigation)
            .where(Investigation.id == run_id, Investigation.status == "queued")
            .values(status="running", worker_id=worker_id, started_at=_utcnow())
        )
        await session.commit()
        return run_id if result.rowcount == 1 else None


async def recover_stale(session_factory) -> int:
    """Fail abandoned running claims from crashed workers; never touch terminal rows."""
    async with session_factory() as session:
        result = await session.execute(
            update(Investigation)
            .where(
                Investigation.status.in_(("running", "cancelling")),
                Investigation.started_at < _utcnow() - STALE_CLAIM,
            )
            .values(status="failed", error="stale_claim", finished_at=_utcnow())
        )
        await session.commit()
        return result.rowcount


async def execute_run(session_factory, run_id: str, client, model: str = MODEL) -> None:
    async with session_factory() as session:
        run = await session.get(Investigation, run_id)
        question, system, scope = run.question, run.system, dict(run.scope)
    error = None
    result = None
    try:
        # The worker owns a database session per tool call through the factory;
        # EvidenceTools needs one live session for the whole run instead.
        async with session_factory() as evidence_session:
            from .config import settings

            tools = RecordingTools(
                InvestigationScope(**scope),
                session_factory,
                run_id,
                session=evidence_session,
                prometheus_url=settings.prometheus_url or None,
            )
            config = BaselineConfig(model=model, max_cost_usd="0.025")
            result = await run_investigation(system, question, tools, client, config)
    except asyncio.CancelledError:
        error = "cancelled"
    except Exception:
        logger.exception("investigation run failed", extra={"run_id": run_id})
        error = "worker_error"
    async with session_factory() as session:
        run = await session.get(Investigation, run_id)
        if run.status in TERMINAL:  # A sweeper or admin already finalized it.
            return
        cancelled = error == "cancelled" or run.status == "cancelling"
        if cancelled:
            run.status, run.error = "cancelled", None
        elif error is not None or result is None:
            run.status, run.error = "failed", error or "worker_error"
        elif result["status"] == "completed":
            run.status, run.report = "completed", result["report"]
        else:
            run.status, run.error = "failed", result["error"]
        if result is not None:
            run.model_requested = result["model_requested"]
            run.prompt_sha256 = result["prompt_sha256"]
            run.usage = result["usage"]
            run.estimated_cost_usd = result["estimated_cost_usd"]
            run.elapsed_ms = result["elapsed_ms"]
        run.code_revision = _code_revision()
        run.finished_at = _utcnow()
        session.add(
            InvestigationEvent(
                investigation_id=run_id,
                sequence=1_000_000,  # Status events sort after tool events.
                kind="status",
                payload={"status": run.status, "error": run.error},
            )
        )
        await session.commit()


async def run_once(session_factory, client, worker_id: str) -> bool:
    """One poll cycle; returns whether a run was executed. Used directly by tests."""
    await recover_stale(session_factory)
    run_id = await claim_next(session_factory, worker_id)
    if run_id is None:
        return False
    await execute_run(session_factory, run_id, client)
    return True


async def main() -> None:
    from openai import AsyncOpenAI

    from .config import settings
    from .database import engine
    from .telemetry import setup_worker_telemetry

    if not settings.investigation_api_key:
        raise SystemExit("Refusing to start: INVESTIGATION_API_KEY is not configured")
    setup_worker_telemetry("investigation-worker", sqlalchemy_engine=engine)
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    client = AsyncOpenAI(api_key=key, max_retries=0) if key else None
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    worker_id = f"{socket.gethostname()}:{os.getpid()}"
    logger.info("investigation worker started", extra={"worker_id": worker_id})
    while True:
        worked = await run_once(session_factory, client, worker_id)
        if not worked:
            await asyncio.sleep(POLL_SECONDS)


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main())
