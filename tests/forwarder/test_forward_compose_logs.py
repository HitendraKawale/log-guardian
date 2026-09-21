"""Exercise collector boundaries without requiring Docker or a provider key."""

import importlib.util
import io
import json
import os
import signal
import subprocess
import sys
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "forward_compose_logs.py"
STAMP = "2026-09-20T12:00:00Z"


@pytest.fixture
def collector():
    assert SCRIPT.exists(), "The planned forwarder has not been implemented"
    spec = importlib.util.spec_from_file_location("forwarder", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("message", "level", "text"),
    [
        ('{"message":"timeout","level":"error","service":"attacker"}', "ERROR", "timeout"),
        ('{"message":"retry","level":"WARN"}', "WARNING", "retry"),
        ('{"message":"stopped","level":"fatal"}', "CRITICAL", "stopped"),
        ('{"message":"hello"}', "INFO", "hello"),
        ('{"broken":', "INFO", '{"broken":'),
        ('{"message":42}', "INFO", '{"message":42}'),
        ("[ERROR] timeout", "ERROR", "[ERROR] timeout"),
        ("WARNING retry", "WARNING", "WARNING retry"),
        ("an error occurred", "INFO", "an error occurred"),
        ("ERRORLESS message", "INFO", "ERRORLESS message"),
        ("hello 世界", "INFO", "hello 世界"),
    ],
)
def test_parse_preserves_text_and_source(collector, message, level, text):
    assert collector.parse_line(f"{STAMP} {message}".encode(), "shop/checkout") == {
        "service": "shop/checkout",
        "level": level,
        "message": text,
        "timestamp": "2026-09-20T12:00:00+00:00",
    }


@pytest.mark.parametrize(
    "line",
    [
        b"no stamp",
        b"2026-09-20T12:00:00 plain",
        b"bad x",
        f'{STAMP} {{"message":"x","level":"BANANA"}}'.encode(),
    ],
)
def test_invalid_records_are_rejected(collector, line):
    with pytest.raises(ValueError):
        collector.parse_line(line, "shop/checkout")


def test_normalizes_offset_and_replaces_invalid_unicode(collector):
    record = collector.parse_line(b"2026-09-20T14:00:00+02:00 hello\xff", "shop/api")
    assert record["timestamp"] == "2026-09-20T12:00:00+00:00"
    assert record["message"] == "hello\ufffd"


def test_oversized_line_is_drained_not_split_into_events(collector):
    stream = io.BytesIO(b"x" * 70_000 + b"\nnext\n")
    assert list(collector.read_lines(stream)) == [None, b"next\n"]


def test_reader_does_not_consume_next_line_early(collector):
    stream = io.BytesIO(b"first\nsecond\n")
    lines = collector.read_lines(stream)
    assert next(lines) == b"first\n"
    assert stream.tell() == 6


@contextmanager
def receiver(status=201):
    records = []
    received = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            records.append(
                (
                    self.path,
                    self.headers.get("X-API-Key"),
                    json.loads(self.rfile.read(int(self.headers["Content-Length"]))),
                )
            )
            self.send_response(status)
            if status == 302:
                self.send_header("Location", "/redirected")
            self.end_headers()
            self.wfile.write(b"{}")
            received.set()

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", records, received
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def fake_docker(tmp_path, body):
    executable = tmp_path / "docker"
    executable.write_text(
        f"#!{sys.executable}\nimport os, sys, json, signal\n"
        "from pathlib import Path\n"
        "with open(os.environ['ARGS_PATH'], 'a') as f: f.write(json.dumps(sys.argv[1:]) + '\\n')\n"
        "if sys.argv[1] == 'compose':\n"
        "    print(os.environ.get('CONTAINER_IDS', 'abc123'))\n"
        "    sys.exit(int(os.environ.get('RESOLVE_EXIT', '0')))\n"
        "if sys.argv[1] == 'inspect':\n"
        "    state_key = 'FINAL_STATE' if Path(os.environ['PID_PATH']).exists() else 'CONTAINER_STATE'\n"
        "    print(os.environ.get(state_key, 'false true'))\n"
        "    sys.exit(0)\n"
        "Path(os.environ['PID_PATH']).write_text(str(os.getpid()))\n" + body
    )
    executable.chmod(0o755)
    return {
        **os.environ,
        "PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}",
        "PID_PATH": str(tmp_path / "pid"),
        "ARGS_PATH": str(tmp_path / "args"),
        "LOG_GUARDIAN_API_KEY": "test-only-key",
    }


def command(url):
    return [
        sys.executable,
        str(SCRIPT),
        "--file",
        "compose.yml",
        "--project-name",
        "shop",
        "--service",
        "checkout",
        "--api-url",
        url,
    ]


def test_cli_forwards_without_stderr_or_key_leakage(tmp_path):
    env = fake_docker(
        tmp_path,
        f"print('{STAMP} owner-only', file=sys.stderr)\nprint('{STAMP} ERROR timeout', flush=True)\n",
    )
    with receiver() as (url, records, _):
        result = subprocess.run(command(url), env=env, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert len(records) == 1
    path, key, record = records[0]
    assert (path, key) == ("/logs", "test-only-key")
    assert record["service"] == "shop/checkout"
    assert record["level"] == "ERROR"
    assert "test-only-key" not in result.stdout + result.stderr
    assert "acknowledged=1" in result.stderr
    calls = [json.loads(line) for line in (tmp_path / "args").read_text().splitlines()]
    assert calls[0] == [
        "compose",
        "--file",
        "compose.yml",
        "--project-name",
        "shop",
        "ps",
        "-q",
        "checkout",
    ]
    assert ["logs", "--follow", "--timestamps", "--tail", "0", "abc123"] in calls
    assert all(call[0] != "compose" or "logs" not in call for call in calls)


@pytest.mark.parametrize("status", [401, 429, 500, 302])
def test_http_failure_stops_without_retry_or_redirect(tmp_path, status):
    env = fake_docker(
        tmp_path, f"print('{STAMP} first', flush=True)\nprint('{STAMP} second', flush=True)\n"
    )
    with receiver(status) as (url, records, _):
        result = subprocess.run(command(url), env=env, capture_output=True, text=True, timeout=10)
    assert result.returncode == 1
    assert len(records) == 1
    assert "acknowledged=0" in result.stderr


def test_transport_failure_stops_and_reports_uncertainty(tmp_path):
    env = fake_docker(tmp_path, f"print('{STAMP} first', flush=True)\n")
    with receiver() as (url, _, _):
        pass
    result = subprocess.run(command(url), env=env, capture_output=True, text=True, timeout=10)
    assert result.returncode == 1
    assert "uncertain" in result.stderr.lower()


@pytest.mark.parametrize("sig", [signal.SIGINT, signal.SIGTERM])
def test_signal_reaps_owned_child(tmp_path, sig):
    env = fake_docker(tmp_path, f"print('{STAMP} first', flush=True)\nsignal.pause()\n")
    with receiver() as (url, records, received):
        process = subprocess.Popen(
            command(url), env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        try:
            assert received.wait(5), "forwarder never delivered its first record"
            process.send_signal(sig)
            _, stderr = process.communicate(timeout=8)
            assert process.returncode == 128 + sig, stderr
            assert len(records) == 1
            pid = int((tmp_path / "pid").read_text())
            with pytest.raises(ProcessLookupError):
                os.kill(pid, 0)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)


@pytest.mark.parametrize(
    "override",
    [
        {"CONTAINER_IDS": ""},
        {"CONTAINER_IDS": "abc123\ndef456"},
        {"CONTAINER_IDS": "-invalid"},
        {"RESOLVE_EXIT": "1"},
        {"CONTAINER_STATE": "true true"},
        {"CONTAINER_STATE": "false false"},
        {"CONTAINER_STATE": "unrecognizable"},
    ],
)
def test_resolution_rejects_ambiguous_or_unsafe_sources(tmp_path, override):
    env = fake_docker(tmp_path, f"print('{STAMP} unexpected', flush=True)\n")
    env.update(override)
    result = subprocess.run(
        command("http://127.0.0.1:8000"), env=env, capture_output=True, text=True, timeout=5
    )
    assert result.returncode == 1
    assert not (tmp_path / "pid").exists(), "unsafe source started streaming"


def test_stopped_container_is_reported_as_failure(tmp_path):
    env = fake_docker(tmp_path, "sys.exit(0)\n")
    env["FINAL_STATE"] = "false false"
    result = subprocess.run(
        command("http://127.0.0.1:8000"), env=env, capture_output=True, text=True, timeout=5
    )
    assert result.returncode == 1
    assert "source" in result.stderr.lower()


def test_docker_failure_is_not_success(tmp_path):
    env = fake_docker(tmp_path, "sys.exit(7)\n")
    result = subprocess.run(
        command("http://127.0.0.1:8000"), env=env, capture_output=True, text=True, timeout=5
    )
    assert result.returncode == 1
    assert "docker" in result.stderr.lower()


@pytest.mark.parametrize(
    ("url", "key", "extra"),
    [
        ("http://user:password@localhost:8000", "key", []),
        ("file:///tmp/logs", "key", []),
        ("http://localhost:8000", "bad\nkey", []),
        ("http://localhost:8000", "", []),
        ("http://localhost:8000", "key", ["--service=-evil"]),
    ],
)
def test_invalid_cli_input_fails_before_docker(tmp_path, url, key, extra):
    env = fake_docker(tmp_path, "sys.exit(0)\n")
    env["LOG_GUARDIAN_API_KEY"] = key
    result = subprocess.run(
        command(url) + extra, env=env, capture_output=True, text=True, timeout=5
    )
    assert result.returncode == 2
    assert not (tmp_path / "pid").exists()
    assert "usage:" in result.stderr.lower()
