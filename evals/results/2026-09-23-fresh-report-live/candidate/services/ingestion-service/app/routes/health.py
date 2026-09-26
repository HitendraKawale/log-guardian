"""Liveness and readiness probes."""

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session

router = APIRouter(tags=["Health"])


@router.get("/health")
async def health_check() -> dict[str, str]:
    """Liveness: the process is up."""
    return {"status": "ok"}


@router.get("/readiness")
async def readiness_check(
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    """Readiness: dependencies (the database) are reachable."""
    await session.execute(text("SELECT 1"))
    return {"status": "ready"}
