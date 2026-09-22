"""Worker lifecycle: atomic claims, events, terminal states, outage, recovery."""

import asyncio
import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from app import investigator
from app.investigation_loop import TOOL_SCHEMAS
from app.investigation_schemas import InvestigationScope
from app.investigation_tools import EvidenceTools
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


TOOL_ARGUMENTS = {
    "query_logs": SCOPE,
    "summarize_logs": SCOPE,
    "search_runbooks": {"query": "checkout"},
    "read_metric_series": {
        "service": "checkout",
        "metric_name": "error_rate",
        "start": SCOPE["start"],
        "end": SCOPE["end"],
    },
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


@pytest.mark.parametrize("name", TOOL_ARGUMENTS)
async def test_every_registered_tool_persists_its_returned_batch(session_factory, name):
    assert set(TOOL_ARGUMENTS) == set(TOOL_SCHEMAS)
    run_id = await seed(session_factory)
    async with session_factory() as evidence_session:
        tools = investigator.RecordingTools(
            InvestigationScope(**SCOPE),
            session_factory,
            run_id,
            session=evidence_session,
        )
        batch = await getattr(tools, name)(**TOOL_ARGUMENTS[name])
    async with session_factory() as session:
        events = (
            await session.scalars(
                select(InvestigationEvent).where(InvestigationEvent.investigation_id == run_id)
            )
        ).all()
        events = sorted(events, key=lambda event: event.sequence)
        assert len(events) == 2
        assert events[0].sequence == 1 and events[0].kind == "tool_request"
        assert events[0].payload == {"tool": name, "arguments": TOOL_ARGUMENTS[name]}
        assert events[1].sequence == 2 and events[1].kind == "tool_call"
        assert events[1].payload == {
            "request_sequence": 1,
            "tool": name,
            "arguments": TOOL_ARGUMENTS[name],
            "result": batch.model_dump(mode="json"),
        }


@pytest.mark.parametrize("name", TOOL_ARGUMENTS)
async def test_every_registered_tool_checks_cancellation_before_execution(
    session_factory, monkeypatch, name
):
    run_id = await seed(session_factory, status="cancelling")

    async def forbidden(self, **arguments):
        raise AssertionError("tool executed after cancellation")

    monkeypatch.setattr(EvidenceTools, name, forbidden)
    async with session_factory() as evidence_session:
        tools = investigator.RecordingTools(
            InvestigationScope(**SCOPE),
            session_factory,
            run_id,
            session=evidence_session,
        )
        with pytest.raises(asyncio.CancelledError):
            await getattr(tools, name)(**TOOL_ARGUMENTS[name])
    async with session_factory() as session:
        assert (
            await session.scalar(
                select(InvestigationEvent).where(InvestigationEvent.investigation_id == run_id)
            )
            is None
        )


@pytest.mark.parametrize("service", ["checkout", "inventory"])
async def test_metric_success_and_scope_denial_are_persisted(session_factory, monkeypatch, service):
    run_id = await seed(session_factory)
    requests = []

    def prometheus(request):
        requests.append(request)
        assert request.url.host == "prometheus.test"
        assert 'service="checkout"' in request.url.params["query"]
        return httpx.Response(
            200,
            json={
                "status": "success",
                "data": {
                    "result": [
                        {
                            "values": [
                                [datetime.fromisoformat(SCOPE["start"]).timestamp() + 60, "0.25"]
                            ]
                        }
                    ]
                },
            },
        )

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(prometheus), **kwargs),
    )
    async with session_factory() as evidence_session:
        tools = investigator.RecordingTools(
            InvestigationScope(**SCOPE),
            session_factory,
            run_id,
            session=evidence_session,
            prometheus_url="http://prometheus.test",
        )
        batch = await tools.read_metric_series(
            **{**TOOL_ARGUMENTS["read_metric_series"], "service": service}
        )
    if service == "checkout":
        assert len(requests) == 1 and batch.error is None
        assert batch.items[0].kind == "metric"
        assert batch.items[0].content["points"][0][1] == "0.25"
    else:
        assert requests == [] and batch.error == "scope_violation"
    async with session_factory() as session:
        event = await session.scalar(
            select(InvestigationEvent).where(
                InvestigationEvent.investigation_id == run_id,
                InvestigationEvent.kind == "tool_call",
            )
        )
        assert event is not None
        assert event.payload["tool"] == "read_metric_series"
        assert event.payload["result"] == batch.model_dump(mode="json")


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
        assert kinds[:-1] == ["tool_request", "tool_call"] * 3  # B's fixed retrieval
        assert kinds[-1] == "status" and events[-1].payload["status"] == "completed"
        assert events[1].payload["result"]["items"][0]["evidence_id"] == "log:1"


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
