"""Queue and inspect investigations. This process never calls the model.

Execution is disabled unless a nonempty investigation API key is configured;
every route here then requires that key. A separate worker process claims
queued rows, so submission stays cheap and never spends provider money.
"""

import hashlib
import json
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_session
from ..investigation_schemas import InvestigationScope
from ..models import Investigation, InvestigationCandidate, InvestigationEvent

router = APIRouter(prefix="/investigations", tags=["investigations"])

MAX_PENDING = 20
CANCELLABLE = {"queued", "running"}
PENDING = {"queued", "running", "cancelling"}


async def require_investigation_key(x_api_key: str | None = Header(default=None)) -> None:
    """Unlike log ingestion, an empty key disables this API entirely."""
    if not settings.investigation_api_key:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Investigation execution is disabled; configure INVESTIGATION_API_KEY",
        )
    if x_api_key != settings.investigation_api_key:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or missing API key")


class PromoteCandidate(BaseModel):
    """Optional overrides when promoting a candidate into a paid run."""

    model_config = ConfigDict(extra="forbid")

    question: str | None = Field(None, min_length=1, max_length=2048)
    system: Literal["A", "B", "C"] = "B"


class InvestigationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=2048)
    system: Literal["A", "B", "C"] = "B"
    scope: InvestigationScope


def _public(run: Investigation) -> dict:
    return {
        "id": run.id,
        "question": run.question,
        "system": run.system,
        "scope": run.scope,
        "status": run.status,
        "error": run.error,
        "report": run.report,
        "model_requested": run.model_requested,
        "prompt_sha256": run.prompt_sha256,
        "code_revision": run.code_revision,
        "usage": run.usage,
        "estimated_cost_usd": run.estimated_cost_usd,
        "elapsed_ms": run.elapsed_ms,
        "created_at": run.created_at,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
    }


@router.post(
    "", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_investigation_key)]
)
async def create_investigation(
    body: InvestigationCreate,
    session: AsyncSession = Depends(get_session),
    idempotency_key: str | None = Header(default=None, max_length=128),
):
    digest = hashlib.sha256(
        json.dumps(body.model_dump(mode="json"), sort_keys=True).encode()
    ).hexdigest()
    if idempotency_key:
        existing = await session.scalar(
            select(Investigation).where(Investigation.idempotency_key == idempotency_key)
        )
        if existing is not None:
            if existing.request_sha256 != digest:
                raise HTTPException(
                    status.HTTP_409_CONFLICT, "Idempotency key reused with a different request"
                )
            return _public(existing)
    pending = await session.scalar(
        select(func.count()).select_from(Investigation).where(Investigation.status.in_(PENDING))
    )
    if pending >= MAX_PENDING:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Investigation queue is full")
    run = Investigation(
        question=body.question,
        system=body.system,
        scope=body.scope.model_dump(mode="json"),
        idempotency_key=idempotency_key,
        request_sha256=digest,
    )
    session.add(run)
    try:
        await session.commit()
    except IntegrityError:
        # Concurrent duplicate submission with the same key: return the winner.
        await session.rollback()
        existing = await session.scalar(
            select(Investigation).where(Investigation.idempotency_key == idempotency_key)
        )
        if existing is None or existing.request_sha256 != digest:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "Idempotency key reused with a different request"
            ) from None
        return _public(existing)
    await session.refresh(run)
    # Re-check after commit so concurrent submissions cannot overshoot the queue:
    # the newest rows above the ceiling remove themselves.
    pending_rows = (
        await session.scalars(
            select(Investigation.id)
            .where(Investigation.status.in_(PENDING))
            .order_by(Investigation.created_at, Investigation.id)
        )
    ).all()
    if run.id in pending_rows[MAX_PENDING:]:
        await session.delete(run)
        await session.commit()
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Investigation queue is full")
    return _public(run)


@router.post(
    "/from-candidate/{candidate_id}",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_investigation_key)],
)
async def promote_candidate(
    candidate_id: str,
    body: PromoteCandidate | None = None,
    session: AsyncSession = Depends(get_session),
):
    """Turn a reviewed candidate into a queued investigation.

    This is the only path from the candidate queue to paid execution, and it
    lives here rather than on the candidates router for that reason: it is
    behind INVESTIGATION_API_KEY, so the capability to spend and the capability
    to review are separate keys. Nothing automatic reaches it -- the trigger
    fills the queue, a human empties it.
    """
    body = body or PromoteCandidate()
    # Share the detector's database lock before copying a mutable incident scope.
    if session.bind.dialect.name == "sqlite":
        await session.execute(text("BEGIN IMMEDIATE"))
    candidate = await session.scalar(
        select(InvestigationCandidate)
        .where(InvestigationCandidate.id == candidate_id)
        .with_for_update()
    )
    if candidate is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Candidate not found")

    # The link is the idempotency record: a second promotion returns the first
    # run instead of paying for the same question twice.
    if candidate.investigation_id:
        existing = await session.get(Investigation, candidate.investigation_id)
        if existing is not None:
            return _public(existing)
    if candidate.status == "dismissed":
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Candidate was dismissed; undismiss it before promoting"
        )

    pending = await session.scalar(
        select(func.count()).select_from(Investigation).where(Investigation.status.in_(PENDING))
    )
    if pending >= MAX_PENDING:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Investigation queue is full")

    # The default question deliberately omits the log message. Message text is
    # attacker-controllable and already reaches the model as tool evidence,
    # where the prompt treats it as untrusted data; copying it into the question
    # would additionally place it in the instruction position for no benefit.
    # The agent finds the line itself through the log tools.
    question = body.question or (
        f"Operational log evidence was selected for {candidate.service} at "
        f"{candidate.occurred_at.isoformat()}. What is going on?"
    )
    scope = dict(candidate.scope)
    digest = hashlib.sha256(
        json.dumps({"candidate": candidate.id, "question": question}, sort_keys=True).encode()
    ).hexdigest()

    run = Investigation(
        question=question,
        system=body.system,
        scope=scope,
        request_sha256=digest,
    )
    session.add(run)
    await session.flush()
    candidate.investigation_id = run.id
    candidate.status = "promoted"
    await session.commit()
    await session.refresh(run)
    return _public(run)


@router.get("", dependencies=[Depends(require_investigation_key)])
async def list_investigations(
    session: AsyncSession = Depends(get_session),
    limit: int = 50,
    offset: int = 0,
):
    if not 1 <= limit <= 100 or offset < 0:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid pagination")
    rows = await session.scalars(
        select(Investigation).order_by(Investigation.created_at.desc()).limit(limit).offset(offset)
    )
    return [_public(run) for run in rows]


async def _load(investigation_id: str, session: AsyncSession) -> Investigation:
    run = await session.get(Investigation, investigation_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown investigation")
    return run


@router.get("/{investigation_id}", dependencies=[Depends(require_investigation_key)])
async def get_investigation(investigation_id: str, session: AsyncSession = Depends(get_session)):
    return _public(await _load(investigation_id, session))


@router.get("/{investigation_id}/events", dependencies=[Depends(require_investigation_key)])
async def get_events(
    investigation_id: str,
    session: AsyncSession = Depends(get_session),
    after: int = 0,
    limit: int = 200,
):
    if not 1 <= limit <= 500 or after < 0:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid cursor")
    await _load(investigation_id, session)
    rows = await session.scalars(
        select(InvestigationEvent)
        .where(
            InvestigationEvent.investigation_id == investigation_id,
            InvestigationEvent.sequence > after,
        )
        .order_by(InvestigationEvent.sequence)
        .limit(limit)
    )
    return [
        {
            "sequence": event.sequence,
            "kind": event.kind,
            "payload": event.payload,
            "created_at": event.created_at,
        }
        for event in rows
    ]


@router.post("/{investigation_id}/cancel", dependencies=[Depends(require_investigation_key)])
async def cancel_investigation(investigation_id: str, session: AsyncSession = Depends(get_session)):
    run = await _load(investigation_id, session)
    if run.status not in CANCELLABLE:
        # Terminal states are preserved; cancelling a finished run is a no-op conflict.
        raise HTTPException(status.HTTP_409_CONFLICT, f"Run is already {run.status}")
    run.status = "cancelling" if run.status == "running" else "cancelled"
    await session.commit()
    return _public(run)
