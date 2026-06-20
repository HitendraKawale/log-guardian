async def test_model_info_proxies_ai_service(client):
    response = await client.get("/model/info")
    assert response.status_code == 200
    body = response.json()
    assert body["current_version"] == "v-test"
    assert body["analyzer"] == "model"
