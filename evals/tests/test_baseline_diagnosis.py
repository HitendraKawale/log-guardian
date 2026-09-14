"""Reconstruct dev-06 at the SDK boundary without contacting the provider.

These checks rule out outcome coercion and missing input in the local runner.
They do not demonstrate that a live model will choose to abstain.
"""

import asyncio
import json
import sys
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services/ingestion-service"))

from app.investigation_agent import PROMPT, BaselineConfig, run_baseline  # noqa: E402
from app.investigation_schemas import InvestigationScope  # noqa: E402
from app.investigation_tools import EvidenceTools  # noqa: E402
from openai import AsyncOpenAI  # noqa: E402
from validate import load_cases  # noqa: E402


@pytest.mark.parametrize("system", ["A", "B"])
def test_real_case_transports_evidence_and_accepts_inconclusive(system):
    case = next(c for c in load_cases(ROOT / "evals/cases/dev.jsonl") if c["case_id"] == "dev-06")
    archived = json.loads(
        (ROOT / (f"evals/results/2026-09-13-baseline-smoke-v2/dev-06-{system}.json")).read_text()
    )
    answer = {
        "outcome": "inconclusive",
        "observations": [
            {"claim": "Gateway requests timed out.", "evidence_ids": ["dev-06:01", "dev-06:02"]}
        ],
        "likely_cause": None,
        "alternatives": [],
        "missing_evidence": ["Search-side logs or traces and upstream timing."],
        "suggested_checks": ["Inspect search-side request traces."],
    }
    captured = []

    async def handle(request):
        body = json.loads(request.content)
        captured.append(body)
        return httpx.Response(
            200,
            json={
                "id": "diagnostic-scripted",
                "object": "chat.completion",
                "created": 1,
                "model": body["model"],
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": json.dumps(answer)},
                    }
                ],
                "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
            },
        )

    async def exercise():
        tools = EvidenceTools(InvestigationScope(**case["scope"]), records=case["logs"])
        async with AsyncOpenAI(
            api_key="scripted-placeholder",
            http_client=httpx.AsyncClient(
                transport=httpx.MockTransport(handle),
            ),
        ) as client:
            return await run_baseline(
                system,
                case["question"],
                tools,
                client,
                BaselineConfig(
                    model=archived["model_requested"],
                    max_cost_usd="0.025",
                    mode="scripted",
                ),
            )

    result = asyncio.run(exercise())
    assert len(captured) == 1
    body = captured[0]
    schema = body["response_format"]["json_schema"]["schema"]["properties"]
    assert list(schema) == [
        "observations",
        "missing_evidence",
        "alternatives",
        "likely_cause",
        "outcome",
        "suggested_checks",
    ]
    assert set(schema["outcome"]["enum"]) == {"supported", "inconclusive"}
    assert {"type": "null"} in schema["likely_cause"]["anyOf"]
    assert body["messages"][0] == {"role": "system", "content": PROMPT}
    assert "Missing telemetry is not evidence of an application failure" in PROMPT
    question = json.loads(body["messages"][1]["content"])
    assert question["question"] == case["question"]
    assert set(question["scope"]["services"]) == {"gateway", "collector"}
    evidence = [json.loads(m["content"]) for m in body["messages"] if m["role"] == "tool"]
    assert evidence == [event["result"] for event in archived["trace"]]
    assert result["mode"] == "scripted" and result["status"] == "completed"
    assert result["report"] == answer
    # This fingerprint includes the schema; reordering changes it without changing PROMPT.
    assert result["prompt_sha256"] != archived["prompt_sha256"]
