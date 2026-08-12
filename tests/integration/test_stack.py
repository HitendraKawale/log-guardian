"""End-to-end tests against the running stack.

Each test names the seam it covers, because the point of this file is the seams
the unit suites replace with fakes.
"""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime

import httpx
import pytest

from tests.integration.conftest import (
    AI_URL,
    FRONTEND_URL,
    JAEGER_URL,
    PROMETHEUS_URL,
    wait_until,
)

pytestmark = pytest.mark.integration


def _log(message: str, level: str = "CRITICAL") -> dict:
    return {
        "service": "integration-test",
        "level": level,
        "message": message,
        "timestamp": datetime.now(UTC).isoformat(),
    }


def _marker() -> str:
    return f"integration marker {uuid.uuid4()}"


# --- ingestion -> ai-service -> postgres, over real HTTP -------------------


def test_sync_ingest_is_scored_by_the_real_ai_service(client):
    response = client.post("/logs", json=_log("database connection refused, request failed"))
    assert response.status_code == 201

    body = response.json()
    # "scored" means the ingestion container reached the AI container over the
    # network and got a usable response back. A fake cannot produce this.
    assert body["status"] == "scored"
    assert 0.0 <= body["anomaly_score"] <= 1.0
    assert body["predicted_severity"] in {"low", "medium", "high"}
    assert body["id"] >= 1


def test_ingested_log_is_readable_back_from_postgres(client):
    marker = _marker()
    created = client.post("/logs", json=_log(marker)).json()

    fetched = client.get(f"/logs/{created['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["message"] == marker


def test_ai_service_scores_severity_consistently(client):
    quiet = client.post("/logs", json=_log("health check ok", level="DEBUG")).json()
    loud = client.post("/logs", json=_log("fatal panic: segfault", level="CRITICAL")).json()
    assert loud["anomaly_score"] > quiet["anomaly_score"]


# --- the Kafka path: producer -> broker -> consumer -> postgres ------------


def test_streamed_log_reaches_the_database_via_kafka(client):
    marker = _marker()
    response = client.post("/logs/stream", json=_log(marker))
    assert response.status_code == 202
    assert response.json() == {"status": "queued"}

    def find() -> dict | None:
        rows = client.get("/logs", params={"limit": 200, "service": "integration-test"}).json()
        return next((row for row in rows if row["message"] == marker), None)

    # Nothing wrote this row except the consumer worker, so its presence proves
    # produce -> broker -> consume -> persist end to end.
    record = wait_until(find, timeout=60)
    assert record["status"] == "scored"


# --- trace context survives the broker ------------------------------------


def test_one_trace_spans_both_ingestion_and_the_consumer(client):
    # Only traces started after this point count, otherwise the test would
    # happily pass on a joined trace left in Jaeger by an earlier run.
    started_at_micros = int(time.time() * 1_000_000)
    client.post("/logs/stream", json=_log(_marker()))

    def joined_trace() -> dict | None:
        response = httpx.get(
            f"{JAEGER_URL}/api/traces",
            params={"service": "log-consumer", "limit": 20, "start": started_at_micros},
            timeout=10.0,
        )
        for trace in response.json().get("data", []):
            if min(span["startTime"] for span in trace["spans"]) < started_at_micros:
                continue
            services = {p["serviceName"] for p in trace.get("processes", {}).values()}
            if {"ingestion-service", "log-consumer"} <= services:
                return trace
        return None

    # The producer injects W3C traceparent into Kafka headers and the consumer
    # extracts it. If that broke, these would be two unrelated traces.
    trace = wait_until(joined_trace, timeout=90)
    services = {p["serviceName"] for p in trace["processes"].values()}
    assert {"ingestion-service", "log-consumer"} <= services
    assert len({span["traceID"] for span in trace["spans"]}) == 1


# --- migrations actually ran against Postgres -----------------------------


def test_postgres_schema_came_from_alembic(client):
    # Feedback columns arrive in migration 0002; their presence in a response
    # means the container ran `alembic upgrade head` against real Postgres
    # rather than falling back to SQLite create_all.
    created = client.post("/logs", json=_log(_marker())).json()
    assert "true_label" in created

    labelled = client.post(f"/logs/{created['id']}/feedback", json={"is_anomaly": True})
    assert labelled.status_code == 200
    assert labelled.json()["true_label"] is True


def test_feedback_export_returns_labelled_examples(client):
    created = client.post("/logs", json=_log(_marker())).json()
    client.post(f"/logs/{created['id']}/feedback", json={"is_anomaly": False})

    exported = client.get("/feedback/export", params={"limit": 1000}).json()
    assert any(row["true_label"] is False for row in exported)


# --- health, readiness, and the model proxy -------------------------------


def test_readiness_reports_the_database_is_reachable(client):
    assert client.get("/readiness").json() == {"status": "ready"}


def test_model_info_is_proxied_from_the_ai_service(client):
    proxied = client.get("/model/info")
    assert proxied.status_code == 200
    direct = httpx.get(f"{AI_URL}/model/info", timeout=10.0).json()
    assert proxied.json()["analyzer"] == direct["analyzer"]


# --- monitoring is wired, not just configured ------------------------------


def test_prometheus_is_scraping_both_services():
    def both_up() -> bool:
        response = httpx.get(f"{PROMETHEUS_URL}/api/v1/query", params={"query": "up"}, timeout=10.0)
        targets = {
            result["metric"].get("job"): result["value"][1]
            for result in response.json()["data"]["result"]
        }
        return targets.get("ingestion-service") == "1" and targets.get("ai-service") == "1"

    assert wait_until(both_up, timeout=90)


def test_alert_rules_are_loaded():
    response = httpx.get(f"{PROMETHEUS_URL}/api/v1/rules", timeout=10.0)
    names = {
        rule["name"]
        for group in response.json()["data"]["groups"]
        for rule in group.get("rules", [])
    }
    assert names, "Prometheus loaded no alert rules"


def test_ingestion_counter_increases_after_a_request(client):
    def counter() -> float:
        for line in client.get("/metrics").text.splitlines():
            if line.startswith("ingestion_logs_total "):
                return float(line.split()[1])
        return 0.0

    before = counter()
    client.post("/logs", json=_log(_marker()))
    assert counter() > before


# --- the dashboard is served ----------------------------------------------


def test_frontend_serves_the_dashboard():
    response = httpx.get(FRONTEND_URL, timeout=10.0)
    assert response.status_code == 200
    assert "Log Guardian" in response.text
