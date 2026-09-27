"""Export of human-labelled logs for model retraining."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session
from ..models import Log
from ..schemas import LabeledLog
from ..security import require_api_key

router = APIRouter(prefix="/feedback", tags=["Feedback"], dependencies=[Depends(require_api_key)])


@router.get("/export", response_model=list[LabeledLog])
async def export_feedback(
    limit: int = Query(1000, ge=1, le=10000),
    session: AsyncSession = Depends(get_session),
) -> list[Log]:
    """Return every log that has a human label, as training examples."""
    stmt = select(Log).where(Log.true_label.is_not(None)).order_by(Log.id).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())
