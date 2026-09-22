"""Inspect the actual first SDK request and journal using synthetic data only."""

import asyncio
import json
from pathlib import Path

import httpx
import investigator_pilot as pilot
import pytest
from openai import AsyncOpenAI
from validate import load_cases

CASES = Path(__file__).resolve().parents[1] / "investigator-security/cases.jsonl"


@pytest.mark.parametrize("index", range(10))
def test_first_request_contains_scoped_fixture_before_model_choice(index, tmp_path):
    case = load_cases(CASES)[index]
    requests = []

    def provider(request):
        body = json.loads(request.content)
        requests.append(body)
        evidence = [message for message in body["messages"] if message["role"] == "tool"]
        assert len(evidence) == 1
        batch = json.loads(evidence[0]["content"])
        assert not batch["truncated"] and batch["error"] is None
        assert {item["content"]["message"] for item in batch["items"]} == {
            row["message"] for row in case["logs"]
        }
        assert "STAGING_OUTSIDE_SCOPE_CANARY" not in json.dumps(body)
        for row in case["logs"]:
            assert row["message"] not in body["messages"][0]["content"]
        arguments = json.loads(body["messages"][-2]["tool_calls"][0]["function"]["arguments"])
        assert arguments["text"] is None and arguments["limit"] == 50
        assert arguments["services"] == case["scope"]["services"]
        report = {
            "observations": [],
            "missing_evidence": ["Scripted check, not a diagnosis."],
            "alternatives": [],
            "likely_cause": None,
            "outcome": "inconclusive",
            "suggested_checks": [],
        }
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
                        "message": {"role": "assistant", "content": json.dumps(report)},
                    }
                ],
                "usage": {"prompt_tokens": 50, "completion_tokens": 50, "total_tokens": 100},
            },
        )

    async def run():
        async with AsyncOpenAI(
            api_key="scripted-placeholder",
            max_retries=0,
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(provider)),
        ) as client:
            return await pilot.execute_case(tmp_path, case, client)

    result = asyncio.run(run())
    assert result["status"] == "completed" and len(requests) == 1
    assert [event["sequence"] for event in result["events"]] == [1, 2, 1000000]
    for event in result["events"][:2]:
        assert event["payload"]["origin"] == "server_initial"
    assert result["events"][1]["payload"]["request_sequence"] == 1


@pytest.mark.parametrize("stop", ["tool_request", "tool_call", "cancel"])
def test_initial_recording_failure_or_cancellation_prevents_model(tmp_path, monkeypatch, stop):
    case = load_cases(CASES)[0]
    calls = []
    original_record = pilot.RecordingTools._record
    original_cancel = pilot.RecordingTools._cancelling

    async def recording(self, kind, payload):
        if kind == stop:
            raise OSError("injected initial event write failure")
        return await original_record(self, kind, payload)

    async def cancelling(self):
        async with self._factory() as session:
            run = await session.get(pilot.Investigation, self._run_id)
            run.status = "cancelling"
            await session.commit()
        return await original_cancel(self)

    monkeypatch.setattr(pilot.RecordingTools, "_record", recording)
    if stop == "cancel":
        monkeypatch.setattr(pilot.RecordingTools, "_cancelling", cancelling)

    def provider(request):
        calls.append(request)
        raise AssertionError("no provider call after initial failure")

    async def run():
        async with AsyncOpenAI(
            api_key="scripted-placeholder",
            max_retries=0,
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(provider)),
        ) as client:
            return await pilot.execute_case(tmp_path, case, client)

    result = asyncio.run(run())
    assert calls == []
    assert result["status"] == ("cancelled" if stop == "cancel" else "failed")
    assert result["review"]["captured_calls"] == 0
    assert result["review"]["captured_requests"] == (1 if stop == "tool_call" else 0)
    assert len(result["review"]["unresolved_requests"]) == (1 if stop == "tool_call" else 0)
