from app.schemas import AIResponse, Severity

ANOMALY = AIResponse(anomaly_score=0.9, is_anomaly=True, predicted_severity=Severity.HIGH)

PAYLOAD = {
    "service": "payment-api",
    "level": "CRITICAL",
    "message": "Database connection refused",
    "timestamp": "2026-06-18T10:00:00Z",
}


async def test_submit_feedback_sets_true_label(client):
    created = (await client.post("/logs", json=PAYLOAD)).json()
    resp = await client.post(f"/logs/{created['id']}/feedback", json={"is_anomaly": False})
    assert resp.status_code == 200
    assert resp.json()["true_label"] is False


async def test_feedback_on_missing_log_404(client):
    resp = await client.post("/logs/99999/feedback", json={"is_anomaly": True})
    assert resp.status_code == 404


async def test_export_returns_only_labelled_logs(make_client):
    async with make_client(ANOMALY) as client:
        a = (await client.post("/logs", json=PAYLOAD)).json()
        await client.post("/logs", json={**PAYLOAD, "message": "no feedback here"})

        # label only the first
        await client.post(f"/logs/{a['id']}/feedback", json={"is_anomaly": True})

        export = await client.get("/feedback/export")
        assert export.status_code == 200
        rows = export.json()
        assert len(rows) == 1
        assert rows[0]["true_label"] is True
        assert rows[0]["message"] == PAYLOAD["message"]
        assert set(rows[0]) == {"service", "level", "message", "timestamp", "true_label"}
