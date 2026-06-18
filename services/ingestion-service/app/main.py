"""Log Guardian ingestion service.

Accepts logs, enriches them with anomaly scores from the AI service, and
persists them. Exposes health, readiness and Prometheus metrics endpoints.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from .database import init_db
from .routes import health, logs


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="Log Guardian Ingestion Service",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(health.router)
app.include_router(logs.router)


@app.get("/metrics", tags=["Monitoring"])
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
