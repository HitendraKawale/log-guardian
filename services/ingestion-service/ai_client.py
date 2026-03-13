import httpx
from app.config import settings
from app.schemas import AIResponse, LogCreate


async def analyze_log(log: LogCreate) -> AIResponse:
    async with httpx.AsyncClient(timeout=settings.AI_TIMEOUT) as client:
        response = await client.post(
            f"{settings.AI_SERVICE_URL}/analyze",
            json=log.dict()
        )
        response.raise_for_status()
        return AIResponse(**response.json())