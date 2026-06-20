"""Log Guardian ingestion service.

Accepts logs, enriches them with anomaly scores from the AI service, and
persists them. Exposes health, readiness and Prometheus metrics endpoints.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware

from .config import settings
from .database import init_db
from .producer import start_producer, stop_producer
from .routes import health, logs
from .security import rate_limit_middleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await start_producer()
    yield
    await stop_producer()


app = FastAPI(
    title="Log Guardian Ingestion Service",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(BaseHTTPMiddleware, dispatch=rate_limit_middleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(logs.router)


@app.get("/metrics", tags=["Monitoring"])
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
