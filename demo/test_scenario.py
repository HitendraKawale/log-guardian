"""Real timeout and recovery against an isolated in-process sandbox.

Runs both roles of demo/app.py as real HTTP servers on ephemeral localhost
ports: an injected inventory delay must produce a genuine checkout timeout,
and resetting it must restore success. No Docker or network stubbing.
"""

import json
import socket
import sys
import threading
import time
from pathlib import Path

import httpx
import pytest
import uvicorn
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app import create_apps  # noqa: E402


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def start(app, port):
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        assert time.monotonic() < deadline, "server did not start"
        time.sleep(0.05)
    return server, thread


@pytest.fixture
def sandbox():
    inventory_port, checkout_port, fault_port = free_port(), free_port(), free_port()
    inventory_app, inventory_faults, fault_state = create_apps("inventory")
    checkout_app, _, _ = create_apps(
        "checkout", inventory_url=f"http://127.0.0.1:{inventory_port}", deadline_ms=500
    )
    servers = []
    try:
        for app, port in (
            (inventory_app, inventory_port),
            (inventory_faults, fault_port),
            (checkout_app, checkout_port),
        ):
            servers.append(start(app, port))
        yield {
            "checkout": f"http://127.0.0.1:{checkout_port}",
            "faults": f"http://127.0.0.1:{fault_port}",
            "fault_state": fault_state,
        }
    finally:
        for server, _ in servers:
            server.should_exit = True
        for _, thread in servers:
            thread.join(timeout=10)
        assert not any(thread.is_alive() for _, thread in servers), "server did not stop"


def test_sandbox_teardown_waits_for_server_threads():
    before = set(threading.enumerate())
    fixture = sandbox.__wrapped__()
    next(fixture)
    servers = set(threading.enumerate()) - before
    assert servers
    fixture.close()
    assert not any(thread.is_alive() for thread in servers)


def test_fault_causes_real_timeout_and_reset_restores_service(sandbox):
    with httpx.Client(timeout=5.0) as client:
        healthy = client.get(f"{sandbox['checkout']}/checkout/ok-1")
        assert healthy.status_code == 200 and healthy.json()["status"] == "confirmed"
        try:
            applied = client.post(f"{sandbox['faults']}/fault/delay", json={"seconds": 2.0})
            assert applied.status_code == 200
            started = time.monotonic()
            failed = client.get(f"{sandbox['checkout']}/checkout/fault-1")
            elapsed = time.monotonic() - started
            assert failed.status_code == 504
            assert 0.4 <= elapsed <= 1.9, f"not a real deadline timeout: {elapsed:.2f}s"
        finally:
            reset = client.post(f"{sandbox['faults']}/fault/reset")
            assert reset.status_code == 200 and sandbox["fault_state"]["delay_seconds"] == 0
        recovered = client.get(f"{sandbox['checkout']}/checkout/after-1")
        assert recovered.status_code == 200


def test_fault_controls_reject_out_of_bounds_delay(sandbox):
    with httpx.Client(timeout=5.0) as client:
        response = client.post(f"{sandbox['faults']}/fault/delay", json={"seconds": 3600})
        assert response.status_code == 422
        assert sandbox["fault_state"]["delay_seconds"] == 0


@pytest.mark.parametrize("direct", [False, True])
def test_application_record_reaches_stdout_with_optional_direct_delivery(
    capsys, monkeypatch, direct
):
    delivered = []

    def ingest(request):
        delivered.append(json.loads(request.content))
        return httpx.Response(201, json={"id": 1})

    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(ingest), **kwargs),
    )
    app, faults, _ = create_apps("inventory", ingestion_url="http://ingestion" if direct else "")
    with TestClient(app) as client:
        assert client.get("/stock/42").status_code == 200
    with TestClient(faults) as client:
        assert client.post("/fault/delay", json={"seconds": 0.1}).status_code == 200
        assert client.post("/fault/reset").status_code == 200
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["service"] == "inventory"
    assert record["level"] == "INFO"
    assert "stock request 42 completed" in record["message"]
    assert delivered == ([record] if direct else [])


def test_fault_endpoints_are_not_on_the_public_app_port(sandbox):
    with httpx.Client(timeout=5.0) as client:
        for route in ("/fault", "/fault/delay", "/fault/reset"):
            assert client.get(f"{sandbox['checkout']}{route}").status_code == 404
