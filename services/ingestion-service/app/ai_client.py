"""Client for the downstream AI analysis service.

Calls are best-effort: if the AI service is slow or unavailable the ingestion
path must still succeed, so failures are swallowed and surfaced as ``None``.
The log is then persisted in an ``unscored`` state and can be re-scored later.
"""

import logging

import httpx

from .config import settings
from .schemas import AIResponse, LogCreate

logger = logging.getLogger(__name__)


class AIClient:
    def __init__(self, base_url: str, timeout: float) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    async def analyze(self, log: LogCreate) -> AIResponse | None:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{self._base_url}/analyze",
                    json=log.model_dump(mode="json"),
                )
                response.raise_for_status()
                return AIResponse(**response.json())
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("AI analysis unavailable: %s", exc)
            return None

    async def model_info(self) -> dict | None:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(f"{self._base_url}/model/info")
                response.raise_for_status()
                return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("AI model info unavailable: %s", exc)
            return None


def get_ai_client() -> AIClient:
    """FastAPI dependency. Overridable in tests."""
    return AIClient(settings.ai_service_url, settings.ai_timeout)
