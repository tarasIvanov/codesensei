"""Integration tests against the FastAPI app via httpx.AsyncClient."""


async def test_healthz_all_ok(async_client, mock_probes):
    mock_probes({"db": "ok", "vector": "ok"}, "ok")
    response = await async_client.get("/healthz")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["db"] == "ok"
    assert body["redis"] == "ok"
    assert body["extensions"]["vector"] == "ok"


async def test_healthz_db_down(async_client, mock_probes):
    mock_probes({"db": "down", "vector": "unknown"}, "ok")
    response = await async_client.get("/healthz")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["db"] == "down"
    assert "db" in body["failing"]


async def test_healthz_redis_down(async_client, mock_probes):
    mock_probes({"db": "ok", "vector": "ok"}, "down")
    response = await async_client.get("/healthz")
    assert response.status_code == 503
    body = response.json()
    assert body["redis"] == "down"
    assert "redis" in body["failing"]


async def test_healthz_vector_missing(async_client, mock_probes):
    mock_probes({"db": "ok", "vector": "missing"}, "ok")
    response = await async_client.get("/healthz")
    assert response.status_code == 503
    body = response.json()
    assert body["extensions"]["vector"] == "missing"
    assert "vector" in body["failing"]


async def test_api_prefix_alias_returns_same_envelope(async_client, mock_probes):
    """/healthz and /api/healthz must return identical responses."""
    mock_probes({"db": "ok", "vector": "ok"}, "ok")
    r1 = await async_client.get("/healthz")
    r2 = await async_client.get("/api/healthz")
    assert r1.status_code == r2.status_code == 200
    assert r1.json() == r2.json()
