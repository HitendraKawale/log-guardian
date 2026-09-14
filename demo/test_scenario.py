"""Real timeout and recovery against an isolated in-process sandbox.

Runs both roles of demo/app.py as real HTTP servers on ephemeral localhost
ports: an injected inventory delay must produce a genuine checkout timeout,
and resetting it must restore success. No Docker or network stubbing.
"""

import socket
import sys
import threading
import time
from pathlib import Path

import httpx
import pytest
import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app import create_apps  # noqa: E402


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def start(app, port):
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    threading.Thread(target=server.run, daemon=True).start()
    deadline = time.monotonic() + 10
    while not server.started:
        assert time.monotonic() < deadline, "server did not start"
        time.sleep(0.05)
    return server


@pytest.fixture
def sandbox():
    inventory_port, checkout_port, fault_port = free_port(), free_port(), free_port()
    inventory_app, inventory_faults, fault_state = create_apps("inventory")
    checkout_app, _, _ = create_apps(
        "checkout", inventory_url=f"http://127.0.0.1:{inventory_port}", deadline_ms=500
    )
    servers = [
        start(inventory_app, inventory_port),
        start(inventory_faults, fault_port),
        start(checkout_app, checkout_port),
    ]
    yield {
        "checkout": f"http://127.0.0.1:{checkout_port}",
        "faults": f"http://127.0.0.1:{fault_port}",
        "fault_state": fault_state,
    }
    for server in servers:
        server.should_exit = True


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


def test_fault_endpoints_are_not_on_the_public_app_port(sandbox):
    with httpx.Client(timeout=5.0) as client:
        for route in ("/fault", "/fault/delay", "/fault/reset"):
            assert client.get(f"{sandbox['checkout']}{route}").status_code == 404
