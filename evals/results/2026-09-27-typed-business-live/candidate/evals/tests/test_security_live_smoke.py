"""The approved batch must fail closed before money or source boundaries can expand."""

import hashlib
import json
from decimal import Decimal

import httpx
import pytest
import security_live_smoke as s


def response(request):
    body = json.loads(request.content)
    assert [t["function"]["name"] for t in body["tools"]] == ["read_security_evidence"]
    assert body["service_tier"] == "default"
    report = {"focus_evidence_ids": [], "hypothesis_codes": [], "check_codes": []}
    return httpx.Response(
        200,
        json={
            "id": "mock",
            "object": "chat.completion",
            "created": 1,
            "model": s.p.MODEL,
            "service_tier": "default",
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": json.dumps(report)},
                }
            ],
            "usage": {"prompt_tokens": 100, "completion_tokens": 100, "total_tokens": 200},
        },
    )


@pytest.mark.asyncio
async def test_real_routes_worker_capture_and_single_use(tmp_path, monkeypatch):
    output = tmp_path / "batch"
    native, sent = [], []
    original = s.p.RecordingTransport.handle_async_request

    async def observe(self, request):
        native.append(json.loads(await request.aread()))
        return await original(self, request)

    monkeypatch.setattr(s.p.RecordingTransport, "handle_async_request", observe)

    def provider(request):
        reservations = list(output.glob("*.reservation.json"))
        assert reservations
        prior = sorted(output.glob("*.response.json"))
        assert len(reservations) == len(prior) + 1
        sent.append(request.content)
        return response(request)

    result = await s.run_batch(output, s.manifest()[1], transport=httpx.MockTransport(provider))
    assert result["cases"] == dict.fromkeys(s.CASE_IDS, "completed")
    assert result["attempts"] == 4 and result["usage_complete"] and result["allowance_closed"]
    assert Decimal(result["reserved_usd"]) <= Decimal("0.10")
    assert len(native) == len(sent) == 4
    for number, (body, wire) in enumerate(zip(native, sent, strict=True), 1):
        # Compare serialization, not dict equality: nested property order matters.
        body["service_tier"] = "default"
        assert json.dumps(json.loads(wire), ensure_ascii=False) == json.dumps(
            body, ensure_ascii=False
        )
        reservation = json.loads((output / f"request-{number:03}.reservation.json").read_bytes())
        assert reservation["request_json"].encode() == wire
        assert reservation["request_sha256"] == hashlib.sha256(wire).hexdigest()
        assert reservation["request"] == json.loads(wire)
    for identity in s.CASE_IDS:
        case = json.loads((output / f"{identity}.json").read_bytes())
        events = case["events"]
        assert events[0]["kind"] == "tool_request"
        assert events[1]["payload"]["request_sequence"] == events[0]["sequence"]
        assert events[1]["payload"]["tool"] == "read_security_evidence"
        assert case["run"]["security_case_id"] == case["saved_case"]["id"]
    with pytest.raises(FileExistsError):
        await s.run_batch(output, s.manifest()[1], transport=httpx.MockTransport(provider))


@pytest.mark.asyncio
async def test_provider_failure_stops_without_retry(tmp_path):
    requests = []

    def unavailable(request):
        requests.append(request)
        return httpx.Response(503)

    output = tmp_path / "failed"
    result = await s.run_batch(output, s.manifest()[1], transport=httpx.MockTransport(unavailable))
    assert len(requests) == 1 and result["attempts"] == 1 and result["fatal"]
    assert result["cases"]["smoke-02"] == "not_run"
    assert not result["usage_complete"]
    assert list(output.glob("*.failure.json"))
    assert Decimal(result["reserved_usd"]) > 0


def test_batch_caps_and_foreign_cases_cannot_reserve(tmp_path):
    with s.configured():
        transport = s.p.RecordingTransport(tmp_path, httpx.MockTransport(response), s.manifest()[1])
        body = {
            "model": s.p.MODEL,
            "messages": [],
            "tools": [],
            "response_format": {},
            "temperature": 0,
            "store": False,
            "max_completion_tokens": 1024,
            "service_tier": "default",
        }
        transport.case_id = "foreign"
        with pytest.raises(ValueError):
            transport.reserve(s.p.canonical(body))
        transport.case_id = "smoke-01"
        for _ in range(6):
            transport.reserve(s.p.canonical(body))
        with pytest.raises(ValueError):
            transport.reserve(s.p.canonical(body))
        transport.case_id = "smoke-02"
        body["messages"] = [{"role": "user", "content": "x" * 60000}]
        with pytest.raises(ValueError):
            transport.reserve(s.p.canonical(body))
        assert len(transport.records) == 6


@pytest.mark.asyncio
async def test_mock_rehearsal_allows_source_changes_but_live_still_checks_base(
    tmp_path, monkeypatch
):
    original = s.subprocess.run

    def changed_source(command, *args, **kwargs):
        if command[:2] == ["git", "diff"]:
            raise s.subprocess.CalledProcessError(1, command)
        return original(command, *args, **kwargs)

    def forbidden_network(**kwargs):
        pytest.fail("changed production source reached live transport construction")

    monkeypatch.setattr(s.subprocess, "run", changed_source)
    result = await s.run_batch(
        tmp_path / "offline", s.manifest()[1], transport=httpx.MockTransport(response)
    )
    assert result["cases"] == dict.fromkeys(s.CASE_IDS, "completed")
    monkeypatch.setattr(s.p, "clean_worktree", lambda: True)
    target = tmp_path / "live"
    monkeypatch.setattr(s, "ledger", lambda: target)
    monkeypatch.setattr(s.httpx, "AsyncHTTPTransport", forbidden_network)
    with pytest.raises(s.subprocess.CalledProcessError):
        await s.run_batch(target, s.manifest()[1], live=True, key="not-a-real-key")
    assert not target.exists()


@pytest.mark.asyncio
async def test_frozen_digest_and_live_gate(tmp_path):
    with pytest.raises(ValueError, match="frozen"):
        await s.run_batch(tmp_path / "changed", "wrong", transport=httpx.MockTransport(response))
    with pytest.raises(ValueError, match="live run requires"):
        await s.run_batch(
            tmp_path / "wrong-ledger", s.manifest()[1], live=True, key="not-a-real-key"
        )
