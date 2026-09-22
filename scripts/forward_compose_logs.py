#!/usr/bin/env python3
"""Forward one Compose service without a Docker socket mount or unbounded buffering.

One request at a time, no retries or durable spool. HTTP failures stop collection:
a timed-out request may already have persisted, so replay can create duplicates.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime

LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
ALIASES = {"WARN": "WARNING", "FATAL": "CRITICAL"}
MAX_LINE_BYTES = 64 * 1024


def read_lines(stream):
    """Yield bounded records; None represents one drained oversized line."""
    while line := stream.readline(MAX_LINE_BYTES + 1):
        if len(line) > MAX_LINE_BYTES:
            while not line.endswith(b"\n"):
                line = stream.readline(MAX_LINE_BYTES + 1)
                if not line:
                    break
            yield None
        else:
            yield line


def parse_line(line: bytes, source: str) -> dict:
    """Trust source identity and Docker event time, not embedded JSON metadata."""
    stamp, separator, message = line.decode("utf-8", errors="replace").rstrip("\r\n").partition(" ")
    if not separator or not message.strip():
        raise ValueError("missing timestamp or message")
    timestamp = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    if timestamp.tzinfo is None:
        raise ValueError("timestamp needs an offset")
    try:
        data = json.loads(message)
    except (ValueError, RecursionError):
        data = None
    level = "INFO"
    if isinstance(data, dict) and isinstance(data.get("message"), str) and data["message"].strip():
        message = data["message"]
        raw_level = data.get("level", "INFO")
        if not isinstance(raw_level, str):
            raise ValueError("invalid level")
        level = ALIASES.get(raw_level.upper(), raw_level.upper())
        if level not in LEVELS:
            raise ValueError("invalid level")
    else:
        match = re.match(r"^(?:\[([A-Za-z]+)\]|([A-Za-z]+))(?=\s|:|$)", message)
        if match:
            token = (match[1] or match[2]).upper()
            candidate = ALIASES.get(token, token)
            if candidate in LEVELS:
                level = candidate
    return {
        "service": source,
        "level": level,
        "message": message,
        "timestamp": timestamp.astimezone(UTC).isoformat(),
    }


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Never forward an ingestion credential to a redirect destination."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def arguments(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Example:
  LOG_GUARDIAN_API_KEY=<key> python3 scripts/forward_compose_logs.py \\
    --file compose.yml --project-name shop --service checkout

Resolves exactly one running non-TTY container, then follows native docker logs.
Starts at new output (--tail 0). Set LOG_GUARDIAN_API_KEY in the environment.
Plain text defaults to INFO unless it starts with a severity token.
Multiline output becomes separate records. Oversized/invalid lines are rejected.
Exit codes: 0 clean EOF, 1 collection/delivery failure, 2 invalid configuration,
130 interrupted, 143 terminated. No automatic reconnect or replay.
""",
    )
    parser.add_argument(
        "--file", action="append", required=True, help="Compose file; repeat for overrides"
    )
    parser.add_argument("--project-name", required=True)
    parser.add_argument("--service", required=True)
    parser.add_argument("--source-name", help="Stored service identity (default: project/service)")
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    args = parser.parse_args(argv)
    for value in (args.project_name, args.service):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", value):
            parser.error("project and service must be names, not options or paths")
    args.source_name = args.source_name or f"{args.project_name}/{args.service}"
    if len(args.source_name) > 128 or any(ord(c) < 32 or ord(c) == 127 for c in args.source_name):
        parser.error("source name must be at most 128 characters with no control characters")
    key = os.environ.get("LOG_GUARDIAN_API_KEY", "")
    if not key or any(not 33 <= ord(c) <= 126 for c in key):
        parser.error("set LOG_GUARDIAN_API_KEY to a nonempty printable ASCII key without spaces")
    try:
        url = urllib.parse.urlsplit(args.api_url)
        port = url.port
    except ValueError:
        parser.error("invalid API URL")
    if (
        url.scheme not in {"http", "https"}
        or not url.hostname
        or url.username is not None
        or url.password is not None
        or url.query
        or url.fragment
        or url.path not in {"", "/"}
        or (port is not None and port == 0)
        or any(c.isspace() or ord(c) < 32 for c in args.api_url)
    ):
        parser.error(
            "API URL must be an HTTP(S) origin without credentials, path, query, or fragment"
        )
    if url.scheme == "http" and url.hostname not in {"localhost", "127.0.0.1", "::1"}:
        parser.error("use HTTPS for a non-loopback API")
    args.api_url = args.api_url.rstrip("/")
    return args, key


def main(argv=None) -> int:
    args, key = arguments(argv)
    command = ["docker", "compose"]
    for path in args.file:
        command.extend(["--file", path])
    command.extend(
        [
            "--project-name",
            args.project_name,
            "ps",
            "-q",
            args.service,
        ]
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    acknowledged = rejected = 0
    last_ack = "never"
    child = None

    def status(state):
        print(
            f"{state} source={args.source_name} acknowledged={acknowledged} "
            f"rejected={rejected} last_ack={last_ack}",
            file=sys.stderr,
            flush=True,
        )

    def interrupted(signum, frame):
        raise SystemExit(128 + signum)

    previous = {sig: signal.signal(sig, interrupted) for sig in (signal.SIGINT, signal.SIGTERM)}
    try:
        containers = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            text=True,
            check=True,
            timeout=10,
        ).stdout.split()
        if len(containers) != 1 or not re.fullmatch(r"[0-9a-f]+", containers[0]):
            status("select exactly one running service container; scaled services are unsupported")
            return 1
        container = containers[0]
        inspect = ["docker", "inspect", "--format", "{{.Config.Tty}} {{.State.Running}}", container]
        state = subprocess.run(
            inspect,
            stdout=subprocess.PIPE,
            text=True,
            check=True,
            timeout=10,
        ).stdout.strip()
        if state != "false true":
            status("source must be running with tty disabled to separate log streams")
            return 1
        # Compose logs merges streams; native logs preserves non-TTY stderr separation.
        child = subprocess.Popen(
            ["docker", "logs", "--follow", "--timestamps", "--tail", "0", container],
            stdout=subprocess.PIPE,
        )
        status("following")
        for line in read_lines(child.stdout):
            try:
                if line is None:
                    raise ValueError("oversized line")
                record = parse_line(line, args.source_name)
            except (ValueError, OverflowError):
                rejected += 1
                status("rejected invalid or oversized line")
                continue
            request = urllib.request.Request(
                f"{args.api_url}/logs",
                data=json.dumps(record).encode(),
                headers={"Content-Type": "application/json", "X-API-Key": key},
                method="POST",
            )
            try:
                with opener.open(request, timeout=5) as response:
                    if response.status != 201:
                        raise ValueError("unexpected ingestion status")
            except (urllib.error.URLError, OSError, ValueError):
                status("delivery failed; current record uncertain; stopping without retry")
                return 1
            acknowledged += 1
            last_ack = datetime.now(UTC).isoformat()
            status("delivered")
        if child.wait(timeout=5) != 0:
            status("docker exited unsuccessfully")
            return 1
        final_state = subprocess.run(
            inspect,
            stdout=subprocess.PIPE,
            text=True,
            check=True,
            timeout=10,
        ).stdout.strip()
        if final_state != "false true":
            status("source stopped; restart collection explicitly after checking the service")
            return 1
        return 0
    except (OSError, subprocess.SubprocessError):
        status("docker collection failed; check Docker and Compose configuration")
        return 1
    finally:
        # Ignore repeated interrupts while reaping only our child.
        for sig in previous:
            signal.signal(sig, signal.SIG_IGN)
        try:
            if child is not None:
                if child.poll() is None:
                    child.terminate()
                    try:
                        child.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        child.kill()
                        child.wait()
                child.stdout.close()
            status("stopped")
        finally:
            for sig, handler in previous.items():
                signal.signal(sig, handler)


if __name__ == "__main__":
    sys.exit(main())
