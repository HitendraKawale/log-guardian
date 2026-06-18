async def test_health(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_readiness_checks_database(client):
    response = await client.get("/readiness")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


async def test_metrics(client):
    response = await client.get("/metrics")
    assert response.status_code == 200
    assert "ingestion_logs_total" in response.text
