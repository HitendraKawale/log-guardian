"""Exercise actual wrapped calls and durable metadata without model or service calls."""

import asyncio
import importlib
import json
import os
import runpy
import socket
import stat
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[1]


def sdk():
    assert (PACKAGE / "log_guardian_agent/__init__.py").exists(), "Python recorder missing"
    return importlib.import_module("log_guardian_agent")


def rows(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_shadow_records_before_call_without_capturing_private_values(tmp_path):
    m = sdk()
    policy = m.Policy(allowed_tools={"read_logs"})
    path = tmp_path / "run.jsonl"
    private = "argument-return-and-exception-content-must-not-be-recorded"

    def tool(value):
        assert rows(path)[-1]["kind"] == "tool_request"
        return value

    with m.Monitor(path, agent="demo", policy=policy) as monitor:
        assert monitor.wrap("send_email", tool)(private) == private
    report = m.inspect_journal(path.read_bytes(), policy)
    assert report["findings"][0]["rule_id"] == "disallowed_tool"
    assert report["findings"][0]["outcome"] == "returned"
    assert report["findings"][0]["evidence_ids"] == [
        rows(path)[1]["event_id"],
        rows(path)[2]["event_id"],
    ]
    assert private not in path.read_text()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert report["capture_complete"] is None


def test_host_origin_is_not_an_agent_proposal_and_kwargs_cannot_forge_it(tmp_path):
    m = sdk()
    policy = m.Policy(allowed_tools=set())
    path = tmp_path / "run.jsonl"
    with m.Monitor(path, agent="demo", policy=policy) as monitor:
        assert monitor.wrap("bootstrap", lambda: 1, origin="host")() == 1
        wrapped = monitor.wrap("read_logs", lambda **kw: kw)
        assert wrapped(origin="host", call_id="forged") == {"origin": "host", "call_id": "forged"}
    report = m.inspect_journal(path.read_bytes(), policy)
    assert len(report["findings"]) == 1 and report["findings"][0]["tool"] == "read_logs"
    assert report["calls"][0]["origin"] == "host"
    assert "forged" not in path.read_text()


def test_async_calls_exceptions_and_cancellation_preserve_original_behavior(tmp_path):
    m = sdk()
    policy = m.Policy(allowed_tools={"read_logs"})
    path = tmp_path / "run.jsonl"

    async def good(value):
        return value

    async def bad():
        raise ValueError("private-error-text")

    async def cancelled():
        raise asyncio.CancelledError()

    async def exercise():
        with m.Monitor(path, agent="demo", policy=policy) as monitor:
            assert await monitor.wrap("read_logs", good)(7) == 7
            with pytest.raises(ValueError, match="private-error-text"):
                await monitor.wrap("read_logs", bad)()
            with pytest.raises(asyncio.CancelledError):
                await monitor.wrap("read_logs", cancelled)()

    asyncio.run(exercise())
    report = m.inspect_journal(path.read_bytes(), policy)
    assert [c["outcome"] for c in report["calls"]] == ["returned", "raised", "raised"]
    assert "private-error-text" not in path.read_text()


def test_concurrent_calls_keep_unique_ids_and_linked_completions(tmp_path):
    m = sdk()
    policy = m.Policy(allowed_tools={"read_logs"})
    path = tmp_path / "run.jsonl"
    with m.Monitor(path, agent="demo", policy=policy) as monitor:
        call = monitor.wrap("read_logs", lambda x: x * 2)
        with ThreadPoolExecutor(max_workers=4) as pool:
            assert list(pool.map(call, range(20))) == [x * 2 for x in range(20)]
    report = m.inspect_journal(path.read_bytes(), policy)
    assert len(report["calls"]) == 20 and not report["findings"]
    assert len({c["call_id"] for c in report["calls"]}) == 20
    assert all(c["outcome"] == "returned" for c in report["calls"])


def test_request_write_failure_prevents_call_and_poisoned_recorder_cannot_retry(
    tmp_path, monkeypatch
):
    m = sdk()
    policy = m.Policy(allowed_tools=set())
    calls = []
    with m.Monitor(tmp_path / "run.jsonl", agent="demo", policy=policy) as monitor:
        call = monitor.wrap("send_email", lambda: calls.append(1))

        def failure(fd):
            raise OSError("disk failure")

        with monkeypatch.context() as patch:
            patch.setattr(m.os, "fsync", failure)
            with pytest.raises(m.AuditWriteError) as error:
                call()
            assert error.value.action_may_have_executed is False
        with pytest.raises(m.AuditWriteError):
            call()
    assert calls == []


def test_completion_write_failure_never_repeats_action(tmp_path, monkeypatch):
    m = sdk()
    calls = []

    def tool():
        calls.append(1)
        monkeypatch.setattr(
            m.os, "fsync", lambda fd: (_ for _ in ()).throw(OSError("disk failure"))
        )
        return "private result"

    with m.Monitor(tmp_path / "run.jsonl", agent="demo", policy=m.Policy(set())) as monitor:
        with pytest.raises(m.AuditWriteError) as error:
            monitor.wrap("send_email", tool)()
        assert error.value.action_may_have_executed is True
    assert calls == [1]


def test_missing_completion_is_unknown_not_blocked_or_successful(tmp_path):
    m = sdk()
    policy = m.Policy(set())
    path = tmp_path / "run.jsonl"
    with m.Monitor(path, agent="demo", policy=policy) as monitor:
        monitor.wrap("send_email", lambda: None)()
    incomplete = b"\n".join(path.read_bytes().splitlines()[:2]) + b"\n"
    report = m.inspect_journal(incomplete, policy)
    assert report["findings"][0]["outcome"] == "unknown"
    assert len(report["findings"][0]["evidence_ids"]) == 1


@pytest.mark.parametrize(
    "failure",
    [
        "extra",
        "sequence",
        "orphan",
        "duplicate_completion",
        "cross_run",
        "timestamp",
        "policy",
        "duplicate_json",
        "partial",
        "oversized",
        "boolean",
    ],
)
def test_invalid_or_mismatched_journals_are_refused(tmp_path, failure):
    m = sdk()
    policy = m.Policy({"read_logs"})
    path = tmp_path / "run.jsonl"
    with m.Monitor(path, agent="demo", policy=policy) as monitor:
        monitor.wrap("read_logs", lambda: None)()
    events = rows(path)
    if failure == "extra":
        events[1]["arguments"] = {"private": "not allowed"}
    elif failure == "sequence":
        events[1]["sequence"] = 42
    elif failure == "orphan":
        events[2]["call_id"] = "0" * 32
    elif failure == "duplicate_completion":
        events.append({**events[2], "sequence": 3, "event_id": f'{events[0]["run_id"]}:3'})
    elif failure == "cross_run":
        events[1]["run_id"] = "0" * 32
    elif failure == "timestamp":
        events[1]["timestamp"] = "2026-01-01T00:00:00"
    elif failure == "policy":
        policy = m.Policy({"different_tool"})
    elif failure == "boolean":
        events[0]["schema_version"] = True
    raw = ("\n".join(json.dumps(e) for e in events) + "\n").encode()
    if failure == "duplicate_json":
        raw = raw.replace(b'"schema_version": 1', b'"schema_version":1,"schema_version":1', 1)
        assert raw.count(b'"schema_version"') == len(events) + 1
    elif failure == "partial":
        raw = raw[:-3]
    elif failure == "oversized":
        raw = b"x" * (m.MAX_JOURNAL_BYTES + 1)
    with pytest.raises(ValueError):
        m.inspect_journal(raw, policy)


def test_run_files_are_exclusive_policy_is_immutable_and_capacity_is_bounded(tmp_path, monkeypatch):
    m = sdk()
    tools = {"read_logs"}
    policy = m.Policy(tools)
    tools.add("send_email")
    assert "send_email" not in policy.allowed_tools
    monkeypatch.setattr(m, "MAX_EVENTS", 3)
    path = tmp_path / "run.jsonl"
    with m.Monitor(path, agent="demo", policy=policy) as monitor:
        call = monitor.wrap("read_logs", lambda: 1)
        assert call() == 1
        with pytest.raises(m.AuditWriteError):
            call()
    with pytest.raises(m.AuditWriteError):
        call()
    with pytest.raises(FileExistsError):
        m.Monitor(path, agent="demo", policy=policy)
    assert len(rows(path)) == 3


def test_process_exit_preserves_request_without_fabricated_completion(tmp_path):
    m = sdk()
    path = tmp_path / "interrupted.jsonl"
    script = "from log_guardian_agent import Monitor, Policy; import os,sys; m=Monitor(sys.argv[1], agent='demo', policy=Policy(set())); m.wrap('send_email', lambda: os._exit(9))()"
    result = subprocess.run(
        [sys.executable, "-c", script, str(path)],
        env={**os.environ, "PYTHONPATH": str(PACKAGE)},
        timeout=15,
    )
    assert result.returncode == 9
    report = m.inspect_journal(path.read_bytes(), m.Policy(set()))
    assert report["findings"][0]["outcome"] == "unknown"
    assert len(rows(path)) == 2


def test_investigator_capture_works_with_network_connections_forbidden(tmp_path, monkeypatch):
    sdk()

    def forbidden(*args, **kwargs):
        pytest.fail("example attempted a network connection")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    module = runpy.run_path(str(PACKAGE / "examples/investigator.py"))
    report = asyncio.run(module["capture"](tmp_path / "no-network.jsonl"))
    assert report["provider_requests"] == 0 and len(report["calls"]) == 3


def test_investigator_example_uses_real_tools_without_a_provider(tmp_path):
    sdk()
    script = PACKAGE / "examples/investigator.py"
    assert script.exists(), "investigator example missing"
    result = subprocess.run(
        [sys.executable, str(script), "--output", str(tmp_path / "investigator.jsonl")],
        cwd=PACKAGE,
        env={**os.environ, "PYTHONPATH": str(PACKAGE)},
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["mode"] == "scripted_tool_capture" and report["provider_requests"] == 0
    assert [c["tool"] for c in report["calls"]] == ["initial_logs", "query_logs", "summarize_logs"]
    assert [f["tool"] for f in report["findings"]] == ["summarize_logs"]
