"""Disabling the unrelated classifier must avoid network work, not fake an outage."""

from datetime import UTC, datetime

import httpx
import pytest
from app.ai_client import AIClient
from app.schemas import LogCreate


@pytest.mark.parametrize("method", ["analyze", "model_info"])
async def test_empty_url_disables_network(monkeypatch, method):
    def forbidden_client(*args, **kwargs):
        raise AssertionError("disabled scoring constructed an HTTP client")

    monkeypatch.setattr(httpx, "AsyncClient", forbidden_client)
    client = AIClient("", 2.0)
    args = (
        []
        if method == "model_info"
        else [
            LogCreate(
                service="checkout", level="ERROR", message="timeout", timestamp=datetime.now(UTC)
            )
        ]
    )
    assert await getattr(client, method)(*args) is None


@pytest.mark.parametrize("method", ["analyze", "model_info"])
async def test_configured_outage_still_returns_none(monkeypatch, method):
    def unavailable(request):
        raise httpx.ConnectError("unavailable", request=request)

    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(unavailable), **kwargs),
    )
    client = AIClient("http://scorer:8001", 2.0)
    args = (
        []
        if method == "model_info"
        else [
            LogCreate(
                service="checkout", level="ERROR", message="timeout", timestamp=datetime.now(UTC)
            )
        ]
    )
    assert await getattr(client, method)(*args) is None
