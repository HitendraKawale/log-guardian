from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)

ANOMALOUS = {
    "service": "payment-api",
    "level": "CRITICAL",
    "message": "Database connection refused, request failed",
    "timestamp": "2026-06-18T03:00:00Z",
}
BENIGN = {
    "service": "payment-api",
    "level": "DEBUG",
    "message": "health check ok",
    "timestamp": "2026-06-18T12:00:00Z",
}


def _score(payload: dict) -> dict:
    response = client.post("/analyze", json=payload)
    assert response.status_code == 200
    return response.json()


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["analyzer"] in {"model", "heuristic"}


def test_metrics_exposes_prometheus_format():
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "ai_analyze_requests_total" in response.text


def test_analyze_returns_valid_contract():
    body = _score(ANOMALOUS)
    assert 0.0 <= body["anomaly_score"] <= 1.0
    assert isinstance(body["is_anomaly"], bool)
    assert body["predicted_severity"] in {"low", "medium", "high"}


def test_anomalous_scores_higher_than_benign():
    assert _score(ANOMALOUS)["anomaly_score"] > _score(BENIGN)["anomaly_score"]


def test_clear_anomaly_is_flagged():
    body = _score(ANOMALOUS)
    assert body["is_anomaly"] is True
    assert body["predicted_severity"] == "high"


def test_analyze_rejects_invalid_level():
    payload = {**BENIGN, "level": "NOPE"}
    response = client.post("/analyze", json=payload)
    assert response.status_code == 422
