"""Exercise real nginx request-ID replacement and query-free logging against a stub upstream."""

import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session", autouse=True)
def require_stack():
    if not os.environ.get("LG_TEST_NGINX_IMAGE"):
        pytest.skip("set LG_TEST_NGINX_IMAGE to a task-owned nginx test image")


def test_real_nginx_replaces_client_id_and_does_not_log_query(tmp_path):
    configuration = (ROOT / "examples/security-review/nginx.conf").read_text()
    configuration += """
server {
    listen 9000;
    access_log off;
    location / {
        default_type application/json;
        return 200 '{"received_request_id":"$http_x_request_id"}';
    }
}
"""
    path = tmp_path / "security.conf"
    path.write_text(configuration)
    name = "lg48-nginx-" + uuid.uuid4().hex[:12]

    def docker(*args, check=True):
        return subprocess.run(["docker", *args], text=True, capture_output=True, check=check)

    docker(
        "run",
        "-d",
        "--name",
        name,
        "-p",
        "127.0.0.1::8080",
        "-v",
        f"{path}:/etc/nginx/conf.d/security.conf:ro",
        os.environ["LG_TEST_NGINX_IMAGE"],
    )
    try:
        port = docker("port", name, "8080/tcp").stdout.strip().rsplit(":", 1)[1]
        url = f"http://127.0.0.1:{port}/login?token=DO-NOT-CAPTURE"
        request = urllib.request.Request(
            url, headers={"X-Request-ID": "attacker-controlled", "X-Forwarded-For": "127.0.0.99"}
        )
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(request, timeout=1) as response:
                    upstream = json.load(response)
                break
            except (urllib.error.URLError, TimeoutError, ConnectionError):
                if docker("inspect", "-f", "{{.State.Running}}", name).stdout.strip() != "true":
                    logs = docker("logs", name)
                    pytest.fail(logs.stdout + logs.stderr)
                time.sleep(0.1)
        else:
            pytest.fail("nginx did not become ready")
        assert re.fullmatch(r"[0-9a-f]{32}", upstream["received_request_id"])
        assert "syntax is ok" in docker("exec", name, "nginx", "-t").stderr
        target = tmp_path / "gateway.jsonl"
        docker("cp", f"{name}:/var/log/nginx/security-review.jsonl", str(target))
        raw = target.read_bytes()
        assert b"DO-NOT-CAPTURE" not in raw and b"attacker-controlled" not in raw
        records = [json.loads(line) for line in raw.splitlines()]
        assert records[-1]["request_id"] == upstream["received_request_id"]
        assert records[-1]["route"] == "/login"
        assert records[-1]["remote_addr"] != "127.0.0.99"
        assert set(records[-1]) == {"time", "request_id", "remote_addr", "status", "route"}
        print("nginx -t passed; generated ID reached upstream; query and client ID absent from log")
    finally:
        docker("stop", name, check=False)
        docker("rm", name, check=False)
