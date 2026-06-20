"""Proxy to the AI service's model metadata, so the dashboard stays single-origin."""

from fastapi import APIRouter, Depends

from ..ai_client import AIClient, get_ai_client

router = APIRouter(tags=["Model"])


@router.get("/model/info")
async def model_info(ai: AIClient = Depends(get_ai_client)) -> dict:
    info = await ai.model_info()
    return info or {"current_version": None, "analyzer": "unavailable"}
