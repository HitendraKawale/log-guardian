"""Investigations API: auth gate, bounds, idempotency, queue limit, history."""

import pytest
from app.config import settings
from app.models import Investigation, InvestigationEvent
from app.routes.investigations import MAX_PENDING
from sqlalchemy import select

BODY = {
    "question": "Why did checkout fail?",
    "system": "B",
    "scope": {
        "services": ["checkout"],
        "start": "2026-01-01T10:00:00+00:00",
        "end": "2026-01-01T10:10:00+00:00",
    },
}


@pytest.fixture
def key(monkeypatch):
    monkeypatch.setattr(settings, "investigation_api_key", "test-key")
    return {"X-API-Key": "test-key"}


async def test_disabled_without_configured_key(make_client):
    async with make_client(None) as client:
        response = await client.post("/investigations", json=BODY)
        assert response.status_code == 503
        assert (await client.get("/investigations")).status_code == 503


async def test_requires_correct_key(make_client, key):
    async with make_client(None) as client:
        assert (await client.post("/investigations", json=BODY)).status_code == 401
        wrong = await client.get("/investigations", headers={"X-API-Key": "nope"})
        assert wrong.status_code == 401


async def test_create_queues_without_model_call_and_lists(make_client, key):
    async with make_client(None) as client:
        created = await client.post("/investigations", json=BODY, headers=key)
        assert created.status_code == 201
        run = created.json()
        assert run["status"] == "queued" and run["report"] is None
        assert run["usage"] is None  # No model was invoked by submission.
        listed = await client.get("/investigations", headers=key)
        assert [r["id"] for r in listed.json()] == [run["id"]]
        detail = await client.get(f"/investigations/{run['id']}", headers=key)
        assert detail.json()["scope"]["services"] == ["checkout"]


async def test_scope_and_body_validation(make_client, key):
    bad_scope = {**BODY, "scope": {**BODY["scope"], "end": "2026-01-01T12:00:01+00:00"}}
    async with make_client(None) as client:
        assert (
            await client.post("/investigations", json=bad_scope, headers=key)
        ).status_code == 422
        assert (
            await client.post("/investigations", json={**BODY, "system": "Z"}, headers=key)
        ).status_code == 422
        huge = {**BODY, "question": "x" * 3000}
        assert (await client.post("/investigations", json=huge, headers=key)).status_code == 422


async def test_idempotency_same_body_returns_same_run(make_client, key):
    headers = {**key, "Idempotency-Key": "abc"}
    async with make_client(None) as client:
        first = await client.post("/investigations", json=BODY, headers=headers)
        second = await client.post("/investigations", json=BODY, headers=headers)
        assert first.status_code == 201
        assert second.json()["id"] == first.json()["id"]
        conflict = await client.post(
            "/investigations", json={**BODY, "question": "Different?"}, headers=headers
        )
        assert conflict.status_code == 409


async def test_queue_limit_returns_429(make_client, key):
    async with make_client(None) as client:
        for _ in range(MAX_PENDING):
            assert (await client.post("/investigations", json=BODY, headers=key)).status_code == 201
        rejected = await client.post("/investigations", json=BODY, headers=key)
        assert rejected.status_code == 429


async def test_cancel_transitions_and_preserves_terminal_states(make_client, key, session_factory):
    async with make_client(None) as client:
        run_id = (await client.post("/investigations", json=BODY, headers=key)).json()["id"]
        cancelled = await client.post(f"/investigations/{run_id}/cancel", headers=key)
        assert cancelled.json()["status"] == "cancelled"
        again = await client.post(f"/investigations/{run_id}/cancel", headers=key)
        assert again.status_code == 409
        async with session_factory() as session:
            run = (await session.scalars(select(Investigation))).one()
            run.status = "running"
            await session.commit()
        racing = await client.post(f"/investigations/{run_id}/cancel", headers=key)
        assert racing.json()["status"] == "cancelling"


async def test_events_cursor_returns_ordered_history(make_client, key, session_factory):
    async with make_client(None) as client:
        run_id = (await client.post("/investigations", json=BODY, headers=key)).json()["id"]
        async with session_factory() as session:
            for seq in (1, 2, 3):
                session.add(
                    InvestigationEvent(
                        investigation_id=run_id,
                        sequence=seq,
                        kind="tool_call",
                        payload={"tool": "query_logs", "n": seq},
                    )
                )
            await session.commit()
        events = (await client.get(f"/investigations/{run_id}/events", headers=key)).json()
        assert [e["sequence"] for e in events] == [1, 2, 3]
        after = (await client.get(f"/investigations/{run_id}/events?after=2", headers=key)).json()
        assert [e["sequence"] for e in after] == [3]
        missing = await client.get("/investigations/nope/events", headers=key)
        assert missing.status_code == 404


async def test_log_ingestion_still_works_without_investigation_key(make_client):
    async with make_client(None) as client:
        response = await client.post(
            "/logs",
            json={
                "service": "checkout",
                "level": "ERROR",
                "message": "boom",
                "timestamp": "2026-01-01T10:00:00Z",
            },
        )
        assert response.status_code == 201
