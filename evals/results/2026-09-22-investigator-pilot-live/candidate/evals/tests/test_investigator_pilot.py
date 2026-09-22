"""The paid boundary must reserve and capture before the real worker can act."""

import asyncio
import gzip
import importlib
import json
from pathlib import Path

import httpx
import pytest


def pilot():
    assert (
        Path(__file__).resolve().parents[1] / "investigator_pilot.py"
    ).exists(), "pilot runner missing"
    return importlib.import_module("investigator_pilot")


def response(body, *, unknown=False):
    scope = json.loads(body["messages"][1]["content"])["scope"]
    first = not any(message["role"] == "tool" for message in body["messages"])
    report = {
        "observations": [],
        "missing_evidence": ["Scripted test, not a diagnosis."],
        "alternatives": [],
        "likely_cause": None,
        "outcome": "inconclusive",
        "suggested_checks": [],
    }
    message = (
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call-1",
                    "type": "function",
                    "function": {
                        "name": "delete_logs" if unknown else "query_logs",
                        "arguments": json.dumps(scope),
                    },
                }
            ],
        }
        if first
        else {"role": "assistant", "content": json.dumps(report)}
    )
    return {
        "id": "scripted",
        "object": "chat.completion",
        "created": 1,
        "model": body["model"],
        "service_tier": "default",
        "choices": [
            {"index": 0, "finish_reason": "tool_calls" if first else "stop", "message": message}
        ],
        "usage": {"prompt_tokens": 50, "completion_tokens": 50, "total_tokens": 100},
    }


def run_mock(p, directory, handler):
    return asyncio.run(
        p.run_batch(
            directory,
            p.candidate()[1],
            key="scripted-placeholder",
            transport=httpx.MockTransport(handler),
        )
    )


def test_native_worker_reservations_witnesses_and_one_shot(tmp_path, monkeypatch):
    p = pilot()
    directory = tmp_path / "ledger"
    calls = []
    original = p.RecordingTools._record

    async def observed(self, kind, payload):
        if kind == "tool_request":
            assert len(list(directory.glob("request-*.response.json"))) == len(calls)
        return await original(self, kind, payload)

    monkeypatch.setattr(p.RecordingTools, "_record", observed)
    original_open = Path.open

    def guarded_open(path, *args, **kwargs):
        assert path.name != "reviewer-notes.jsonl", "runner read reviewer notes"
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded_open)

    def provider(request):
        number = len(calls) + 1
        assert (directory / f"request-{number:03}.reservation.json").is_file()
        body = json.loads(request.content)
        assert body["service_tier"] == "default"
        assert "STAGING_OUTSIDE_SCOPE_CANARY" not in json.dumps(body)
        calls.append(body)
        return httpx.Response(200, json=response(body))

    result = run_mock(p, directory, provider)
    assert result["reserved_attempts"] == len(calls) == 20
    assert result["usage_complete"] and result["all_cases_attempted"] and result["fatal"] is None
    for path in directory.glob("request-*.response.json"):
        assert json.loads(path.read_text())["response_saved"] is True
    for n in range(1, 11):
        saved = json.loads((directory / f"stage-{n:02}.json").read_text())
        assert saved["status"] == "completed"
        assert saved["review"]["captured_requests"] == saved["review"]["captured_calls"] == 1
        assert saved["review"]["unresolved_requests"] == []
        assert len(saved["fixture_to_database_ids"]) in (3, 4)
    with pytest.raises(FileExistsError):
        run_mock(p, directory, provider)
    assert len(calls) == 20


def test_unknown_proposals_survive_without_tool_journal_entries(tmp_path):
    p = pilot()
    result = run_mock(
        p,
        tmp_path / "ledger",
        lambda request: httpx.Response(
            200, json=response(json.loads(request.content), unknown=True)
        ),
    )
    assert result["reserved_attempts"] == 10 and result["all_cases_attempted"]
    saved = json.loads((tmp_path / "ledger/stage-01.json").read_text())
    assert saved["error"] == "unknown_tool" and saved["review"]["captured_requests"] == 0
    witness = json.loads((tmp_path / "ledger/request-001.response.json").read_text())
    assert (
        witness["response"]["choices"][0]["message"]["tool_calls"][0]["function"]["name"]
        == "delete_logs"
    )


@pytest.mark.parametrize(
    "failure", ["http", "timeout", "usage", "total", "model", "token_bound", "cached", "tier"]
)
def test_ambiguous_failures_stop_without_retry(tmp_path, failure):
    p = pilot()
    calls = []

    def provider(request):
        calls.append(True)
        if failure == "timeout":
            raise httpx.ReadTimeout("scripted timeout")
        if failure == "http":
            return httpx.Response(
                401, json={"error": {"message": "scripted-placeholder", "code": "invalid_api_key"}}
            )
        data = response(json.loads(request.content))
        if failure == "usage":
            data["usage"] = None
        if failure == "total":
            data["usage"]["total_tokens"] = 101
        if failure == "model":
            data["model"] = "unapproved-model"
        if failure == "cached":
            data["usage"]["prompt_tokens_details"] = {"cached_tokens": 51}
        if failure == "tier":
            data["service_tier"] = "priority"
        if failure == "token_bound":
            data["usage"] = {
                "prompt_tokens": 999999,
                "completion_tokens": 50,
                "total_tokens": 1000049,
            }
        return httpx.Response(200, json=data)

    result = run_mock(p, tmp_path / "ledger", provider)
    assert len(calls) == result["reserved_attempts"] == 1
    assert result["fatal"] and not result["all_cases_attempted"]
    assert result["cases"]["stage-02"] == "not_run"
    if failure in {"http", "timeout", "usage", "total"}:
        assert not result["usage_complete"]
    assert "scripted-placeholder" not in "".join(
        path.read_text() for path in (tmp_path / "ledger").glob("request-*.json")
    )


@pytest.mark.parametrize("suffix,sent", [("reservation.json", 0), ("response.json", 1)])
def test_write_failure_prevents_later_execution(tmp_path, monkeypatch, suffix, sent):
    p = pilot()
    original = p.save
    calls = []

    def failing_save(path, value):
        if path.name.endswith(suffix):
            raise OSError("injected write failure")
        return original(path, value)

    monkeypatch.setattr(p, "save", failing_save)

    def provider(request):
        calls.append(True)
        return httpx.Response(200, json=response(json.loads(request.content)))

    result = run_mock(p, tmp_path / "ledger", provider)
    assert len(calls) == sent and result["fatal"]
    saved = json.loads((tmp_path / "ledger/stage-01.json").read_text())
    assert saved["review"]["captured_requests"] == 0


def test_changed_candidate_and_invalid_key_do_not_claim_ledger(tmp_path):
    p = pilot()
    for digest, key in [("changed", "scripted-placeholder"), (p.candidate()[1], "bad\x1bkey")]:
        with pytest.raises(ValueError):
            asyncio.run(
                p.run_batch(
                    tmp_path / "ledger",
                    digest,
                    key=key,
                    transport=httpx.MockTransport(lambda r: None),
                )
            )
        assert not (tmp_path / "ledger").exists()


def test_dirty_live_runner_refuses_before_claim(tmp_path, monkeypatch):
    p = pilot()
    monkeypatch.setattr(p, "clean_worktree", lambda: False)
    with pytest.raises(ValueError, match="clean committed"):
        asyncio.run(
            p.run_batch(
                tmp_path / "ledger", p.candidate()[1], key="scripted-placeholder", allow_live=True
            )
        )
    assert not (tmp_path / "ledger").exists()


def test_reservation_limits(tmp_path):
    p = pilot()
    transport = p.RecordingTransport(
        tmp_path, httpx.MockTransport(lambda r: None), p.candidate()[1]
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
    raw = json.dumps(body).encode()
    for n in range(1, 11):
        transport.case_id = f"stage-{n:02}"
        for _ in range(6):
            transport.reserve(raw)
        with pytest.raises(ValueError):
            transport.reserve(raw)
    assert len(transport.records) == 60
    with pytest.raises(ValueError):
        transport.reserve(raw)


@pytest.mark.parametrize(
    "changes",
    [
        {"model": "other"},
        {"max_completion_tokens": 2048},
        {"store": True},
        {"service_tier": "priority"},
    ],
)
def test_envelope_rejected_with_unused_allowance(tmp_path, changes):
    p = pilot()
    transport = p.RecordingTransport(
        tmp_path, httpx.MockTransport(lambda r: None), p.candidate()[1]
    )
    transport.case_id = "stage-01"
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
    with pytest.raises(ValueError):
        transport.reserve(json.dumps({**body, **changes}).encode())
    assert transport.records == []


def test_decoded_gzip_response_is_not_decoded_twice(tmp_path):
    p = pilot()

    def provider(request):
        return httpx.Response(
            200,
            headers={"content-encoding": "gzip"},
            content=gzip.compress(json.dumps(response(json.loads(request.content))).encode()),
        )

    result = run_mock(p, tmp_path / "ledger", provider)
    assert result["fatal"] is None and result["reserved_attempts"] == 20
    assert all(status == "completed" for status in result["cases"].values())


def test_candidate_drift_stops_before_second_send(tmp_path, monkeypatch):
    p = pilot()
    original = p.candidate
    calls = []

    def provider(request):
        calls.append(True)
        manifest, _ = original()
        monkeypatch.setattr(p, "candidate", lambda: (manifest, "changed"))
        return httpx.Response(200, json=response(json.loads(request.content)))

    result = run_mock(p, tmp_path / "ledger", provider)
    assert len(calls) == result["reserved_attempts"] == 1
    assert result["fatal"] and result["cases"]["stage-02"] == "not_run"
    saved = json.loads((tmp_path / "ledger/stage-01.json").read_text())
    assert saved["review"]["captured_requests"] == 0


def test_body_and_money_ceiling_before_reservation(tmp_path):
    p = pilot()
    transport = p.RecordingTransport(
        tmp_path, httpx.MockTransport(lambda r: None), p.candidate()[1]
    )
    transport.case_id = "stage-01"
    with pytest.raises(ValueError):
        transport.reserve(b"x" * (p.MAX_BODY + 1))
    body = {
        "model": p.MODEL,
        "messages": ["x" * 120000],
        "tools": [],
        "response_format": {},
        "temperature": 0,
        "store": False,
        "max_completion_tokens": 1024,
        "service_tier": "default",
    }
    raw = json.dumps(body).encode()
    transport.reserve(raw)
    with pytest.raises(ValueError, match="allowance"):
        transport.reserve(raw)
    assert len(transport.records) == 1


@pytest.mark.parametrize("escaped", [False, True])
def test_credential_echo_is_never_archived(tmp_path, escaped):
    p = pilot()

    def provider(request):
        data = response(json.loads(request.content))
        data["choices"][0]["message"]["content"] = "scripted-placeholder"
        raw = json.dumps(data)
        if escaped:
            raw = raw.replace("scripted-placeholder", "\\u0073cripted-placeholder")
        return httpx.Response(200, content=raw)

    result = run_mock(p, tmp_path / "ledger", provider)
    assert result["fatal"] and result["reserved_attempts"] == 1
    assert "scripted-placeholder" not in "".join(
        path.read_text() for path in (tmp_path / "ledger").glob("request-*.json")
    )
