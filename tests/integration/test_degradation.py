"""What happens to ingestion when the model is gone.

The whole point of the best-effort AI call is that losing the scorer must not
lose logs. That is asserted in the unit suite with a fake returning None, which
proves the branch works but not that the real failure looks like the fake one:
a stopped container is a connection error inside httpx, not a tidy None.

This stops the actual container, so it is slower than everything else here and
restores the service on the way out even if the assertions fail.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.integration.conftest import service_is_up, wait_until

AI_HEALTH = "http://localhost:8001/health"

pytestmark = pytest.mark.integration

COMPOSE_FILE = (
    Path(__file__).resolve().parents[2] / "infrastructure" / "docker" / "docker-compose.yml"
)
LOG = {
    "service": "degradation-test",
    "level": "CRITICAL",
    "message": "scorer unavailable, log must still land",
    "timestamp": "2026-06-18T10:00:00Z",
}


def _compose(*args: str) -> None:
    subprocess.run(
        ["docker", "compose", "-f", str(COMPOSE_FILE), *args],
        check=True,
        capture_output=True,
        timeout=120,
    )


@pytest.fixture(scope="module")
def ai_service_down():
    """Stop the scorer for this module, and put it back whatever happens."""
    _compose("stop", "ai-service")
    try:
        yield
    finally:
        _compose("start", "ai-service")
        wait_until(lambda: service_is_up(AI_HEALTH), timeout=90)


def test_ingestion_survives_the_scorer_being_down(client, ai_service_down):
    response = client.post("/logs", json=LOG)

    # 201, not 502: the log is captured even though nothing could score it.
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "unscored"
    assert body["anomaly_score"] is None
    assert body["is_anomaly"] is None


def test_unscored_log_is_still_queryable(client, ai_service_down):
    created = client.post("/logs", json=LOG).json()
    fetched = client.get(f"/logs/{created['id']}").json()
    assert fetched["status"] == "unscored"
    assert fetched["message"] == LOG["message"]


def test_readiness_ignores_the_scorer(client, ai_service_down):
    # Readiness tracks the database, not the model. Reporting not-ready here
    # would take the pods out of rotation for a dependency they can live without.
    assert client.get("/readiness").status_code == 200


# Recovery is covered by test_stack.py: this module sorts first, so the scoring
# tests there only pass if the fixture put ai-service back.
