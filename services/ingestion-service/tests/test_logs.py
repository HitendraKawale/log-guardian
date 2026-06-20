from app.schemas import AIResponse, Severity

PAYLOAD = {
    "service": "payment-api",
    "level": "CRITICAL",
    "message": "Database connection failed",
    "timestamp": "2026-06-18T10:00:00Z",
}


async def test_ingest_log_persists_with_ai_score(client):
    response = await client.post("/logs", json=PAYLOAD)
    assert response.status_code == 201
    body = response.json()
    assert body["id"] >= 1
    assert body["status"] == "scored"
    assert body["anomaly_score"] == 0.92
    assert body["is_anomaly"] is True
    assert body["predicted_severity"] == "high"


async def test_ingest_log_when_ai_unavailable(make_client):
    async with make_client(None) as client:
        response = await client.post("/logs", json=PAYLOAD)
        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "unscored"
        assert body["anomaly_score"] is None
        assert body["is_anomaly"] is None


async def test_ingest_validates_log_level(client):
    bad = {**PAYLOAD, "level": "NOPE"}
    response = await client.post("/logs", json=bad)
    assert response.status_code == 422


async def test_get_log_by_id(client):
    created = (await client.post("/logs", json=PAYLOAD)).json()
    response = await client.get(f"/logs/{created['id']}")
    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


async def test_get_missing_log_returns_404(client):
    response = await client.get("/logs/99999")
    assert response.status_code == 404


async def test_stream_disabled_returns_503(client):
    # Kafka is disabled by default in tests.
    response = await client.post("/logs/stream", json=PAYLOAD)
    assert response.status_code == 503


async def test_list_logs_filters(make_client):
    anomaly = AIResponse(
        anomaly_score=0.9, is_anomaly=True, predicted_severity=Severity.HIGH
    )
    async with make_client(anomaly) as client:
        await client.post("/logs", json={**PAYLOAD, "service": "auth", "level": "INFO"})
        await client.post("/logs", json={**PAYLOAD, "service": "gateway", "level": "ERROR"})

        by_service = await client.get("/logs", params={"service": "auth"})
        assert [r["service"] for r in by_service.json()] == ["auth"]

        by_level = await client.get("/logs", params={"level": "ERROR"})
        assert [r["level"] for r in by_level.json()] == ["ERROR"]

        anomalous = await client.get("/logs", params={"anomalous": "true"})
        assert len(anomalous.json()) == 2
        assert all(r["is_anomaly"] for r in anomalous.json())


async def test_list_logs_returns_newest_first(make_client):
    low = AIResponse(anomaly_score=0.1, is_anomaly=False, predicted_severity=Severity.LOW)
    async with make_client(low) as client:
        await client.post("/logs", json={**PAYLOAD, "message": "first"})
        await client.post("/logs", json={**PAYLOAD, "message": "second"})
        response = await client.get("/logs")
        assert response.status_code == 200
        messages = [item["message"] for item in response.json()]
        assert messages == ["second", "first"]
