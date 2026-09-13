"""Exercise the real SDK through HTTPX transport doubles, never paid requests."""

import asyncio
import json

import httpx
import pytest
from app.investigation_agent import BaselineConfig, run_baseline
from app.investigation_schemas import InvestigationScope
from app.investigation_tools import EvidenceTools
from openai import AsyncOpenAI

MODEL = "gpt-4.1-mini-2025-04-14"
SCOPE = {"services": ["checkout"], "start": "2026-01-01T10:00:00Z", "end": "2026-01-01T10:10:00Z"}


def tools(records=True):
    return EvidenceTools(
        InvestigationScope(**SCOPE),
        records=[
            {
                "evidence_id": "case:1",
                "service": "checkout",
                "level": "ERROR",
                "message": "upstream timeout; API_KEY=fixture-key",
                "timestamp": SCOPE["start"],
            }
        ]
        if records
        else [],
    )


def report():
    finding = {"claim": "An upstream timeout occurred.", "evidence_ids": ["case:1"]}
    return {
        "outcome": "supported",
        "observations": [finding],
        "likely_cause": finding,
        "alternatives": [],
        "missing_evidence": [],
        "suggested_checks": ["Inspect upstream timing."],
    }


def completion(body=None):
    return {
        "id": "chatcmpl-scripted",
        "object": "chat.completion",
        "created": 1,
        "model": MODEL,
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {
                    "role": "assistant",
                    "content": json.dumps(body if body is not None else report()),
                },
            }
        ],
        "usage": {
            "prompt_tokens": 100,
            "completion_tokens": 20,
            "total_tokens": 120,
            "prompt_tokens_details": {"cached_tokens": 40},
        },
    }


def config(**updates):
    return BaselineConfig(**{"model": MODEL, "max_cost_usd": "0.10", "mode": "scripted", **updates})


async def execute(payload, *, system="A", source=None, settings=None, status=200):
    requests = []

    async def handle(request):
        requests.append(json.loads(request.content))
        return httpx.Response(status, json=payload)

    async with AsyncOpenAI(
        api_key="scripted-placeholder",
        http_client=httpx.AsyncClient(
            transport=httpx.MockTransport(handle),
        ),
    ) as client:
        result = await run_baseline(
            system,
            "Why the upstream timeout? token=fixture-question",
            source or tools(),
            client,
            settings or config(),
        )
    return result, requests


@pytest.mark.parametrize(
    "system,names",
    [("A", ["query_logs"]), ("B", ["query_logs", "summarize_logs", "search_runbooks"])],
)
async def test_baselines_use_fixed_tools_one_sdk_request_and_strict_reports(system, names):
    result, requests = await execute(completion(), system=system)
    assert result["status"] == "completed" and result["mode"] == "scripted"
    assert [event["tool"] for event in result["trace"]] == names
    assert len(requests) == result["model_requests"] == 1
    assert requests[0]["model"] == MODEL
    assert requests[0]["max_completion_tokens"] == 1024
    assert requests[0]["temperature"] == result["parameters"]["temperature"] == 0
    assert requests[0]["response_format"]["json_schema"]["strict"] is True
    assert len([m for m in requests[0]["messages"] if m["role"] == "tool"]) == len(names)
    assert result["usage"] == {"input_tokens": 100, "output_tokens": 20, "cached_input_tokens": 40}
    assert result["estimated_cost_usd"] == "0.00006000"
    assert result["elapsed_ms"] >= 0 and len(result["prompt_sha256"]) == 64
    serialized = json.dumps([result, requests])
    assert "fixture-key" not in serialized and "fixture-question" not in serialized
    assert "[REDACTED]" in serialized


@pytest.mark.parametrize(
    "change",
    ["invented", "runbook_only", "no_cause", "inconclusive_cause", "no_missing", "empty_claim"],
)
async def test_invalid_reports_fail_without_losing_usage(change):
    body = report()
    if change == "invented":
        body["observations"][0]["evidence_ids"] = ["invented:1"]
    elif change == "runbook_only":
        body["likely_cause"] = {"claim": "Timeout", "evidence_ids": ["runbook:timeouts"]}
    elif change == "no_cause":
        body["likely_cause"] = None
    elif change == "inconclusive_cause":
        body["outcome"] = "inconclusive"
        body["missing_evidence"] = ["Upstream logs"]
    elif change == "no_missing":
        body.update(outcome="inconclusive", likely_cause=None)
    else:
        body["observations"][0]["claim"] = " "
    result, _ = await execute(completion(body), system="B")
    assert result["status"] == "failed" and result["error"] == "invalid_report"
    assert result["report"] is None and result["usage"]["input_tokens"] == 100


async def test_empty_evidence_can_produce_explicit_inconclusive_report():
    body = {
        "outcome": "inconclusive",
        "observations": [],
        "likely_cause": None,
        "alternatives": [],
        "missing_evidence": ["Upstream logs"],
        "suggested_checks": [],
    }
    result, _ = await execute(completion(body), source=tools(False))
    assert result["status"] == "completed"
    assert result["report"]["outcome"] == "inconclusive"


@pytest.mark.parametrize("status", [401, 429, 500])
async def test_provider_errors_are_not_retried_and_have_unknown_usage(status):
    result, requests = await execute({"error": {"message": "token=fixture-error"}}, status=status)
    assert len(requests) == 1
    assert result["error"] == "provider_error" and result["usage"] is None
    assert result["estimated_cost_usd"] is None
    assert "fixture-error" not in json.dumps(result)
    assert result["trace"]


@pytest.mark.parametrize("variant", ["refusal", "length", "json", "model"])
async def test_unusable_completions_preserve_usage_but_not_raw_output(variant):
    response = completion()
    if variant == "refusal":
        response["choices"][0]["message"].update(content=None, refusal="token=fixture-refusal")
    elif variant == "length":
        response["choices"][0]["finish_reason"] = "length"
    elif variant == "json":
        response["choices"][0]["message"]["content"] = "malformed token=fixture-response"
    else:
        response["model"] = "unexpected-model"
    result, _ = await execute(response)
    assert result["status"] == "failed" and result["report"] is None
    assert result["usage"]["input_tokens"] == 100
    assert "fixture-response" not in json.dumps(result)
    assert "fixture-refusal" not in json.dumps(result)


@pytest.mark.parametrize("payload", [{}, {"model": MODEL}, []])
async def test_malformed_success_response_fails_closed(payload):
    result, requests = await execute(payload)
    assert len(requests) == 1
    assert result["status"] == "failed" and result["report"] is None
    assert result["error"] == "invalid_response" and result["usage"] is None


async def test_reported_spend_over_allowance_is_not_accepted():
    response = completion()
    response["usage"].update(completion_tokens=100000, total_tokens=100100)
    result, _ = await execute(response)
    assert result["error"] == "cost_budget" and result["report"] is None
    assert result["estimated_cost_usd"] == "0.16002800"


async def test_missing_usage_is_unknown_not_free():
    response = completion()
    response.pop("usage")
    result, _ = await execute(response)
    assert result["status"] == "completed"
    assert result["usage"] is None and result["estimated_cost_usd"] is None


async def test_budget_preflight_and_dry_run_make_no_provider_request():
    for settings, dry_run in [(config(max_cost_usd="0.00000001"), False), (config(), True)]:
        result = await run_baseline("B", "Why timeout?", tools(), None, settings, dry_run=dry_run)
        assert result["model_requests"] == 0
        assert result["status"] == ("dry_run" if dry_run else "failed")
        assert result["estimated_cost_usd"] == "0.00000000"
        assert result["trace"]


async def test_deadline_cancels_sdk_request_and_retains_partial_evidence():
    async def handle(request):
        await asyncio.Event().wait()

    async with AsyncOpenAI(
        api_key="scripted-placeholder",
        http_client=httpx.AsyncClient(
            transport=httpx.MockTransport(handle),
        ),
    ) as client:
        result = await run_baseline(
            "A", "Why timeout?", tools(), client, config(deadline_seconds=0.02)
        )
    assert result["error"] == "deadline_exceeded" and result["model_requests"] == 1
    assert result["usage"] is None and result["trace"]


@pytest.mark.parametrize(
    "updates",
    [
        {"model": "gpt-4.1-mini"},
        {"max_cost_usd": "NaN"},
        {"max_cost_usd": "0"},
        {"deadline_seconds": 121},
    ],
)
def test_explicit_snapshot_and_finite_positive_limits(updates):
    with pytest.raises(ValueError):
        config(**updates)
