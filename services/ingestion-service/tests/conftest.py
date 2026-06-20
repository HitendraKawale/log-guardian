import pytest_asyncio
from app.ai_client import AIClient, get_ai_client
from app.database import Base, get_session
from app.main import app
from app.schemas import AIResponse, Severity
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool


class FakeAIClient(AIClient):
    """Returns a fixed score without any network call."""

    def __init__(self, response: AIResponse | None) -> None:  # noqa: D401
        self._response = response

    async def analyze(self, log) -> AIResponse | None:
        return self._response

    async def model_info(self) -> dict:
        return {"analyzer": "model", "current_version": "v-test"}


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def make_client(engine):
    """Factory: build a test client with a configurable fake AI response."""
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_session():
        async with session_factory() as session:
            yield session

    def _make(ai_response: AIResponse | None) -> AsyncClient:
        app.dependency_overrides[get_session] = override_get_session
        app.dependency_overrides[get_ai_client] = lambda: FakeAIClient(ai_response)
        transport = ASGITransport(app=app)
        return AsyncClient(transport=transport, base_url="http://test")

    yield _make
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client(make_client):
    """Default client: AI flags the log as a high-severity anomaly."""
    anomaly = AIResponse(anomaly_score=0.92, is_anomaly=True, predicted_severity=Severity.HIGH)
    async with make_client(anomaly) as c:
        yield c
