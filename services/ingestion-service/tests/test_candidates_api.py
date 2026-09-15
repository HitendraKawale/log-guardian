"""The candidate queue: reviewable, and incapable of spending money."""

from datetime import UTC, datetime

import pytest
from app.models import InvestigationCandidate

pytestmark = pytest.mark.anyio


def _candidate(service: str = "checkout", template: str = "disk error", **overrides):
    values = {
        "service": service,
        "level": "ERROR",
        "message": "disk controller reset",
        "template": template,
        "reason": "unseen-template",
        "scope": {
            "services": [service],
            "start": "2026-01-01T09:55:00+00:00",
            "end": "2026-01-01T10:05:00+00:00",
        },
        "status": "new",
        "occurred_at": datetime(2026, 1, 1, 10, tzinfo=UTC),
    }
    values.update(overrides)
    return InvestigationCandidate(**values)


async def _seed(session_factory, *candidates) -> list[str]:
    async with session_factory() as session:
        for candidate in candidates:
            session.add(candidate)
        await session.commit()
        return [candidate.id for candidate in candidates]


async def test_ingesting_a_novel_log_creates_a_candidate(client, session_factory, monkeypatch):
    """End to end: the trigger's selection becomes a reviewable row."""
    from app import service as service_module
    from app.trigger import InvestigationTrigger

    # monkeypatch, not assignment: the trigger is a module global, and leaking a
    # warmed-up one into other tests makes ordering matter.
    monkeypatch.setattr(
        service_module,
        "investigation_trigger",
        InvestigationTrigger(candidate_levels=("ERROR",), warmup_logs=0),
    )
    response = await client.post(
        "/logs",
        json={
            "service": "checkout",
            "level": "ERROR",
            "message": "inventory read timed out after 1000ms",
            "timestamp": "2026-06-18T10:00:00Z",
        },
    )
    assert response.status_code == 201

    listing = await client.get("/candidates")
    assert listing.status_code == 200
    body = listing.json()
    assert body["total"] == 1
    assert body["items"][0]["service"] == "checkout"
    assert body["items"][0]["reason"] == "unseen-template"


async def test_candidate_scope_is_usable_by_an_investigation(client, session_factory):
    from app.investigation_schemas import InvestigationScope

    await _seed(session_factory, _candidate())
    body = (await client.get("/candidates")).json()
    scope = InvestigationScope(**body["items"][0]["scope"])
    assert scope.services == ("checkout",)


async def test_listing_filters_by_status_and_service(client, session_factory):
    await _seed(
        session_factory,
        _candidate(template="a"),
        _candidate(template="b", status="dismissed"),
        _candidate(service="inventory", template="c"),
    )
    assert (await client.get("/candidates?status=new")).json()["total"] == 2
    assert (await client.get("/candidates?status=dismissed")).json()["total"] == 1
    assert (await client.get("/candidates?service=inventory")).json()["total"] == 1


async def test_dismiss_marks_reviewed_and_is_idempotent(client, session_factory):
    ids = await _seed(session_factory, _candidate())
    first = await client.post(f"/candidates/{ids[0]}/dismiss")
    assert first.status_code == 200
    assert first.json()["status"] == "dismissed"
    stamp = first.json()["dismissed_at"]

    second = await client.post(f"/candidates/{ids[0]}/dismiss")
    assert second.status_code == 200
    assert second.json()["dismissed_at"] == stamp, "a retried click must not move the timestamp"


async def test_unknown_candidate_is_404(client):
    assert (await client.get("/candidates/does-not-exist")).status_code == 404
    assert (await client.post("/candidates/does-not-exist/dismiss")).status_code == 404


async def test_the_queue_cannot_start_an_investigation(client, session_factory):
    """The spend boundary, asserted rather than documented.

    Reviewing candidates must not create investigations: a paid run is a
    separate, key-gated, human action on another router.
    """
    from app.models import Investigation
    from sqlalchemy import func, select

    ids = await _seed(session_factory, _candidate())
    await client.get("/candidates")
    await client.get(f"/candidates/{ids[0]}")
    await client.post(f"/candidates/{ids[0]}/dismiss")

    async with session_factory() as session:
        queued = await session.scalar(select(func.count()).select_from(Investigation))
    assert queued == 0

    # And there is no promote route to reach by accident: 404 means the path
    # matches nothing at all, not merely that the method is wrong.
    assert (await client.post(f"/candidates/{ids[0]}/investigate")).status_code == 404
