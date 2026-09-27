"""Review the investigation candidate queue.

Nothing here spends money, and that is the point of keeping it separate from
`routes/investigations.py`. A candidate is the trigger's suggestion that a
message family is worth a human's attention; an investigation is a paid model
run. This router can list candidates and dismiss them, and it cannot start one:
promotion lives on the investigations router behind INVESTIGATION_API_KEY, so
the capability to review and the capability to spend are separate keys.

It therefore sits behind the ordinary log API key rather than
`INVESTIGATION_API_KEY`: reading the queue is no more sensitive than reading the
logs it was derived from, and gating it behind the execution key would imply a
spending capability it does not have."""

from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, computed_field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_session
from ..models import DetectorState, InvestigationCandidate
from ..security import require_api_key
from ..trigger import detector_readiness

router = APIRouter(prefix="/candidates", tags=["candidates"])

DISMISSABLE = {"new"}


class CandidateOut(BaseModel):
    """``investigation_id`` is set only once a human promoted this candidate."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    service: str
    level: str
    message: str
    template: str
    reason: str
    scope: dict
    status: str
    log_id: int | None
    investigation_id: str | None
    occurred_at: datetime
    created_at: datetime
    dismissed_at: datetime | None
    last_seen_at: datetime | None
    occurrence_count: int
    signal_details: dict

    @computed_field
    @property
    def activity(self) -> Literal["active", "quiet", "legacy"]:
        if not self.signal_details or self.signal_details.get("legacy"):
            return "legacy"
        at = self.last_seen_at or self.occurred_at
        at = at.replace(tzinfo=at.tzinfo or UTC)
        return "quiet" if (datetime.now(UTC) - at).total_seconds() >= 600 else "active"


@router.get("", dependencies=[Depends(require_api_key)])
async def list_candidates(
    session: AsyncSession = Depends(get_session),
    status_filter: Literal["new", "dismissed", "promoted"] | None = Query(None, alias="status"),
    service: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict:
    """Newest first, because a review queue is worked from the top."""
    query = select(InvestigationCandidate)
    counter = select(func.count()).select_from(InvestigationCandidate)
    if status_filter:
        query = query.where(InvestigationCandidate.status == status_filter)
        counter = counter.where(InvestigationCandidate.status == status_filter)
    if service:
        query = query.where(InvestigationCandidate.service == service)
        counter = counter.where(InvestigationCandidate.service == service)

    rows = await session.execute(
        query.order_by(
            func.coalesce(
                InvestigationCandidate.last_seen_at, InvestigationCandidate.occurred_at
            ).desc(),
            InvestigationCandidate.id.desc(),
        )
        .limit(limit)
        .offset(offset)
    )
    total = await session.scalar(counter)
    return {
        "total": total or 0,
        "items": [CandidateOut.model_validate(row) for row in rows.scalars()],
    }


@router.get("/detectors", dependencies=[Depends(require_api_key)])
async def list_detectors(
    session: AsyncSession = Depends(get_session),
    service: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict:
    query = select(DetectorState)
    counter = select(func.count()).select_from(DetectorState)
    if service:
        query = query.where(DetectorState.service == service)
        counter = counter.where(DetectorState.service == service)
    rows = await session.scalars(query.order_by(DetectorState.service).limit(limit).offset(offset))
    now = datetime.now(UTC)
    return {
        "total": await session.scalar(counter) or 0,
        "items": [
            {
                "service": row.service,
                **detector_readiness(row.data, now, settings.trigger_warmup_logs),
            }
            for row in rows
        ],
    }


@router.get("/{candidate_id}", dependencies=[Depends(require_api_key)])
async def get_candidate(
    candidate_id: str, session: AsyncSession = Depends(get_session)
) -> CandidateOut:
    candidate = await session.get(InvestigationCandidate, candidate_id)
    if candidate is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Candidate not found")
    return CandidateOut.model_validate(candidate)


@router.post("/{candidate_id}/dismiss", dependencies=[Depends(require_api_key)])
async def dismiss_candidate(
    candidate_id: str, session: AsyncSession = Depends(get_session)
) -> CandidateOut:
    """Mark a candidate reviewed and not worth investigating.

    Idempotent: dismissing an already-dismissed candidate returns it unchanged
    rather than erroring, so a retried click cannot move the timestamp.
    """
    candidate = await session.get(InvestigationCandidate, candidate_id)
    if candidate is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Candidate not found")
    if candidate.status in DISMISSABLE:
        candidate.status = "dismissed"
        candidate.dismissed_at = datetime.now(UTC)
        await session.commit()
        await session.refresh(candidate)
    return CandidateOut.model_validate(candidate)
