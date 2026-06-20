"""API-key authentication and a small in-memory rate limiter.

Both are opt-in via settings, so the service stays open and dependency-free for
local development unless explicitly locked down.
"""
import time
from collections import defaultdict

from fastapi import Header, HTTPException, Request, status
from fastapi.responses import JSONResponse

from .config import settings


async def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Dependency: enforce the API key when one is configured."""
    if not settings.api_key:
        return
    if x_api_key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing API key"
        )


class RateLimiter:
    """Fixed-window per-IP limiter. Adequate for a single instance / demo."""

    def __init__(self, limit_per_minute: int) -> None:
        self.limit = limit_per_minute
        self._hits: dict[str, list[float]] = defaultdict(list)

    def allow(self, client: str) -> bool:
        if self.limit <= 0:
            return True
        now = time.monotonic()
        window = [t for t in self._hits[client] if now - t < 60.0]
        window.append(now)
        self._hits[client] = window
        return len(window) <= self.limit


_limiter = RateLimiter(settings.rate_limit_per_minute)


async def rate_limit_middleware(request: Request, call_next):
    client = request.client.host if request.client else "unknown"
    if not _limiter.allow(client):
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={"detail": "Rate limit exceeded"},
        )
    return await call_next(request)
