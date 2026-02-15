# Settings API Tests
"""
配置管理API测试
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_get_settings(client):
    """测试获取配置"""
    response = await client.get("/api/v1/settings")
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 0
    assert "data" in data


@pytest.mark.asyncio
async def test_update_settings(client):
    """测试更新配置"""
    response = await client.put("/api/v1/settings", json={
        "refresh_interval": 5,
        "language": "zh",
    })
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 0


@pytest.mark.asyncio
async def test_create_ai_config(client):
    """测试创建AI配置"""
    response = await client.post("/api/v1/settings/ai-configs", json={
        "name": "Test Config",
        "base_url": "https://api.openai.com",
        "api_key": "test-key",
        "model_name": "gpt-4",
    })
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 0
    assert data["data"]["name"] == "Test Config"
