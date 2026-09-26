"""Security review permission cannot spend, and one saved case queues at most once."""

import asyncio

import pytest
from app.config import settings
from app.models import Investigation
from app.routes.security_cases import save_case
from sqlalchemy import func, select

from tests.security_case_helpers import OWNER, payload

EXECUTION = {"X-API-Key": "execution-test"}


@pytest.fixture(autouse=True)
def keys(monkeypatch):
    monkeypatch.setattr(settings, "investigation_api_key", "execution-test")
    monkeypatch.setattr(settings, "security_api_key", "review-test")


async def seed_case(session_factory):
    async with session_factory() as session:
        case, _ = await save_case(session, OWNER, payload(), "import-test")
        return case.id, case.report["scope"]


async def test_promote_once_with_saved_scope_and_reopen_terminal_run(client, session_factory):
    case_id, scope = await seed_case(session_factory)
    url = f"/investigations/from-security-case/{case_id}"
    first = await client.post(url, headers=EXECUTION)
    assert first.status_code == 201, first.text
    run = first.json()
    assert run["security_case_id"] == case_id
    assert run["scope"] == scope and run["system"] == "C"
    for path in (
        f"/investigations/{run['id']}",
        f"/investigations/{run['id']}/events",
        "/investigations",
    ):
        read = await client.get(path, headers=EXECUTION)
        assert read.status_code == 200
        assert read.headers.get("cache-control") == "no-store"
    assert "request-1" not in run["question"]
    async with session_factory() as session:
        saved = await session.get(Investigation, run["id"])
        saved.status = "failed"
        await session.commit()
    again = await client.post(url, headers=EXECUTION)
    assert again.status_code == 200 and again.json()["id"] == run["id"]
    assert again.json()["status"] == "failed"
    detail = await client.get(f"/security/cases/{case_id}", headers={"X-API-Key": "review-test"})
    assert detail.json()["investigation_id"] == run["id"]
    async with session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(Investigation)) == 1


@pytest.mark.parametrize("key", [None, "review-test", "wrong"])
async def test_review_key_cannot_promote(client, session_factory, key):
    case_id, _ = await seed_case(session_factory)
    headers = {"X-API-Key": key} if key else {}
    response = await client.post(f"/investigations/from-security-case/{case_id}", headers=headers)
    assert response.status_code == 401
    async with session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(Investigation)) == 0


async def test_disabled_unknown_and_body_overrides(client, session_factory, monkeypatch):
    case_id, _ = await seed_case(session_factory)
    url = f"/investigations/from-security-case/{case_id}"
    monkeypatch.setattr(settings, "investigation_api_key", "")
    assert (await client.post(url, headers=EXECUTION)).status_code == 503
    monkeypatch.setattr(settings, "investigation_api_key", "execution-test")
    assert (
        await client.post("/investigations/from-security-case/missing", headers=EXECUTION)
    ).status_code == 404
    for body in ({"scope": {}}, {"system": "A"}, {"question": "override"}, {"case_id": "other"}):
        assert (await client.post(url, headers=EXECUTION, json=body)).status_code == 422
    async with session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(Investigation)) == 0


async def test_queue_full_does_not_bind_case(client, session_factory):
    case_id, scope = await seed_case(session_factory)
    async with session_factory() as session:
        session.add_all(
            [
                Investigation(question="existing", system="C", scope=scope, request_sha256="0" * 64)
                for _ in range(20)
            ]
        )
        await session.commit()
    response = await client.post(f"/investigations/from-security-case/{case_id}", headers=EXECUTION)
    assert response.status_code == 429


async def test_legacy_dispatch_rejects_security_run_before_provider(client, session_factory):
    import runpy
    from pathlib import Path

    from app.investigation_agent import MODEL, BaselineConfig
    from app.investigation_schemas import InvestigationScope
    from app.investigation_tools import EvidenceTools

    from tests.test_investigator import scripted_client

    case_id, scope = await seed_case(session_factory)
    queued = (
        await client.post(f"/investigations/from-security-case/{case_id}", headers=EXECUTION)
    ).json()
    async with session_factory() as session:
        run = await session.get(Investigation, queued["id"])
        stored_system = run.system
    root = Path(__file__).resolve().parents[3]
    legacy = runpy.run_path(
        str(
            root
            / "evals/results/2026-09-23-fresh-report-live/candidate/services/ingestion-service/app/investigation_agent.py"
        ),
        run_name="app._legacy_security_dispatch",
    )
    tools = EvidenceTools(InvestigationScope(**scope), records=[])
    async with scripted_client(
        lambda request: pytest.fail("legacy dispatch reached the provider with the wrong source")
    ) as provider:
        with pytest.raises(ValueError, match="Invalid baseline"):
            await legacy["run_investigation"](
                stored_system,
                queued["question"],
                tools,
                provider,
                BaselineConfig(model=MODEL, max_cost_usd="0.025"),
            )


async def test_sqlite_concurrent_promotion_has_one_winner(tmp_path):
    from app.routes.investigations import promote_security_case
    from fastapi import Response

    from tests.test_investigation_journal import database

    async with database(tmp_path) as (factory, observer, _):
        case_id, _ = await seed_case(factory)

        async def promote():
            async with factory() as session:
                reply = Response()
                run = await promote_security_case(case_id, reply, session=session)
                return run["id"], reply.status_code

        results = await asyncio.gather(*(promote() for _ in range(4)))
        assert len({identity for identity, _ in results}) == 1
        assert sorted(code for _, code in results) == [200, 200, 200, 201]
        async with observer() as session:
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(Investigation)
                    .where(Investigation.security_case_id == case_id)
                )
                == 1
            )
