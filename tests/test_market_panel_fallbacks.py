import pytest

from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_market_industry_rank_falls_back_to_sina_when_eastmoney_fails(monkeypatch):
    from app.utils.cache import cache
    import app.datasources.eastmoney as eastmoney_module
    import app.datasources.sina as sina_module

    await cache.clear()

    async def fake_get_industry_rank(self, sort_by: str, order: str, limit: int):
        raise RuntimeError("push2 blocked")

    async def fake_board_rank(self, category: str, limit: int, sort: str, order: str):
        assert category == "hangye"
        assert limit == 2
        return [
            {
                "bk_code": "new_test",
                "name": "测试行业",
                "change_percent": 1.23,
                "main_net_inflow": 123456789.0,
                "main_net_inflow_percent": 3.21,
                "leader_stock_code": "sz000001",
                "leader_stock_name": "平安银行",
                "leader_change_percent": 5.0,
            }
        ]

    monkeypatch.setattr(eastmoney_module.EastMoneyClient, "get_industry_rank", fake_get_industry_rank)
    monkeypatch.setattr(sina_module.SinaClient, "get_board_money_flow_rank", fake_board_rank)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/market/industry-rank?sort_by=change_percent&order=desc&limit=2")
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["code"] == 0
        assert payload["data"]["items"][0]["bk_name"] == "测试行业"


@pytest.mark.asyncio
async def test_market_concept_rank_falls_back_to_sina_when_eastmoney_fails(monkeypatch):
    from app.utils.cache import cache
    import app.datasources.eastmoney as eastmoney_module
    import app.datasources.sina as sina_module

    await cache.clear()

    async def fake_get_concept_rank(self, sort_by: str, order: str, limit: int):
        raise RuntimeError("push2 blocked")

    async def fake_board_rank(self, category: str, limit: int, sort: str, order: str):
        assert category == "gainian"
        assert limit == 2
        return [
            {
                "bk_code": "gn_test",
                "name": "测试概念",
                "change_percent": -2.0,
                "main_net_inflow": -100.0,
                "main_net_inflow_percent": -1.0,
                "leader_stock_code": "sh600000",
                "leader_stock_name": "浦发银行",
                "leader_change_percent": -3.0,
            }
        ]

    monkeypatch.setattr(eastmoney_module.EastMoneyClient, "get_concept_rank", fake_get_concept_rank)
    monkeypatch.setattr(sina_module.SinaClient, "get_board_money_flow_rank", fake_board_rank)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/market/concept-rank?sort_by=change_percent&order=desc&limit=2")
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["code"] == 0
        assert payload["data"]["items"][0]["bk_name"] == "测试概念"


@pytest.mark.asyncio
async def test_market_industry_money_flow_falls_back_to_sina_when_eastmoney_fails(monkeypatch):
    from app.utils.cache import cache
    import app.datasources.eastmoney as eastmoney_module
    import app.datasources.sina as sina_module

    await cache.clear()

    async def fake_board_money_flow_rank(self, category: str, sort_by: str, order: str, limit: int):
        raise RuntimeError("push2 blocked")

    async def fake_board_rank(self, category: str, limit: int, sort: str, order: str):
        assert category == "hangye"
        assert sort == "netamount"
        return [
            {"bk_code": "new_a", "name": "电网设备", "change_percent": 1.0, "main_net_inflow": 123.0, "main_net_inflow_percent": 2.0}
        ]

    monkeypatch.setattr(eastmoney_module.EastMoneyClient, "get_board_money_flow_rank", fake_board_money_flow_rank)
    monkeypatch.setattr(sina_module.SinaClient, "get_board_money_flow_rank", fake_board_rank)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/market/industry-money-flow?category=hangye&sort_by=main_inflow")
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["code"] == 0
        assert isinstance(payload["data"], list)
        assert payload["data"][0]["name"] == "电网设备"


@pytest.mark.asyncio
async def test_market_stock_money_rank_falls_back_to_sina_when_eastmoney_fails(monkeypatch):
    from app.utils.cache import cache
    import app.datasources.eastmoney as eastmoney_module
    import app.datasources.sina as sina_module

    await cache.clear()

    async def fake_money_flow_rank(self, sort_by: str, order: str, limit: int):
        raise RuntimeError("push2 blocked")

    async def fake_stock_money_rank(self, limit: int, sort: str, order: str):
        assert sort == "r0_net"
        assert limit == 5
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
    monkeypatch.setattr(sina_module.SinaClient, "get_stock_money_rank", fake_stock_money_rank)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/market/stock-money-rank?sort_by=zjlr&limit=5")
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["code"] == 0
        assert isinstance(payload["data"], list)
        assert payload["data"][0]["stock_code"] == "002471"


@pytest.mark.asyncio
async def test_stock_rank_falls_back_to_sina_when_eastmoney_returns_empty(monkeypatch):
    from app.utils.cache import cache
    import app.datasources.eastmoney as eastmoney_module
    import app.datasources.sina as sina_module

    await cache.clear()

    async def fake_stock_rank(self, sort_by: str, order: str, limit: int, market: str):
        return []

    async def fake_sina_rank(self, sort_by: str, order: str, limit: int, market: str):
        assert sort_by == "change_percent"
        return [
            {
                "stock_code": "600000",
                "stock_name": "浦发银行",
                "current_price": 10.0,
                "change_percent": 1.0,
                "volume": 100,
                "amount": 1000.0,
                "pe": 5.0,
                "pb": 0.8,
            }
        ]

    monkeypatch.setattr(eastmoney_module.EastMoneyClient, "get_stock_rank_enhanced", fake_stock_rank)
    monkeypatch.setattr(sina_module.SinaClient, "get_stock_rank", fake_sina_rank)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/stock/rank?sort_by=change_percent&order=desc&limit=50&market=all")
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["code"] == 0
        assert payload["data"][0]["pe"] == 5.0
