"""Use real saved evidence and worker receipts; only the provider transport is scripted."""

import copy
import json

import httpx
import pytest
from app.config import settings
from app.investigation_schemas import InvestigationScope
from app.investigation_security import snapshot
from app.investigation_tools import EvidenceTools
from app.investigator import RecordingTools, claim_next, execute_run
from app.models import Investigation, InvestigationEvent, SecurityCase
from app.routes.security_cases import save_case
from sqlalchemy import select

from tests.security_case_helpers import OWNER, payload
from tests.test_investigator import scripted_client


async def saved_source(factory, body=None):
    async with factory() as session:
        case, _ = await save_case(session, OWNER, body or payload(), "security-input")
        return snapshot(case)


def tools_for(saved):
    return EvidenceTools(
        InvestigationScope(**saved["report"]["scope"]), records=[], security_case=saved
    )


async def test_case_tool_preserves_http_auth_distinction_and_fixed_scope(session_factory):
    saved = await saved_source(session_factory)
    tools = tools_for(saved)
    batch = await tools.read_security_evidence()
    assert batch.source == "security_case" and batch.error is None
    rows = [i for i in batch.items if i.kind == "security_event"]
    assert [i.content["event_kind"] for i in rows] == ["authentication_result", "gateway_request"]
    assert rows[0].content["auth_outcome"] == "failure"
    assert rows[1].content["http_status"] == 200
    assert all(i.content["correlation"] == "confirmed_pair" for i in rows)
    assert batch.items[0].content["collection_complete"] is None
    assert batch.items[0].content["sources"]["auth"]["auth_outcomes"]["failure"] == 1
    assert batch.items[1].content["next_offset"] is None
    for args in (
        {"case_id": "other"},
        {"services": ["other"]},
        {"offset": -1},
        {"limit": True},
        {"limit": 49},
    ):
        denied = await tools.read_security_evidence(**args)
        assert denied.error == "invalid_arguments" and denied.items == []
    absent = EvidenceTools(tools.scope, records=[])
    assert (await absent.read_security_evidence()).error == "source_unavailable"


async def test_byte_pages_are_contiguous_and_citations_stable(session_factory):
    body = payload()
    originals = {k: json.loads(v) for k, v in body["logs"].items()}
    body["logs"] = {
        k: "\n".join(
            json.dumps(
                {
                    **row,
                    "request_id": f"request-{n}-" + "x" * 100,
                    **(
                        {"event_id": f"auth-{n}-" + "y" * 100, "account_ref": "z" * 128}
                        if k == "auth"
                        else {}
                    ),
                }
            )
            for n in range(100)
        )
        for k, row in originals.items()
    }
    saved = await saved_source(session_factory, body)
    tools = tools_for(saved)
    offset, delivered, ids = 0, [], set()
    previous = {}
    while True:
        batch = await tools.read_security_evidence(offset=offset, limit=48)
        assert len(batch.model_dump_json().encode()) <= 16384
        assert batch.error is None
        for item in batch.items:
            if item.evidence_id in previous:
                assert previous[item.evidence_id] == item.model_dump()
            previous[item.evidence_id] = item.model_dump()
        events = [i for i in batch.items if i.kind == "security_event"]
        assert 0 < len(events) < 48  # long records exercise byte-based truncation
        delivered.extend(i.content["evidence"] for i in events)
        ids.update(i.evidence_id for i in events)
        next_offset = batch.items[1].content["next_offset"]
        if next_offset is None:
            assert batch.truncated is False
            break
        assert next_offset == offset + len(events) and batch.truncated
        offset = next_offset
    assert delivered == [r["evidence"] for r in saved["report"]["timeline"]]
    assert len(ids) == 200
    assert all(len(identity) <= 128 for identity in ids)


def response(body, report=None, tool=None):
    message = {"role": "assistant", "content": json.dumps(report)}
    if tool:
        message = {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "followup",
                    "type": "function",
                    "function": {"name": tool[0], "arguments": json.dumps(tool[1])},
                }
            ],
        }
    return httpx.Response(
        200,
        json={
            "id": "scripted-security",
            "object": "chat.completion",
            "created": 1,
            "model": body["model"],
            "choices": [
                {"index": 0, "finish_reason": "tool_calls" if tool else "stop", "message": message}
            ],
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 100,
                "total_tokens": 200,
                "prompt_tokens_details": {"cached_tokens": 0},
            },
        },
    )


async def queue(client, factory, monkeypatch):
    monkeypatch.setattr(settings, "investigation_api_key", "execution-test")
    saved = await saved_source(factory)
    queued = await client.post(
        f"/investigations/from-security-case/{saved['case_id']}",
        headers={"X-API-Key": "execution-test"},
    )
    assert queued.status_code == 201
    run_id = queued.json()["id"]
    assert await claim_next(factory, "scripted-worker") == run_id
    return run_id, saved


async def test_worker_delivers_security_before_provider_and_records_citations(
    client, session_factory, monkeypatch, tmp_path
):
    run_id, saved = await queue(client, session_factory, monkeypatch)
    other = payload()
    other["logs"] = {
        k: json.dumps(
            {
                **json.loads(v),
                "request_id": "other-request",
                **(
                    {"event_id": "other-auth", "account_ref": "OTHER_CASE_CANARY"}
                    if k == "auth"
                    else {}
                ),
            }
        )
        for k, v in other["logs"].items()
    }
    async with session_factory() as session:
        await save_case(session, OWNER, other, "other-case")
    wire = []

    async def provider(request):
        body = json.loads(request.content)
        wire.append(body)
        assert "OTHER_CASE_CANARY" not in request.content.decode()
        assert {t["function"]["name"] for t in body["tools"]} == {"read_security_evidence"}
        batch = json.loads(body["messages"][-1]["content"])
        assert batch["source"] == "security_case"
        auth = next(
            i
            for i in batch["items"]
            if i["kind"] == "security_event"
            and i["content"]["event_kind"] == "authentication_result"
        )
        async with session_factory() as session:
            receipts = (
                await session.scalars(
                    select(InvestigationEvent)
                    .where(InvestigationEvent.investigation_id == run_id)
                    .order_by(InvestigationEvent.sequence)
                )
            ).all()
            assert [r.kind for r in receipts] == ["tool_request", "tool_call"]
            assert receipts[1].payload["request_sequence"] == receipts[0].sequence
            assert receipts[0].payload["origin"] == "server_initial"
        report = {
            "observations": [
                {
                    "claim": "One authentication failure was recorded.",
                    "evidence_ids": [auth["evidence_id"]],
                }
            ],
            "missing_evidence": ["Account ownership and downstream access are not established."],
            "alternatives": [],
            "likely_cause": None,
            "outcome": "inconclusive",
            "suggested_checks": [],
        }
        return response(body, report)

    async with scripted_client(provider) as provider_client:
        await execute_run(session_factory, run_id, provider_client)
    async with session_factory() as session:
        run = await session.get(Investigation, run_id)
        assert run.status == "completed", run.error
        assert run.report["outcome"] == "inconclusive" and len(wire) == 1
        assert run.usage["input_tokens"] == 100
        assert run.security_case_id == saved["case_id"]
        events = (
            await session.scalars(
                select(InvestigationEvent)
                .where(InvestigationEvent.investigation_id == run_id)
                .order_by(InvestigationEvent.sequence)
            )
        ).all()
        (tmp_path / "security-run.json").write_text(
            json.dumps(
                {
                    "provider": "httpx.MockTransport",
                    "real_model_requests": 0,
                    "scripted_provider_requests": len(wire),
                    "wire": wire,
                    "source": saved,
                    "run": {
                        "id": run.id,
                        "status": run.status,
                        "report": run.report,
                        "stored_system": run.system,
                        "security_case_id": run.security_case_id,
                        "prompt_sha256": run.prompt_sha256,
                        "code_revision": run.code_revision,
                        "usage": run.usage,
                        "estimated_cost_usd": run.estimated_cost_usd,
                    },
                    "events": [
                        {"sequence": e.sequence, "kind": e.kind, "payload": e.payload}
                        for e in events
                    ],
                },
                indent=2,
            )
            + "\n"
        )


@pytest.mark.parametrize("mutation", ["report", "scope", "system", "question"])
async def test_inconsistent_binding_fails_before_provider(
    client, session_factory, monkeypatch, mutation
):
    run_id, saved = await queue(client, session_factory, monkeypatch)
    async with session_factory() as session:
        run = await session.get(Investigation, run_id)
        if mutation == "report":
            case = await session.get(SecurityCase, saved["case_id"])
            changed = copy.deepcopy(case.report)
            changed["timeline"][0]["auth_outcome"] = "success"
            case.report = changed
        else:
            setattr(
                run,
                mutation,
                {
                    "scope": {**run.scope, "services": ["other"]},
                    "system": "B",
                    "question": "different",
                }[mutation],
            )
        await session.commit()
    async with scripted_client(
        lambda request: pytest.fail("provider called on inconsistent binding")
    ) as provider_client:
        await execute_run(session_factory, run_id, provider_client)
    async with session_factory() as session:
        run = await session.get(Investigation, run_id)
        assert run.status == "failed" and run.report is None


@pytest.mark.parametrize(
    "tool,args,error",
    [
        ("query_logs", {}, "unknown_tool"),
        ("read_security_evidence", {}, "duplicate_call"),
        ("read_security_evidence", {"case_id": "other"}, "invalid_arguments"),
    ],
)
async def test_security_model_cannot_read_other_sources(
    client, session_factory, monkeypatch, tool, args, error
):
    run_id, _ = await queue(client, session_factory, monkeypatch)
    async with scripted_client(
        lambda request: response(json.loads(request.content), tool=(tool, args))
    ) as provider_client:
        await execute_run(session_factory, run_id, provider_client)
    async with session_factory() as session:
        run = await session.get(Investigation, run_id)
        assert run.status == "failed" and run.error == error


@pytest.mark.parametrize("failure,expected_executions", [("tool_request", 0), ("tool_call", 1)])
async def test_security_journal_failure_stops_before_provider(
    client, session_factory, monkeypatch, failure, expected_executions
):
    run_id, _ = await queue(client, session_factory, monkeypatch)
    record = RecordingTools._record
    read = EvidenceTools.read_security_evidence
    executed = []

    async def recording(self, kind, payload):
        if kind == failure:
            raise OSError("scripted audit failure")
        return await record(self, kind, payload)

    async def reading(self, **arguments):
        executed.append(True)
        return await read(self, **arguments)

    monkeypatch.setattr(RecordingTools, "_record", recording)
    monkeypatch.setattr(EvidenceTools, "read_security_evidence", reading)
    async with scripted_client(
        lambda request: pytest.fail("provider called after audit failure")
    ) as provider_client:
        await execute_run(session_factory, run_id, provider_client)
    assert len(executed) == expected_executions
    async with session_factory() as session:
        events = (
            await session.scalars(
                select(InvestigationEvent).where(InvestigationEvent.investigation_id == run_id)
            )
        ).all()
        assert [e.kind for e in events if e.kind != "status"] == (
            [] if failure == "tool_request" else ["tool_request"]
        )
        assert (await session.get(Investigation, run_id)).status == "failed"


@pytest.mark.parametrize(
    "mode,error",
    [("missing", "provider_not_configured"), ("outage", "provider_error"), ("cancel", None)],
)
async def test_security_missing_provider_outage_and_cancellation(
    client, session_factory, monkeypatch, mode, error
):
    run_id, _ = await queue(client, session_factory, monkeypatch)
    requests = []
    if mode == "cancel":
        async with session_factory() as session:
            run = await session.get(Investigation, run_id)
            run.status = "cancelling"
            await session.commit()

    def outage(request):
        requests.append(request)
        return httpx.Response(503)

    async with scripted_client(outage) as provider_client:
        await execute_run(session_factory, run_id, None if mode == "missing" else provider_client)
    async with session_factory() as session:
        run = await session.get(Investigation, run_id)
        assert run.status == ("cancelled" if mode == "cancel" else "failed")
        assert run.report is None and run.error == error
        assert len(requests) == (1 if mode == "outage" else 0)
        if mode == "outage":
            assert run.usage is None and run.estimated_cost_usd is None


async def test_security_intent_visible_from_independent_connection(tmp_path, monkeypatch):
    from tests.test_investigation_journal import database

    async with database(tmp_path) as (factory, observer, run_id):
        saved = await saved_source(factory)
        original = EvidenceTools.read_security_evidence

        async def read(self, **arguments):
            async with observer() as session:
                events = (await session.scalars(select(InvestigationEvent))).all()
                assert len(events) == 1 and events[0].kind == "tool_request"
                assert events[0].payload["tool"] == "read_security_evidence"
            return await original(self, **arguments)

        monkeypatch.setattr(EvidenceTools, "read_security_evidence", read)
        tools = RecordingTools(
            InvestigationScope(**saved["report"]["scope"]),
            factory,
            run_id,
            records=[],
            security_case=saved,
        )
        assert (await tools._initial_security_evidence({})).items


@pytest.mark.parametrize(
    "budget,error",
    [
        ("cost", "cost_budget"),
        ("evidence", "evidence_budget"),
        ("tools", "tool_budget"),
        ("deadline", "deadline_exceeded"),
    ],
)
async def test_security_initial_read_obeys_existing_budgets(
    session_factory, monkeypatch, budget, error
):
    from app import investigation_loop as loop
    from app.investigation_agent import MODEL, BaselineConfig

    tools = tools_for(await saved_source(session_factory))
    if budget == "evidence":
        monkeypatch.setattr(loop, "MAX_EVIDENCE_BYTES", 1)
    if budget == "tools":
        monkeypatch.setattr(loop, "MAX_TOOL_EXECUTIONS", 0)
    config = BaselineConfig(
        model=MODEL,
        max_cost_usd="0.00000001" if budget == "cost" else "0.025",
        deadline_seconds=1e-9 if budget == "deadline" else 120,
    )
    result = await loop.run_agent("Review this case", tools, None, config, dry_run=True)
    assert result["error"] == error and result["model_requests"] == 0


@pytest.mark.parametrize("mode", ["missing-auth", "ambiguous"])
async def test_security_projection_keeps_missing_and_ambiguous_outcomes(session_factory, mode):
    body = payload()
    if mode == "missing-auth":
        body["logs"]["auth"] = ""
    else:
        original = json.loads(body["logs"]["auth"])
        body["logs"]["auth"] += "\n" + json.dumps(
            {**original, "event_id": "second-auth", "outcome": "success"}
        )
    batch = await tools_for(await saved_source(session_factory, body)).read_security_evidence()
    summary = batch.items[0].content
    assert summary["confirmed_pairs"] == 0
    events = [i.content for i in batch.items if i.kind == "security_event"]
    if mode == "missing-auth":
        assert "missing_authentication_results" in summary["gaps"]
        assert events[0]["correlation"] == "unlinked"
    else:
        assert summary["ambiguous_groups"] == 1
        assert {e["correlation"] for e in events} == {"ambiguous"}
        assert {e["auth_outcome"] for e in events if "auth_outcome" in e} == {"success", "failure"}
