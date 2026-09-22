"""Runtime selection must remain authenticated, explainable and incapable of spending."""

from datetime import UTC, datetime, timedelta

from app.config import settings
from app.models import Investigation
from sqlalchemy import func, select


async def test_familiar_burst_creates_one_incident_without_an_investigation(
    client, session_factory
):
    at = datetime.now(UTC)
    payload = {
        "service": "api-burst",
        "level": "ERROR",
        "message": "same timeout",
        "timestamp": at.isoformat(),
    }
    for _ in range(6):
        assert (await client.post("/logs", json=payload)).status_code == 201
    rows = (await client.get("/candidates", params={"service": "api-burst"})).json()["items"]
    assert len(rows) == 1 and rows[0]["occurrence_count"] == 2
    assert rows[0]["signal_details"]["count"] == 6
    assert rows[0]["activity"] == "active"
    async with session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(Investigation)) == 0


async def test_excluded_logs_store_without_learning_and_detector_route_uses_log_key(
    client, monkeypatch
):
    payload = {
        "service": "old-api",
        "level": "ERROR",
        "message": "timeout",
        "timestamp": (datetime.now(UTC) - timedelta(minutes=10)).isoformat(),
    }
    assert (await client.post("/logs", json=payload)).status_code == 201
    assert (await client.get("/candidates/detectors", params={"service": "old-api"})).json()[
        "total"
    ] == 0
    monkeypatch.setattr(settings, "api_key", "review-key")
    assert (await client.get("/candidates/detectors")).status_code == 401
    assert (
        await client.get("/candidates/detectors", headers={"X-API-Key": "review-key"})
    ).status_code == 200
    assert (
        await client.get("/candidates/detectors", headers={"X-API-Key": "execution-key"})
    ).status_code == 401


async def test_detector_configuration_rejects_negative_warmup():
    import pytest
    from app.config import Settings

    with pytest.raises(ValueError):
        Settings(trigger_warmup_logs=-1)
