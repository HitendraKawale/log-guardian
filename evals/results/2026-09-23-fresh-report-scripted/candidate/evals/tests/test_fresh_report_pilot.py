"""Exercise the new batch through the existing transport without reading grading files."""

import asyncio
import importlib
import json
from pathlib import Path

import httpx
import pytest


def fresh():
    assert (Path(__file__).resolve().parents[1] / "fresh_report_pilot.py").exists()
    return importlib.import_module("fresh_report_pilot")


def test_fresh_batch_configuration_restores_consumed_batch():
    f = fresh()
    old = f.p.AUTHORIZATION
    with f.configured() as p:
        manifest, _ = p.candidate()
        assert manifest["authorization"] == "fresh-report-grounding-2026-09-23"
        assert manifest["max_requests"] == 72 and len(manifest["case_ids"]) == 12
        assert manifest["frozen_production_candidate"] == f.CANDIDATE_SHA
        assert manifest["frozen_corpus"] == f.CORPUS_SHA
        assert p.shared_ledger().name == manifest["authorization"]
        assert not any(
            Path(name).name
            in {"labels.jsonl", "rubric.md", "pairs.json", "provenance.md", "build.py"}
            for name in manifest["files"]
        )
    assert f.p.AUTHORIZATION == old


def test_fresh_batch_real_worker_and_input_separation(tmp_path, monkeypatch):
    f = fresh()
    original = Path.open

    def guarded(path, *args, **kwargs):
        assert path.name not in {
            "labels.jsonl",
            "rubric.md",
            "pairs.json",
            "provenance.md",
            "build.py",
            "expected-reports.json",
        }
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded)
    calls = []

    def provider(request):
        body = json.loads(request.content)
        calls.append(body)
        assert "STAGING_OUTSIDE_SCOPE_CANARY" not in json.dumps(body)
        batches = [json.loads(m["content"]) for m in body["messages"] if m["role"] == "tool"]
        assert len(batches) == 1 and not batches[0]["truncated"]
        expected = cases[len(calls) - 1]
        assert {item["content"]["message"] for item in batches[0]["items"]} == {
            row["message"] for row in expected["logs"]
        }
        assert len(batches[0]["items"]) == len(expected["logs"])
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
                "service_tier": "default",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": json.dumps(report)},
                    }
                ],
                "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
            },
        )

    with f.configured() as p:
        cases = p.load_cases(p.ROOT / p.CASE_FILE)
        sha = p.candidate()[1]
        result = asyncio.run(
            p.run_batch(
                tmp_path / "ledger",
                sha,
                key="scripted-placeholder",
                transport=httpx.MockTransport(provider),
            )
        )
        assert result["all_cases_attempted"] and result["fatal"] is None
        assert result["reserved_attempts"] == len(calls) == 12
        assert all(s == "completed" for s in result["cases"].values())
        for case_id in p.CASE_IDS:
            case = json.loads((tmp_path / "ledger" / f"{case_id}.json").read_bytes())
            assert case["review"]["captured_requests"] == case["review"]["captured_calls"] == 1
            assert case["events"][0]["payload"]["origin"] == "server_initial"
        with pytest.raises(FileExistsError):
            asyncio.run(
                p.run_batch(
                    tmp_path / "ledger",
                    sha,
                    key="scripted-placeholder",
                    transport=httpx.MockTransport(provider),
                )
            )
        assert len(calls) == 12


def test_seventy_two_reservations_then_stop(tmp_path):
    f = fresh()
    with f.configured() as p:
        recorder = p.RecordingTransport(
            tmp_path, httpx.MockTransport(lambda _: None), p.candidate()[1]
        )
        body = {
            "model": p.MODEL,
            "messages": [],
            "tools": [],
            "response_format": {},
            "temperature": 0,
            "store": False,
            "max_completion_tokens": 1024,
            "service_tier": "default",
        }
        for identity in p.CASE_IDS:
            recorder.case_id = identity
            for _ in range(6):
                recorder.reserve(json.dumps(body).encode())
            with pytest.raises(ValueError, match="allowance"):
                recorder.reserve(json.dumps(body).encode())
        assert len(recorder.records) == 72


@pytest.mark.parametrize(
    "changed", ["app/investigation_agent.py", "fresh-case-authoring/cases.jsonl"]
)
def test_frozen_production_drift_refuses_before_ledger(tmp_path, monkeypatch, changed):
    f = fresh()
    original = Path.read_bytes

    def drift(path):
        if str(path).endswith(changed):
            return b"changed"
        return original(path)

    with f.configured() as p:
        monkeypatch.setattr(Path, "read_bytes", drift)
        with pytest.raises(ValueError, match="frozen production|authorized case bytes"):
            asyncio.run(
                p.run_batch(
                    tmp_path / "ledger",
                    "unused",
                    key="scripted-placeholder",
                    transport=httpx.MockTransport(lambda _: None),
                )
            )
    assert not (tmp_path / "ledger").exists()
