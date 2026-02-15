import pytest
from sqlalchemy import delete

from app.database import async_session_maker
from app.models.stock import FollowedStock
from app.schemas.stock import StockQuote
from app.services.stock_service import StockService


@pytest.mark.asyncio
async def test_portfolio_analysis_matches_quotes_with_normalized_stock_code(monkeypatch):
    async with async_session_maker() as db:
        await db.execute(delete(FollowedStock))
        db.add(FollowedStock(
            stock_code="SH600000",
            stock_name="浦发银行",
            cost_price=10.0,
            volume=100,
        ))
        await db.commit()

        service = StockService(db)

        async def fake_get_realtime_quotes(codes):
            # 组合收益分析会先对持仓股票做归一化，避免 quote_map key 不一致导致现价=0
            assert codes == ["sh600000"]
            return [
                StockQuote(
                    stock_code="sh600000",
                    stock_name="浦发银行",
                    current_price=11.0,
                    change_percent=1.0,
                    change_amount=0.1,
                    open_price=10.8,
                    high_price=11.2,
                    low_price=10.7,
                    prev_close=10.9,
                    volume=123456,
                    amount=987654.0,
                    update_time="",
                )
            ]

        monkeypatch.setattr(service, "get_realtime_quotes", fake_get_realtime_quotes)

        data = await service.get_portfolio_analysis()
        assert data["position_count"] == 1
        assert data["positions"][0]["stock_code"] == "sh600000"
        assert data["positions"][0]["current_price"] == 11.0


@pytest.mark.asyncio
async def test_portfolio_analysis_empty_has_stable_shape():
    async with async_session_maker() as db:
        await db.execute(delete(FollowedStock))
        await db.commit()

        service = StockService(db)
        data = await service.get_portfolio_analysis()

        assert data["position_count"] == 0
        assert data["positions"] == []
        assert data["total_cost"] == 0


@pytest.mark.asyncio
async def test_portfolio_analysis_missing_quote_does_not_assume_zero_price(monkeypatch):
    async with async_session_maker() as db:
        await db.execute(delete(FollowedStock))
        db.add(FollowedStock(
            stock_code="SH600000",
            stock_name="浦发银行",
            cost_price=10.0,
            volume=100,
        ))
        await db.commit()

        service = StockService(db)

        async def fake_get_realtime_quotes(codes):
            assert codes == ["sh600000"]
            return []

        monkeypatch.setattr(service, "get_realtime_quotes", fake_get_realtime_quotes)

        data = await service.get_portfolio_analysis()
        assert data["position_count"] == 1
        assert data["missing_quote_count"] == 1

        pos = data["positions"][0]
        assert pos["stock_code"] == "sh600000"
        assert pos["current_price"] is None
        assert pos["market_value"] is None
        assert pos["profit"] is None
        assert pos["profit_percent"] is None

        # 成本可计算，但总市值/总盈亏在行情缺失时应保持未知（避免误导为 0）
        assert data["total_cost"] == 1000.0
        assert data["total_market_value"] is None
        assert data["total_profit"] is None
        assert data["total_profit_percent"] is None
