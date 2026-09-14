"""One small demo application, deployed twice as checkout and inventory.

Checkout calls inventory over real HTTP with a deadline, so an injected
inventory delay produces genuine upstream timeouts, not scripted errors.

Fault controls live on a SEPARATE port (FAULT_PORT) that the demo Compose
file binds to localhost only. They are owner-operated and are not registered
as agent tools anywhere.
"""

import asyncio
import logging
import os
import time
from datetime import UTC, datetime

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from pydantic import BaseModel, Field

REQUESTS = Counter("demo_requests_total", "Requests handled", ["service", "route", "status"])
LATENCY = Histogram("demo_request_seconds", "Request latency", ["service", "route"])


class Delay(BaseModel):
    seconds: float = Field(ge=0, le=30)


def create_apps(role, inventory_url="", ingestion_url="", deadline_ms=1000):
    """Build (public_app, fault_app, fault_state) for one role instance."""
    logger = logging.getLogger(role)
    # Owner-controlled fault state; only the private fault app mutates it.
    fault = {"delay_seconds": 0.0}

    async def emit(level: str, message: str) -> None:
        """Best-effort structured log to the ingestion API; never fails the request."""
        if not ingestion_url:
            return
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                await client.post(
                    f"{ingestion_url}/logs",
                    json={
                        "service": role,
                        "level": level,
                        "message": message,
                        "timestamp": datetime.now(UTC).isoformat(),
                    },
                )
        except httpx.HTTPError:
            logger.warning("ingestion unavailable; dropped log")

    app = FastAPI(title=f"demo-{role}")

    @app.get("/health")
    async def health():
        return {"role": role, "status": "ok"}

    @app.get("/metrics")
    async def metrics():
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @app.get("/stock/{item_id}")
    async def stock(item_id: str):
        started = time.monotonic()
        delay = fault["delay_seconds"]
        if delay:
            await asyncio.sleep(delay)
        elapsed = (time.monotonic() - started) * 1000
        REQUESTS.labels(role, "stock", "200").inc()
        LATENCY.labels(role, "stock").observe(elapsed / 1000)
        await emit("INFO", f"stock request {item_id} completed in {elapsed:.0f}ms; available=42")
        return {"item_id": item_id, "available": 42, "elapsed_ms": elapsed}

    @app.get("/checkout/{order_id}")
    async def checkout(order_id: str):
        started = time.monotonic()
        await emit(
            "INFO", f"order {order_id} started; dependency=inventory; deadline_ms={deadline_ms}"
        )
        try:
            async with httpx.AsyncClient(timeout=deadline_ms / 1000) as client:
                upstream = await client.get(f"{inventory_url}/stock/{order_id}")
                upstream.raise_for_status()
        except httpx.TimeoutException:
            elapsed = (time.monotonic() - started) * 1000
            REQUESTS.labels(role, "checkout", "504").inc()
            LATENCY.labels(role, "checkout").observe(elapsed / 1000)
            await emit(
                "ERROR",
                f"order {order_id} inventory read timed out after {deadline_ms}ms; status=504",
            )
            raise HTTPException(504, "inventory timeout") from None
        except httpx.HTTPError:
            REQUESTS.labels(role, "checkout", "502").inc()
            await emit("ERROR", f"order {order_id} inventory request failed; status=502")
            raise HTTPException(502, "inventory unavailable") from None
        elapsed = (time.monotonic() - started) * 1000
        REQUESTS.labels(role, "checkout", "200").inc()
        LATENCY.labels(role, "checkout").observe(elapsed / 1000)
        await emit("INFO", f"order {order_id} completed in {elapsed:.0f}ms; status=200")
        return {"order_id": order_id, "status": "confirmed", "elapsed_ms": elapsed}

    # --- private fault-control app (separate port, localhost-bound in Compose) --
    fault_app = FastAPI(title=f"demo-{role}-faults")

    @fault_app.post("/fault/delay")
    async def set_delay(body: Delay):
        fault["delay_seconds"] = body.seconds
        logger.warning("fault delay set to %.2fs", body.seconds)
        return dict(fault)

    @fault_app.post("/fault/reset")
    async def reset_fault():
        fault["delay_seconds"] = 0.0
        return dict(fault)

    @fault_app.get("/fault")
    async def get_fault():
        return dict(fault)

    return app, fault_app, fault


async def serve() -> None:
    role = os.environ.get("DEMO_ROLE", "checkout")
    app, fault_app, _ = create_apps(
        role,
        inventory_url=os.environ.get("INVENTORY_URL", "http://localhost:9002"),
        ingestion_url=os.environ.get("INGESTION_URL", ""),
        deadline_ms=int(os.environ.get("CHECKOUT_DEADLINE_MS", "1000")),
    )
    port = int(os.environ.get("PORT", "9001"))
    servers = [uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=port, log_level="warning"))]
    if role == "inventory":
        fault_port = int(os.environ.get("FAULT_PORT", "9101"))
        servers.append(
            uvicorn.Server(
                uvicorn.Config(fault_app, host="0.0.0.0", port=fault_port, log_level="warning")
            )
        )
    await asyncio.gather(*[server.serve() for server in servers])


if __name__ == "__main__":
    asyncio.run(serve())
