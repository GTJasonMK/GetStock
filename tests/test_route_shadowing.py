import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_datasources_configs_route_is_reachable(client):
    resp = await client.get("/api/v1/datasources/configs")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["code"] == 0
    assert isinstance(payload.get("data"), list)


@pytest.mark.asyncio
async def test_follow_sort_route_is_reachable(client):
    resp = await client.put("/api/v1/stock/follow/sort", json=["sh600000"])
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["code"] == 0
    assert payload["message"] == "排序成功"
