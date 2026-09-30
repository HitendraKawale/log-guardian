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


async def test_baseline_works_without_execution_key_or_network(
    client, configured, monkeypatch, session_factory
):
    import httpx
    from app.models import Investigation, InvestigationEvent

    async def forbidden_network(*args, **kwargs):
        raise AssertionError("Baseline attempted outbound network access")

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", forbidden_network)
    monkeypatch.setattr(settings, "investigation_api_key", "")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    created = await client.post("/security/cases", json=payload(), headers=HEADERS)
    assert created.status_code == 201
    case = created.json()
    url = f"/security/cases/{case['id']}/assessment"
    first = await client.get(url, headers=HEADERS)
    assert first.status_code == 200
    assert first.headers["cache-control"] == "no-store"
    assert first.json()["method"] == "deterministic"
    assert len(first.content) <= 64 * 1024
    assert (await client.get(url, headers=HEADERS)).content == first.content
    assert (await client.get(f"/security/cases/{case['id']}", headers=HEADERS)).json() == case
    async with session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(Investigation)) == 0
        assert await session.scalar(select(func.count()).select_from(InvestigationEvent)) == 0


async def test_baseline_auth_snapshot_and_sanitized_errors(
    client, configured, monkeypatch, session_factory
):
    from app.models import SecurityCase

    created = await client.post("/security/cases", json=payload(), headers=HEADERS)
    identity = created.json()["id"]
    url = f"/security/cases/{identity}/assessment"
    baseline = await client.get(url, headers=HEADERS)
    assert baseline.status_code == 200
    for headers in ({}, {"X-API-Key": "execution-test"}, {"X-API-Key": "log-key"}):
        response = await client.get(url, headers=headers)
        assert response.status_code == 401
        assert response.headers["cache-control"] == "no-store"
    monkeypatch.setattr(settings, "security_api_key", "")
    assert (await client.get(url, headers=HEADERS)).status_code == 503
    monkeypatch.setattr(settings, "security_api_key", "security-test")
    assert (
        await client.get("/security/cases/missing/assessment", headers=HEADERS)
    ).status_code == 404
    configured.write_text("invalid current registry")
    assert (await client.get(url, headers=HEADERS)).content == baseline.content
    monkeypatch.setattr(settings, "security_sources_path", str(configured.parent / "absent.json"))
    assert (await client.get(url, headers=HEADERS)).content == baseline.content
    async with session_factory() as session:
        case = await session.get(SecurityCase, identity)
        case.report = {"timeline": "PRIVATE_BROKEN_EVIDENCE"}
        await session.commit()
    response = await client.get(url, headers=HEADERS)
    assert response.status_code == 422
    assert response.headers["cache-control"] == "no-store"
    assert "PRIVATE" not in response.text
    assert (await client.get(f"/security/cases/{identity}", headers=HEADERS)).status_code == 200


@pytest.mark.parametrize(
    "status,error",
    [
        ("failed", "invalid_report"),
        ("failed", "provider_error"),
        ("failed", "cost_budget"),
        ("cancelled", "cancelled"),
    ],
)
async def test_ai_failure_does_not_change_baseline_or_stored_run(
    client, configured, session_factory, status, error
):
    from app.models import Investigation, InvestigationEvent, SecurityCase

    created = await client.post("/security/cases", json=payload(), headers=HEADERS)
    saved = created.json()
    identity = saved["id"]
    url = f"/security/cases/{identity}/assessment"
    before = await client.get(url, headers=HEADERS)
    assert before.status_code == 200
    async with session_factory() as session:
        run = Investigation(
            question="Recorded failed attempt",
            system="S",
            security_case_id=identity,
            scope=saved["report"]["scope"],
            status=status,
            error=error,
            request_sha256=saved["request_sha256"],
            report=None,
        )
        session.add(run)
        await session.flush()
        run_id = run.id
        session.add(
            InvestigationEvent(
                investigation_id=run_id,
                sequence=1,
                kind="status",
                payload={"status": status, "error": error},
            )
        )
        await session.commit()
    assert (await client.get(url, headers=HEADERS)).content == before.content
    async with session_factory() as session:
        run = await session.get(Investigation, run_id)
        assert (run.status, run.error, run.report) == (status, error, None)
        assert await session.scalar(select(func.count()).select_from(Investigation)) == 1
        assert await session.scalar(select(func.count()).select_from(InvestigationEvent)) == 1
        case = await session.get(SecurityCase, identity)
        assert case.report == saved["report"]
        assert case.source_snapshot == saved["source_snapshot"]
        assert case.input_hashes == saved["input_hashes"]
