import pytest

from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_market_stock_money_rank_maps_sort_fields(monkeypatch):
    import app.datasources.eastmoney as eastmoney_module

    calls = []

    async def fake_money_flow_rank(self, sort_by: str, order: str, limit: int):
        calls.append((sort_by, order, limit))
        return [
            {
                "stock_code": "002471",
                "stock_name": "中超控股",
                "current_price": 8.61,
                "change_percent": 9.96,
                "main_net_inflow": 1234.0,
                "main_net_inflow_percent": 1.23,
            }
        ]

    monkeypatch.setattr(eastmoney_module.EastMoneyClient, "get_money_flow_rank", fake_money_flow_rank)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 兼容前端 sort_by=zjlr
        resp = await ac.get("/api/v1/market/stock-money-rank?sort_by=zjlr&limit=5")
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["code"] == 0
        assert isinstance(payload["data"], list)
        assert payload["data"][0]["stock_code"] == "002471"
        assert calls[-1] == ("main_net_inflow", "desc", 5)

        # 兼容前端 sort_by=trade
        resp = await ac.get("/api/v1/market/stock-money-rank?sort_by=trade&limit=5")
        assert resp.status_code == 200
        assert calls[-1] == ("current_price", "desc", 5)
