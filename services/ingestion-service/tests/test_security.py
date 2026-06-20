import pytest

from app import security
from app.config import settings

PAYLOAD = {
    "service": "payment-api",
    "level": "INFO",
    "message": "hello",
    "timestamp": "2026-06-18T10:00:00Z",
}


@pytest.fixture
def api_key(monkeypatch):
    monkeypatch.setattr(settings, "api_key", "secret-key")
    yield "secret-key"


async def test_request_without_key_is_rejected(client, api_key):
    response = await client.post("/logs", json=PAYLOAD)
    assert response.status_code == 401


async def test_request_with_wrong_key_is_rejected(client, api_key):
    response = await client.post("/logs", json=PAYLOAD, headers={"X-API-Key": "nope"})
    assert response.status_code == 401


async def test_request_with_correct_key_succeeds(client, api_key):
    response = await client.post("/logs", json=PAYLOAD, headers={"X-API-Key": api_key})
    assert response.status_code == 201


async def test_open_when_no_key_configured(client):
    # Default settings have no api_key, so the dashboard works without one.
    response = await client.post("/logs", json=PAYLOAD)
    assert response.status_code == 201


def test_rate_limiter_blocks_after_limit():
    limiter = security.RateLimiter(limit_per_minute=3)
    assert all(limiter.allow("1.2.3.4") for _ in range(3))
    assert limiter.allow("1.2.3.4") is False
    # A different client is unaffected.
    assert limiter.allow("5.6.7.8") is True


def test_rate_limiter_disabled_when_zero():
    limiter = security.RateLimiter(limit_per_minute=0)
    assert all(limiter.allow("1.2.3.4") for _ in range(100))
