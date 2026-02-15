import pytest

from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_chip_distribution_api_returns_available_when_provider_returns_data(monkeypatch):
    import app.datasources.chip_distribution as chip_module

    async def fake_fetch(symbol: str):
        assert symbol == "600519"
        return {
            "date": "2026-02-02",
            "profit_ratio": 0.42,
            "avg_cost": 100.0,
            "cost_90_low": 90.0,
            "cost_90_high": 110.0,
            "concentration_90": 0.2,
            "cost_70_low": 95.0,
            "cost_70_high": 105.0,
            "concentration_70": 0.1,
            "source": "akshare",
        }

    monkeypatch.setattr(chip_module, "fetch_chip_distribution_em", fake_fetch)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/stock/sh600519/chip-distribution")
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["code"] == 0
        data = payload["data"]
        assert data["stock_code"] == "sh600519"
        assert data["available"] is True
        assert data["data"]["profit_ratio"] == 0.42
        assert data["data"]["avg_cost"] == 100.0


@pytest.mark.asyncio
async def test_chip_distribution_api_returns_unavailable_for_non_a_share():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/stock/usAAPL/chip-distribution")
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["code"] == 0
        data = payload["data"]
        assert data["available"] is False
        assert "A股" in data["reason"]
