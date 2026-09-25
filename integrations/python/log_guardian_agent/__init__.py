"""Record owner-wrapped tool calls without capturing private arguments or enforcing policy."""

from __future__ import annotations

import hashlib
import inspect
import json
import os
import re
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import wraps
from pathlib import Path
from uuid import uuid4

MAX_EVENTS = 10000
MAX_JOURNAL_BYTES = 8 * 1024 * 1024


def _identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", value):
        raise ValueError("identifier must be 1-128 ASCII letters, digits or _.:-")
    return value


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


@dataclass(frozen=True)
class Policy:
    allowed_tools: frozenset[str]

    def __post_init__(self):
        if (
            type(self.allowed_tools) not in (set, frozenset, list, tuple)
            or len(self.allowed_tools) > 256
        ):
            raise ValueError("allowed_tools must contain at most 256 tool identifiers")
        object.__setattr__(
            self, "allowed_tools", frozenset(_identifier(t) for t in self.allowed_tools)
        )

    @property
    def fingerprint(self):
        return hashlib.sha256(
            _json({"schema_version": 1, "allowed_tools": sorted(self.allowed_tools)})
        ).hexdigest()


class AuditWriteError(RuntimeError):
    """A caller must not retry a tool just because its completion could not be recorded."""

    def __init__(self, action_may_have_executed):
        self.action_may_have_executed = action_may_have_executed
        super().__init__(
            "Audit unavailable; action may have executed. Do not automatically retry."
            if action_may_have_executed
            else "Audit unavailable; tool was not invoked."
        )


class Monitor:
    def __init__(self, path: str | Path, *, agent: str, policy: Policy):
        _identifier(agent)
        if not isinstance(policy, Policy):
            raise TypeError("policy must be an owner-constructed Policy")
        self.run_id = uuid4().hex
        self._lock = threading.RLock()
        self._sequence, self._bytes = 0, 0
        self._pending = {}
        self._closed, self._failed = False, False
        path = Path(path)
        self._file = os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb")
        try:
            self._write("run_started", {"agent": agent, "policy_sha256": policy.fingerprint}, False)
            fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        except BaseException:
            self._file.close()
            raise

    def _write(self, kind, fields, after_call):
        if self._closed or self._failed:
            raise AuditWriteError(after_call)
        event = {
            "schema_version": 1,
            "run_id": self.run_id,
            "sequence": self._sequence,
            "event_id": f"{self.run_id}:{self._sequence}",
            "timestamp": datetime.now(UTC).isoformat(),
            "kind": kind,
            **fields,
        }
        raw = _json(event) + b"\n"
        if self._sequence >= MAX_EVENTS or self._bytes + len(raw) > MAX_JOURNAL_BYTES:
            raise AuditWriteError(after_call)
        try:
            self._file.write(raw)
            self._file.flush()
            os.fsync(self._file.fileno())
        except (OSError, ValueError):
            self._failed = True
            raise AuditWriteError(after_call) from None
        self._sequence += 1
        self._bytes += len(raw)

    def _begin(self, tool, origin):
        with self._lock:
            if self._sequence + len(self._pending) + 2 > MAX_EVENTS:
                raise AuditWriteError(False)
            call_id = uuid4().hex
            self._write("tool_request", {"call_id": call_id, "tool": tool, "origin": origin}, False)
            self._pending[call_id] = time.monotonic_ns()
            return call_id

    def _finish(self, call_id, outcome):
        with self._lock:
            elapsed = max(0, (time.monotonic_ns() - self._pending[call_id]) // 1_000_000)
            self._write(
                "tool_completion",
                {"call_id": call_id, "outcome": outcome, "elapsed_ms": elapsed},
                True,
            )
            del self._pending[call_id]

    @contextmanager
    def _call(self, tool, origin):
        call_id = self._begin(tool, origin)
        try:
            yield
        except BaseException:
            self._finish(call_id, "raised")
            raise
        else:
            self._finish(call_id, "returned")

    def wrap(self, tool: str, function, *, origin="agent"):
        _identifier(tool)
        if origin not in ("agent", "host") or not callable(function):
            raise ValueError("wrap requires a callable and agent or host origin")
        if inspect.iscoroutinefunction(function) or inspect.iscoroutinefunction(function.__call__):

            @wraps(function)
            async def asynchronous(*args, **kwargs):
                with self._call(tool, origin):
                    return await function(*args, **kwargs)

            return asynchronous

        @wraps(function)
        def synchronous(*args, **kwargs):
            with self._call(tool, origin):
                return function(*args, **kwargs)

        return synchronous

    def close(self):
        with self._lock:
            if not self._closed:
                self._closed = True
                self._file.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def inspect_journal(raw: bytes, policy: Policy) -> dict:
    """Validate a bounded journal against separate owner policy, never adopt journal policy."""
    if not isinstance(policy, Policy) or not isinstance(raw, bytes):
        raise ValueError("journal bytes and owner Policy are required")
    if not raw or len(raw) > MAX_JOURNAL_BYTES or not raw.endswith(b"\n"):
        raise ValueError("empty, oversized or incomplete journal")
    lines = raw.splitlines()
    if len(lines) > MAX_EVENTS:
        raise ValueError("journal exceeds event limit")
    events = [json.loads(line, object_pairs_hook=_object) for line in lines]
    header = events[0]
    if not isinstance(header, dict) or header.get("kind") != "run_started":
        raise ValueError("journal must start with run_started")
    run_id = header.get("run_id")
    if not isinstance(run_id, str) or not re.fullmatch(r"[0-9a-f]{32}", run_id):
        raise ValueError("invalid run identifier")
    base = {"schema_version", "run_id", "sequence", "event_id", "timestamp", "kind"}
    extra = {
        "run_started": {"agent", "policy_sha256"},
        "tool_request": {"call_id", "tool", "origin"},
        "tool_completion": {"call_id", "outcome", "elapsed_ms"},
    }
    requests, completions = {}, {}
    for number, event in enumerate(events):
        if (
            not isinstance(event, dict)
            or not isinstance(event.get("kind"), str)
            or event["kind"] not in extra
        ):
            raise ValueError("invalid event kind")
        if (
            set(event) != base | extra[event["kind"]]
            or type(event["schema_version"]) is not int
            or event["schema_version"] != 1
        ):
            raise ValueError("invalid event fields or schema version")
        if (
            type(event["sequence"]) is not int
            or event["sequence"] != number
            or event["run_id"] != run_id
            or event["event_id"] != f"{run_id}:{number}"
        ):
            raise ValueError("invalid event identity or sequence")
        stamp = event["timestamp"]
        if (
            not isinstance(stamp, str)
            or len(stamp) > 64
            or datetime.fromisoformat(stamp).utcoffset() is None
        ):
            raise ValueError("timestamp must include a UTC offset")
        if event["kind"] == "run_started":
            if number != 0 or event["policy_sha256"] != policy.fingerprint:
                raise ValueError("duplicate run header or owner policy mismatch")
            _identifier(event["agent"])
            continue
        call_id = event["call_id"]
        if not isinstance(call_id, str) or not re.fullmatch(r"[0-9a-f]{32}", call_id):
            raise ValueError("invalid call identifier")
        if event["kind"] == "tool_request":
            _identifier(event["tool"])
            if call_id in requests or event["origin"] not in ("agent", "host"):
                raise ValueError("duplicate request or invalid origin")
            requests[call_id] = event
        else:
            if (
                call_id not in requests
                or call_id in completions
                or event["outcome"] not in ("returned", "raised")
                or type(event["elapsed_ms"]) is not int
                or event["elapsed_ms"] < 0
            ):
                raise ValueError("orphan, repeated or invalid completion")
            completions[call_id] = event
    calls, findings = [], []
    for call_id, request in requests.items():
        completion = completions.get(call_id)
        call = {
            "call_id": call_id,
            "tool": request["tool"],
            "origin": request["origin"],
            "outcome": completion["outcome"] if completion else "unknown",
            "elapsed_ms": completion["elapsed_ms"] if completion else None,
            "evidence_ids": [request["event_id"]]
            + ([completion["event_id"]] if completion else []),
        }
        calls.append(call)
        if call["origin"] == "agent" and call["tool"] not in policy.allowed_tools:
            findings.append({"rule_id": "disallowed_tool", **call})
    return {
        "schema_version": 1,
        "run_id": run_id,
        "agent": header["agent"],
        "policy_sha256": policy.fingerprint,
        "calls": calls,
        "findings": findings,
        "capture_complete": None,
    }
