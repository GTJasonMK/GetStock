import pytest

from httpx import ASGITransport, AsyncClient

from app.main import app
from app.schemas.market import IndustryRank, IndustryRankResponse, MarketIndex


@pytest.mark.asyncio
async def test_market_overview_api_returns_expected_structure(monkeypatch):
    import app.datasources.eastmoney as eastmoney_module
    import app.datasources.sina as sina_module

    async def fake_get_market_indices(self, codes):
        return [
            MarketIndex(
                code="sh000001",
                name="上证指数",
                current=3000.0,
                change_percent=1.23,
                change_amount=36.5,
                open=2980.0,
                high=3010.0,
                low=2975.0,
                prev_close=2963.5,
                volume=123,
                amount=456,
                amplitude=1.0,
                update_time="2026-02-02 15:00:00",
            )
        ]

    async def fake_a_spot_statistics(self):
        return {
            "up_count": 10,
            "down_count": 20,
            "flat_count": 30,
            "limit_up_count": 40,
            "limit_down_count": 5,
            "total_amount_yi": 12345.67,
        }

    async def fake_industry_rank(self, sort_by: str = "change_percent", order: str = "desc", limit: int = 5):
        items = [
            IndustryRank(
                bk_code="BK0001",
                bk_name="行业A",
                change_percent=2.5,
                turnover=100.0,
                leader_stock_code="sh600000",
                leader_stock_name="浦发银行",
                leader_change_percent=1.0,
                stock_count=100,
            )
        ]
        return IndustryRankResponse(items=items, update_time="2026-02-02 15:00:00")

    async def fake_north_flow(self, days: int = 1):
        # north-flow 接口返回“元”，MarketOverview 输出为“亿元”
        return {"current": {"total_inflow": 12.3 * 1e8}, "history": []}

    monkeypatch.setattr(sina_module.SinaClient, "get_market_indices", fake_get_market_indices)
    monkeypatch.setattr(eastmoney_module.EastMoneyClient, "get_a_spot_statistics", fake_a_spot_statistics)
    monkeypatch.setattr(eastmoney_module.EastMoneyClient, "get_industry_rank", fake_industry_rank)
    monkeypatch.setattr(eastmoney_module.EastMoneyClient, "get_north_flow", fake_north_flow)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/market/overview")
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["code"] == 0

        data = payload["data"]
        assert data["date"]
        assert data["available"] is True
        assert data["reason"] == ""
        assert data["up_count"] == 10
        assert data["down_count"] == 20
        assert data["flat_count"] == 30
        assert data["limit_up_count"] == 40
        assert data["limit_down_count"] == 5
        assert data["total_amount"] == 12345.67
        assert data["north_flow"] == 12.3

        assert len(data["indices"]) == 1
        assert data["indices"][0]["code"] == "sh000001"
        assert len(data["top_sectors"]) == 1
        assert len(data["bottom_sectors"]) == 1


@pytest.mark.asyncio
async def test_market_overview_api_fallbacks_to_sina_when_eastmoney_snapshot_fails(monkeypatch):
    import app.datasources.eastmoney as eastmoney_module
    import app.datasources.sina as sina_module
    from app.utils.cache import cache

    # market_overview 采用内存缓存，为避免上一用例缓存命中影响本用例断言，这里清空缓存
    await cache.clear()

    async def fake_get_market_indices(self, codes):
        return [
            MarketIndex(
                code="sh000001",
                name="上证指数",
                current=3000.0,
                change_percent=1.23,
                change_amount=36.5,
                open=2980.0,
                high=3010.0,
                low=2975.0,
                prev_close=2963.5,
                volume=123,
                amount=456,
                amplitude=1.0,
                update_time="2026-02-02 15:00:00",
            )
        ]

    async def fake_eastmoney_stats_fail(self):
        raise RuntimeError("东财快照不可用")

    async def fake_sina_stats(self):
        return {
            "up_count": 1,
            "down_count": 2,
            "flat_count": 3,
            "limit_up_count": 4,
            "limit_down_count": 5,
            "total_amount_yi": 678.9,
        }

    async def fake_industry_rank(self, sort_by: str = "change_percent", order: str = "desc", limit: int = 5):
        items = [
            IndustryRank(
                bk_code="BK0001",
                bk_name="行业A",
                change_percent=2.5,
                turnover=100.0,
                leader_stock_code="sh600000",
                leader_stock_name="浦发银行",
                leader_change_percent=1.0,
                stock_count=100,
            )
        ]
        return IndustryRankResponse(items=items, update_time="2026-02-02 15:00:00")

    async def fake_north_flow(self, days: int = 1):
        return {"current": None, "history": []}

    monkeypatch.setattr(sina_module.SinaClient, "get_market_indices", fake_get_market_indices)
    monkeypatch.setattr(eastmoney_module.EastMoneyClient, "get_a_spot_statistics", fake_eastmoney_stats_fail)
    monkeypatch.setattr(sina_module.SinaClient, "get_a_spot_statistics", fake_sina_stats)
    monkeypatch.setattr(eastmoney_module.EastMoneyClient, "get_industry_rank", fake_industry_rank)
    monkeypatch.setattr(eastmoney_module.EastMoneyClient, "get_north_flow", fake_north_flow)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/market/overview")
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["code"] == 0

        data = payload["data"]
        assert data["available"] is True
        assert data["up_count"] == 1
        assert data["down_count"] == 2
        assert data["flat_count"] == 3
        assert data["limit_up_count"] == 4
        assert data["limit_down_count"] == 5
        assert data["total_amount"] == 678.9
