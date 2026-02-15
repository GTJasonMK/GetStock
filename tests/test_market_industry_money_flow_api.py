import pytest

from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_market_industry_money_flow_api_returns_list(monkeypatch):
    import app.datasources.eastmoney as eastmoney_module

    async def fake_board_money_flow_rank(self, category: str, sort_by: str, order: str, limit: int):
        assert category in ("hangye", "gainian")
        assert order == "desc"
        assert limit == 50
        return [
            {
                "bk_code": "BK0001",
                "name": "电网设备",
                "change_percent": 1.23,
                "main_net_inflow": 123456789.0,
                "main_net_inflow_percent": 3.21,
            }
        ]

    monkeypatch.setattr(eastmoney_module.EastMoneyClient, "get_board_money_flow_rank", fake_board_money_flow_rank)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/market/industry-money-flow?category=hangye&sort_by=main_inflow")
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["code"] == 0
        assert isinstance(payload["data"], list)
        assert payload["data"][0]["name"] == "电网设备"
