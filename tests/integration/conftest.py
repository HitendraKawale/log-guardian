"""Fixtures for tests that run against the live Compose stack.

Nothing here is mocked. These talk to the containers started by ``make up``, so
they exercise the parts the unit suites cannot: real HTTP between the two
services, a real broker, real Postgres, and spans actually arriving at Jaeger.

If the stack is not running the whole directory skips rather than failing, so
``make test`` stays useful on a machine without Docker.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from typing import Any

import httpx
import pytest

INGESTION_URL = os.getenv("INGESTION_URL", "http://localhost:8000")
AI_URL = os.getenv("AI_URL", "http://localhost:8001")
JAEGER_URL = os.getenv("JAEGER_URL", "http://localhost:16686")
PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://localhost:9090")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:8080")


def wait_until(predicate: Callable[[], Any], timeout: float = 60.0, interval: float = 1.0) -> Any:
    """Poll until the predicate returns something truthy, or fail the test.

    Async paths here are eventually consistent: Kafka delivery and Jaeger's
    batched span export both take seconds, so asserting immediately after a
    request would be a race rather than a test.
    """
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = predicate()
        if last:
            return last
        time.sleep(interval)
    pytest.fail(f"condition not met within {timeout:.0f}s (last value: {last!r})")


def service_is_up(url: str, timeout: float = 3.0) -> bool:
    """True once the URL answers 200.

    A container that is still booting refuses or resets the connection, which
    means "not yet" rather than "broken" - so those errors are swallowed here
    instead of escaping into whatever is polling.
    """
    try:
        return httpx.get(url, timeout=timeout).status_code == 200
    except (httpx.HTTPError, OSError):
        return False


@pytest.fixture(scope="session", autouse=True)
def require_stack() -> None:
    """Skip the whole directory unless the stack answers."""
    try:
        response = httpx.get(f"{INGESTION_URL}/health", timeout=3.0)
        response.raise_for_status()
    except (httpx.HTTPError, OSError) as exc:
        pytest.skip(f"Compose stack not reachable at {INGESTION_URL} ({exc}); run `make up`")


@pytest.fixture
def client() -> httpx.Client:
    with httpx.Client(base_url=INGESTION_URL, timeout=15.0) as session:
        yield session
