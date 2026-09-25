"""Prove offline transport behavior with fake HTTP, not paid model execution."""

import asyncio
import base64
import gzip
import importlib
import json
import socket
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

EVALS = Path(__file__).resolve().parents[1]
SCRIPTED = EVALS / "results/report-verifier-offline-runner-verified/scripted-responses"


def adapter():
    assert (EVALS / "report_verifier_transport.py").exists(), "transport adapter missing"
    return importlib.import_module("report_verifier_transport")


def answer(request):
    body = json.loads(request.content)
    item = json.loads(body["messages"][1]["content"])
    return {
        "model": body["model"],
        "service_tier": "default",
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {
                    "role": "assistant",
                    "content": (SCRIPTED / f'{item["item_id"]}.json').read_text(),
                },
            }
        ],
        "usage": {
            "prompt_tokens": 1000,
            "completion_tokens": 800,
            "total_tokens": 1800,
            "prompt_tokens_details": {"cached_tokens": 200},
        },
    }


def test_wire_preserves_schema_and_messages(tmp_path):
    m = adapter()
    manifest = m.prepare(tmp_path / "wire")
    assert len(manifest["eligible"]) == 17
    assert not (tmp_path / "wire/requests/v13.json").exists()
    from report_verifier_eval import preparation

    files, _ = preparation()
    for ident in manifest["eligible"]:
        wire = json.loads((tmp_path / f"wire/requests/{ident}.json").read_bytes())
        neutral = json.loads(files[f"requests/{ident}.json"])
        assert wire["messages"] == neutral["messages"]
        assert wire["response_format"]["json_schema"]["schema"] == neutral["response_schema"]
        assert wire["response_format"]["json_schema"]["strict"] is True
        assert set(wire) == {
            "model",
            "messages",
            "response_format",
            "store",
            "stream",
            "temperature",
            "max_completion_tokens",
            "service_tier",
        }
        assert wire["store"] is False and wire["stream"] is False
        assert wire["max_completion_tokens"] == 4096


def test_reserves_before_dispatch_and_never_opens_socket(tmp_path, monkeypatch):
    m = adapter()
    m.prepare(tmp_path / "wire")
    seen = []

    def no_socket(*args, **kwargs):
        pytest.fail("real socket opened")

    async def exercise():
        def handler(request):
            item = json.loads(json.loads(request.content)["messages"][1]["content"])
            ident = item["item_id"]
            reservation = json.loads((tmp_path / f"run/{ident}.reservation.json").read_bytes())
            assert reservation["wire_sha256"] == m.sha(request.content)
            assert "authorization" not in request.headers
            assert str(request.url) == "https://api.openai.com/v1/chat/completions"
            assert request.extensions["timeout"]["read"] <= 60
            seen.append(ident)
            return httpx.Response(200, json=answer(request))

        with monkeypatch.context() as patch:
            patch.setattr(socket, "socket", no_socket)
            return await m.run_mock(
                tmp_path / "wire", tmp_path / "run", httpx.MockTransport(handler)
            )

    result = asyncio.run(exercise())
    assert len(seen) == 17 and "v13" not in seen
    assert result["attempted"] == 17 and result["paid_requests"] == 0
    assert result["cases"]["v13"] == "local_invalid"
    assert result["usage_complete"] is True
    assert Decimal(result["simulated_reserved_usd"]) <= Decimal("2")
    assert (tmp_path / "run/responses/v01.json").read_text() == (SCRIPTED / "v01.json").read_text()


@pytest.mark.parametrize(
    "failure",
    [
        "http",
        "missing_usage",
        "boolean_usage",
        "usage_bound",
        "total",
        "cached",
        "model",
        "tier",
        "oversized",
        "duplicate_json",
    ],
)
def test_ambiguous_provider_failures_stop_without_retry(tmp_path, failure):
    m = adapter()
    m.prepare(tmp_path / "wire")
    calls = []

    def handler(request):
        calls.append(request)
        data = answer(request)
        if failure == "http":
            return httpx.Response(429, json={"error": "scripted"})
        if failure == "oversized":
            return httpx.Response(200, content=b"x" * 140000)
        if failure == "missing_usage":
            data.pop("usage")
        elif failure == "boolean_usage":
            data["usage"]["prompt_tokens"] = True
        elif failure == "usage_bound":
            data["usage"].update(prompt_tokens=999999, total_tokens=1000799)
        elif failure == "total":
            data["usage"]["total_tokens"] = 1
        elif failure == "cached":
            data["usage"]["prompt_tokens_details"]["cached_tokens"] = 1001
        elif failure == "model":
            data["model"] = "different-model"
        elif failure == "tier":
            data["service_tier"] = "priority"
        if failure == "duplicate_json":
            return httpx.Response(200, content=b'{"model":"extra",' + m.encode(data)[1:])
        return httpx.Response(200, json=data)

    result = asyncio.run(
        m.run_mock(tmp_path / "wire", tmp_path / "run", httpx.MockTransport(handler))
    )
    assert len(calls) == 1 and result["attempted"] == 1
    assert result["cases"]["v02"] == "not_attempted" and result["fatal"]
    assert (tmp_path / "run/v01.reservation.json").exists()
    assert (tmp_path / "run/v01.http.json").exists()
    assert not (tmp_path / "run/responses/v01.json").exists()


@pytest.mark.parametrize("failure", ["length", "refusal", "tool", "bad_review"])
def test_known_usage_is_counted_even_when_review_fails(tmp_path, failure):
    m = adapter()
    m.prepare(tmp_path / "wire")

    def handler(request):
        data = answer(request)
        if failure == "length":
            data["choices"][0]["finish_reason"] = "length"
        elif failure == "refusal":
            data["choices"][0]["message"]["refusal"] = "scripted refusal"
        elif failure == "tool":
            data["choices"][0]["message"]["tool_calls"] = [{"name": "do_not_execute"}]
        else:
            data["choices"][0]["message"]["content"] = "not JSON"
        return httpx.Response(200, json=data)

    result = asyncio.run(
        m.run_mock(tmp_path / "wire", tmp_path / "run", httpx.MockTransport(handler))
    )
    assert result["attempted"] == 17 and result["usage_complete"]
    assert result["fatal"] is None and result["cases"]["v01"] == "verifier_error"
    assert Decimal(result["simulated_known_cost_upper_usd"]) > 0


def test_deadline_and_write_failure_prevent_later_dispatch(tmp_path, monkeypatch):
    m = adapter()
    m.prepare(tmp_path / "wire")
    monkeypatch.setattr(m, "REQUEST_SECONDS", 0.01)

    async def never_returns(request):
        await asyncio.Event().wait()

    result = asyncio.run(
        m.run_mock(tmp_path / "wire", tmp_path / "timeout", httpx.MockTransport(never_returns))
    )
    assert result["attempted"] == 1 and result["fatal"] == "TimeoutError"
    assert result["cases"]["v02"] == "not_attempted"

    def fail_save(*args, **kwargs):
        raise OSError("scripted write failure")

    monkeypatch.setattr(m, "save", fail_save)
    calls = []
    with pytest.raises(OSError):
        asyncio.run(
            m.run_mock(
                tmp_path / "wire",
                tmp_path / "write-failure",
                httpx.MockTransport(lambda request: calls.append(request)),
            )
        )
    assert calls == []


@pytest.mark.parametrize("stage,expected_calls", [("reservation", 0), ("http", 1)])
def test_journal_write_failure_stops_at_the_correct_boundary(
    tmp_path, monkeypatch, stage, expected_calls
):
    m = adapter()
    m.prepare(tmp_path / "wire")
    real_save = m.save
    calls = []

    def save(path, value):
        if path.name.endswith(f".{stage}.json"):
            raise OSError("scripted persistence failure")
        real_save(path, value)

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=answer(request))

    monkeypatch.setattr(m, "save", save)
    with pytest.raises(OSError):
        asyncio.run(m.run_mock(tmp_path / "wire", tmp_path / "run", httpx.MockTransport(handler)))
    assert len(calls) == expected_calls
    assert not (tmp_path / "run/responses/v01.json").exists()
    if stage == "http":
        assert (tmp_path / "run/v01.reservation.json").exists()
        assert not (tmp_path / "run/v01.result.json").exists()


def test_decoded_capture_is_durable_before_usage_validation(tmp_path, monkeypatch):
    m = adapter()
    manifest = m.prepare(tmp_path / "wire")
    ids = iter(manifest["eligible"])
    real_usage = m.usage

    def usage(data, bound):
        ident = next(ids)
        witness = json.loads((tmp_path / f"run/{ident}.http.json").read_bytes())
        assert witness["capture_complete"] is True
        assert json.loads(base64.b64decode(witness["decoded_body_base64"])) == data
        return real_usage(data, bound)

    monkeypatch.setattr(m, "usage", usage)

    def handler(request):
        return httpx.Response(
            200,
            content=gzip.compress(m.encode(answer(request))),
            headers={"Content-Encoding": "gzip"},
        )

    result = asyncio.run(
        m.run_mock(tmp_path / "wire", tmp_path / "run", httpx.MockTransport(handler))
    )
    assert result["attempted"] == 17 and result["fatal"] is None


def test_wire_tampering_and_batch_deadline_prevent_dispatch(tmp_path, monkeypatch):
    m = adapter()
    m.prepare(tmp_path / "wire")
    calls = []
    transport = httpx.MockTransport(lambda request: calls.append(request))
    monkeypatch.setattr(m, "BATCH_SECONDS", 0)
    result = asyncio.run(m.run_mock(tmp_path / "wire", tmp_path / "expired", transport))
    assert result["attempted"] == 0 and result["fatal"] == "batch_deadline"
    (tmp_path / "wire/requests/v01.json").write_text("{}")
    with pytest.raises(ValueError, match="changed"):
        asyncio.run(m.run_mock(tmp_path / "wire", tmp_path / "changed", transport))
    assert calls == []


def test_real_transport_and_reuse_are_refused(tmp_path):
    m = adapter()
    m.prepare(tmp_path / "wire")
    with pytest.raises(ValueError, match="MockTransport"):
        asyncio.run(m.run_mock(tmp_path / "wire", tmp_path / "run", None))
    assert not (tmp_path / "run").exists()
    with pytest.raises(FileExistsError):
        m.prepare(tmp_path / "wire")
    with pytest.raises(ValueError):
        m.reservation(b"x" * 131073, Decimal(0), 0)
    with pytest.raises(ValueError):
        m.reservation(b"x", Decimal("2"), 1)
    with pytest.raises(ValueError):
        m.reservation(b"x", Decimal(0), 17)
