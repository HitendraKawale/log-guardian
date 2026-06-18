from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_metrics_exposes_prometheus_format():
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "ai_analyze_requests_total" in response.text


def test_analyze_returns_valid_contract():
    payload = {
        "service": "payment-api",
        "level": "CRITICAL",
        "message": "Database connection failed",
        "timestamp": "2026-06-18T10:00:00Z",
    }
    response = client.post("/analyze", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert 0.0 <= body["anomaly_score"] <= 1.0
    assert body["is_anomaly"] is True
    assert body["predicted_severity"] == "high"


def test_analyze_rejects_invalid_level():
    payload = {
        "service": "payment-api",
        "level": "NOPE",
        "message": "x",
        "timestamp": "2026-06-18T10:00:00Z",
    }
    response = client.post("/analyze", json=payload)
    assert response.status_code == 422
