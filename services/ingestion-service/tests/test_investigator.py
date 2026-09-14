"""Worker lifecycle: atomic claims, events, terminal states, outage, recovery."""

import asyncio
import json
from datetime import UTC, datetime, timedelta

import httpx
from app import investigator
from app.investigator import claim_next, execute_run, recover_stale, run_once
from app.models import Investigation, InvestigationEvent, Log
from openai import AsyncOpenAI
from sqlalchemy import select

REPORT = {
    "observations": [{"claim": "checkout logged an error", "evidence_ids": ["log:1"]}],
    "missing_evidence": [],
    "alternatives": [],
    "likely_cause": {"claim": "The observed error", "evidence_ids": ["log:1"]},
    "outcome": "supported",
    "suggested_checks": ["Read more logs"],
}
SCOPE = {
    "services": ["checkout"],
    "start": "2026-01-01T10:00:00+00:00",
    "end": "2026-01-01T10:10:00+00:00",
}


def scripted_client(handler):
    return AsyncOpenAI(
        api_key="scripted-placeholder",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


def completion(body):
    return httpx.Response(
        200,
        json={
            "id": "scripted",
            "object": "chat.completion",
            "created": 1,
            "model": body["model"],
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": json.dumps(REPORT)},
                }
            ],
            "usage": {"prompt_tokens": 50, "completion_tokens": 50, "total_tokens": 100},
        },
    )


async def seed(session_factory, **overrides):
    async with session_factory() as session:
        session.add(
            Log(
                service="checkout",
                level="ERROR",
                message="boom",
                timestamp=datetime(2026, 1, 1, 10, 0, 5, tzinfo=UTC),
            )
        )
        run = Investigation(
            question="Why?", system="B", scope=SCOPE, request_sha256="x" * 64, **overrides
        )
        session.add(run)
        await session.commit()
        return run.id


async def test_claim_is_atomic_and_single_winner(session_factory):
    await seed(session_factory)
    winners = await asyncio.gather(*[claim_next(session_factory, f"w{n}") for n in range(4)])
    assert len([w for w in winners if w]) == 1
    assert await claim_next(session_factory, "late") is None


async def test_completed_run_persists_report_events_usage_and_timings(session_factory):
    run_id = await seed(session_factory)
    assert await claim_next(session_factory, "w1")
    async with scripted_client(lambda r: completion(json.loads(r.content))) as client:
        await execute_run(session_factory, run_id, client)
    async with session_factory() as session:
        run = await session.get(Investigation, run_id)
        assert run.status == "completed" and run.report["outcome"] == "supported"
        assert run.usage["input_tokens"] == 50 and run.estimated_cost_usd is not None
        assert run.elapsed_ms > 0 and run.finished_at is not None
        events = (
            await session.scalars(
                select(InvestigationEvent)
                .where(InvestigationEvent.investigation_id == run_id)
                .order_by(InvestigationEvent.sequence)
            )
        ).all()
        kinds = [event.kind for event in events]
        assert kinds[:3] == ["tool_call", "tool_call", "tool_call"]  # B's fixed retrieval
        assert kinds[-1] == "status" and events[-1].payload["status"] == "completed"
        assert events[0].payload["result"]["items"][0]["evidence_id"] == "log:1"


async def test_provider_outage_fails_run_and_ingestion_keeps_working(session_factory, make_client):
    run_id = await seed(session_factory)
    assert await claim_next(session_factory, "w1")
    async with scripted_client(lambda request: httpx.Response(503)) as client:
        await execute_run(session_factory, run_id, client)
    async with session_factory() as session:
        run = await session.get(Investigation, run_id)
        assert run.status == "failed" and run.error == "provider_error"
        assert run.usage is None and run.estimated_cost_usd is None
    async with make_client(None) as api:
        accepted = await api.post(
            "/logs",
            json={
                "service": "checkout",
                "level": "INFO",
                "message": "still alive",
                "timestamp": "2026-01-01T10:01:00Z",
            },
        )
        assert accepted.status_code == 201


async def test_missing_client_fails_closed_without_fabrication(session_factory):
    run_id = await seed(session_factory)
    assert await claim_next(session_factory, "w1")
    await execute_run(session_factory, run_id, None)
    async with session_factory() as session:
        run = await session.get(Investigation, run_id)
        assert run.status == "failed" and run.error == "provider_not_configured"
        assert run.report is None


async def test_cancellation_race_wins_over_completion(session_factory):
    run_id = await seed(session_factory)
    assert await claim_next(session_factory, "w1")

    async def cancel_midway(request):
        async with session_factory() as session:
            run = await session.get(Investigation, run_id)
            run.status = "cancelling"
            await session.commit()
        return completion(json.loads(request.content))

    async with scripted_client(cancel_midway) as client:
        await execute_run(session_factory, run_id, client)
    async with session_factory() as session:
        run = await session.get(Investigation, run_id)
        assert run.status == "cancelled" and run.error is None


async def test_cancelling_before_tools_stops_without_model_request(session_factory):
    run_id = await seed(session_factory, status="cancelling", worker_id="w1")
    requests = []

    async def tracking(request):
        requests.append(request)
        return completion(json.loads(request.content))

    async with scripted_client(tracking) as client:
        await execute_run(session_factory, run_id, client)
    async with session_factory() as session:
        run = await session.get(Investigation, run_id)
        assert run.status == "cancelled" and requests == []


async def test_restart_recovery_fails_stale_claims_only(session_factory):
    stale_id = await seed(
        session_factory,
        status="running",
        worker_id="dead",
        started_at=datetime.now(UTC) - timedelta(minutes=11),
    )
    fresh_id = await seed(
        session_factory, status="running", worker_id="alive", started_at=datetime.now(UTC)
    )
    done_id = await seed(
        session_factory,
        status="completed",
        started_at=datetime.now(UTC) - timedelta(hours=2),
        finished_at=datetime.now(UTC),
    )
    assert await recover_stale(session_factory) == 1
    async with session_factory() as session:
        assert (await session.get(Investigation, stale_id)).status == "failed"
        assert (await session.get(Investigation, stale_id)).error == "stale_claim"
        assert (await session.get(Investigation, fresh_id)).status == "running"
        assert (await session.get(Investigation, done_id)).status == "completed"


async def test_run_once_processes_queue_and_reports_idle(session_factory):
    async with scripted_client(lambda r: completion(json.loads(r.content))) as client:
        assert await run_once(session_factory, client, "w1") is False
        run_id = await seed(session_factory)
        assert await run_once(session_factory, client, "w1") is True
        assert await run_once(session_factory, client, "w1") is False
    async with session_factory() as session:
        assert (await session.get(Investigation, run_id)).status == "completed"


async def test_terminal_state_is_never_overwritten(session_factory, monkeypatch):
    run_id = await seed(session_factory)
    assert await claim_next(session_factory, "w1")

    async def finalize_first(request):
        async with session_factory() as session:
            run = await session.get(Investigation, run_id)
            run.status, run.error = "failed", "stale_claim"
            await session.commit()
        return completion(json.loads(request.content))

    monkeypatch.setattr(investigator, "STALE_CLAIM", timedelta(seconds=0))
    async with scripted_client(finalize_first) as client:
        await execute_run(session_factory, run_id, client)
    async with session_factory() as session:
        run = await session.get(Investigation, run_id)
        assert run.status == "failed" and run.error == "stale_claim"
