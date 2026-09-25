"""Imports are authorized, atomic and idempotent; reviewing cannot spend model budget."""

import json

import pytest
from app.config import settings
from sqlalchemy import func, select

from tests.security_case_helpers import AUTH, NGINX, OWNER, payload

HEADERS = {"X-API-Key": "security-test", "Idempotency-Key": "import-1"}


@pytest.fixture
def configured(monkeypatch, tmp_path):
    path = tmp_path / "sources.json"
    path.write_text(json.dumps(OWNER))
    monkeypatch.setattr(settings, "security_api_key", "security-test", raising=False)
    monkeypatch.setattr(settings, "security_sources_path", str(path), raising=False)
    return path


async def test_security_api_disabled_or_wrong_key_does_not_accept_uploads(
    client, configured, monkeypatch
):
    monkeypatch.setattr(settings, "security_api_key", "")
    assert (
        await client.post("/security/cases", json=payload(), headers=HEADERS)
    ).status_code == 503
    monkeypatch.setattr(settings, "security_api_key", "security-test")
    for path in ("/security/sources", "/security/cases", "/security/cases/unknown"):
        response = await client.get(path, headers={"X-API-Key": "log-key"})
        assert response.status_code == 401
        assert response.headers["cache-control"] == "no-store"


async def test_import_replay_history_and_snapshot_survive_owner_config_change(
    client, configured, session_factory
):
    from app.models import Investigation, SecurityCase, SecurityEvidence

    first = await client.post("/security/cases", json=payload(), headers=HEADERS)
    assert first.status_code == 201, first.text
    case = first.json()
    assert len(case["report"]["links"]) == 1
    second = await client.post("/security/cases", json=payload(), headers=HEADERS)
    assert second.status_code == 200
    assert second.json() == case
    async with session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(SecurityCase)) == 1
        assert await session.scalar(select(func.count()).select_from(SecurityEvidence)) == 2
        assert await session.scalar(select(func.count()).select_from(Investigation)) == 0
    configured.write_text("invalid configuration")
    assert (await client.get(f"/security/cases/{case['id']}", headers=HEADERS)).json() == case
    history = (await client.get("/security/cases", headers=HEADERS)).json()
    assert history[0]["id"] == case["id"] and "report" not in history[0]
    assert (await client.get("/security/sources", headers=HEADERS)).status_code == 503


async def test_changed_identity_or_idempotency_content_rolls_back_all_rows(
    client, configured, session_factory
):
    from app.models import SecurityCase, SecurityEvidence

    assert (
        await client.post("/security/cases", json=payload(), headers=HEADERS)
    ).status_code == 201
    changed = payload(auth={**AUTH, "outcome": "success"})
    changed["logs"]["auth"] = (
        json.dumps({**AUTH, "event_id": "auth-0-new", "request_id": "new-request"})
        + "\n"
        + changed["logs"]["auth"]
    )
    for key in ("import-1", "import-2"):
        response = await client.post(
            "/security/cases", json=changed, headers={**HEADERS, "Idempotency-Key": key}
        )
        assert response.status_code == 409
    async with session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(SecurityCase)) == 1
        assert await session.scalar(select(func.count()).select_from(SecurityEvidence)) == 2


async def test_overlap_reuses_evidence_but_owner_drift_cannot_reinterpret_it(
    client, configured, session_factory
):
    from app.models import SecurityEvidence

    assert (
        await client.post("/security/cases", json=payload(), headers=HEADERS)
    ).status_code == 201
    assert (
        await client.post(
            "/security/cases", json=payload(), headers={**HEADERS, "Idempotency-Key": "other"}
        )
    ).status_code == 201
    async with session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(SecurityEvidence)) == 2
    owner = json.loads(configured.read_text())
    owner["sources"][0]["request_namespace"] = "other-app"
    configured.write_text(json.dumps(owner))
    for key in ("import-1", "changed-owner"):
        assert (
            await client.post(
                "/security/cases", json=payload(), headers={**HEADERS, "Idempotency-Key": key}
            )
        ).status_code == 409


async def test_invalid_inputs_are_sanitized_and_large_chunked_bodies_rejected(client, configured):
    bad = payload(nginx={**NGINX, "password": "PRIVATE"})
    response = await client.post("/security/cases", json=bad, headers=HEADERS)
    assert response.status_code == 422
    assert "PRIVATE" not in response.text
    assert (
        await client.post("/security/cases", json=payload(), headers={"X-API-Key": "security-test"})
    ).status_code == 422

    async def chunks():
        for _ in range(33):
            yield b"x" * 65536

    assert (
        await client.post("/security/cases", content=chunks(), headers=HEADERS)
    ).status_code == 413
    assert (await client.get("/security/cases?limit=1000", headers=HEADERS)).status_code == 422
    assert (await client.get("/security/cases/unknown", headers=HEADERS)).status_code == 404
