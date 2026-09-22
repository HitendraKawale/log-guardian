"""Initial evidence must obey the same bounds and fail before any provider request."""

import asyncio

import pytest
from app import investigation_loop as loop
from app.investigation_agent import MODEL, BaselineConfig, run_investigation
from app.investigation_schemas import EvidenceBatch, InvestigationScope
from app.investigation_tools import MAX_RESULT_BYTES, EvidenceTools

from tests.test_investigation_loop import SCOPE, exercise, reply


@pytest.mark.parametrize("message_size", [20, 4000])
async def test_initial_sample_retains_row_and_byte_truncation(message_size):
    records = [
        {
            "evidence_id": f"bounded:{n}",
            "service": "gateway",
            "level": "ERROR",
            "timestamp": "2026-01-01T10:03:00Z",
            "message": "x" * message_size,
        }
        for n in range(51)
    ]
    result, requests = await exercise(lambda *_: reply(), records=records)
    batch = result["trace"][0]["result"]
    assert result["status"] == "completed" and len(requests) == 1
    assert batch["truncated"] is True
    assert len(batch["items"]) == 50 if message_size == 20 else len(batch["items"]) < 50
    assert len(EvidenceBatch.model_validate(batch).model_dump_json().encode()) <= MAX_RESULT_BYTES
    assert result["tool_executions"] == 1


async def test_initial_source_error_is_delivered_without_inventing_absence(monkeypatch):
    async def unavailable(self, **arguments):
        return EvidenceBatch(source="replay", error="source_unavailable")

    monkeypatch.setattr(EvidenceTools, "query_logs", unavailable)
    result, requests = await exercise(lambda *_: reply())
    assert result["trace"][0]["result"]["error"] == "source_unavailable"
    assert '"source_unavailable"' in requests[0]["messages"][-1]["content"]


async def test_missing_provider_does_not_read_initial_evidence(monkeypatch):
    async def forbidden(self, **arguments):
        raise AssertionError("unconfigured run must not read")

    monkeypatch.setattr(EvidenceTools, "query_logs", forbidden)
    result = await run_investigation(
        "C",
        "Investigate",
        EvidenceTools(InvestigationScope(**SCOPE), records=[]),
        None,
        BaselineConfig(model=MODEL, max_cost_usd=".10"),
    )
    assert result["error"] == "provider_not_configured"
    assert result["tool_executions"] == result["model_requests"] == 0


@pytest.mark.parametrize("dry_run", [False, True])
async def test_initial_read_is_inside_deadline(monkeypatch, dry_run):
    async def slow(self, **arguments):
        await asyncio.sleep(0.1)
        return EvidenceBatch(source="replay")

    monkeypatch.setattr(EvidenceTools, "query_logs", slow)
    result = await run_investigation(
        "C",
        "Investigate",
        EvidenceTools(InvestigationScope(**SCOPE), records=[]),
        object(),
        BaselineConfig(model=MODEL, max_cost_usd=".10", deadline_seconds=0.01),
        dry_run=dry_run,
    )
    assert result["error"] == "deadline_exceeded" and result["model_requests"] == 0


async def test_initial_read_counts_against_tool_budget(monkeypatch):
    monkeypatch.setattr(loop, "MAX_TOOL_EXECUTIONS", 0)
    result, requests = await exercise(lambda *_: reply())
    assert result["error"] == "tool_budget" and result["tool_executions"] == 0 and requests == []
