import logging

import pytest
from sqlalchemy import delete

from app.database import async_session_maker
from app.models.settings import Settings
from app.models.stock import FollowedStock
from app.schemas.stock import StockQuote
from app.services.stock_service import StockService
from app.tasks import scheduler as scheduler_module


@pytest.mark.asyncio
async def test_refresh_realtime_data_respects_open_alert(monkeypatch, caplog):
    scheduler_module._alert_once_state = {}
    monkeypatch.setattr(scheduler_module, "is_trading_time", lambda now=None: True)

    async def fake_get_realtime_quotes(self, codes):
        assert codes == ["sh600000"]
        return [
            StockQuote(
                stock_code="sh600000",
                stock_name="浦发银行",
                current_price=9.0,
                change_percent=-1.0,
                change_amount=-0.1,
                open_price=9.5,
                high_price=9.6,
                low_price=8.9,
                prev_close=9.1,
                volume=123,
                amount=456.0,
                update_time="",
            )
        ]

    monkeypatch.setattr(StockService, "get_realtime_quotes", fake_get_realtime_quotes)

    async with async_session_maker() as db:
        await db.execute(delete(FollowedStock))
        await db.execute(delete(Settings))
        db.add(Settings(id=1, open_alert=False, alert_frequency="always"))
        db.add(FollowedStock(stock_code="sh600000", stock_name="浦发银行", alert_price_min=10.0))
        await db.commit()

    caplog.set_level(logging.INFO, logger="app.tasks.scheduler")
    await scheduler_module.refresh_realtime_data()
    assert "触发" not in caplog.text


@pytest.mark.asyncio
async def test_refresh_realtime_data_alert_frequency_once(monkeypatch, caplog):
    scheduler_module._alert_once_state = {}
    monkeypatch.setattr(scheduler_module, "is_trading_time", lambda now=None: True)

    async def fake_get_realtime_quotes(self, codes):
        assert codes == ["sh600000"]
        return [
            StockQuote(
                stock_code="sh600000",
                stock_name="浦发银行",
                current_price=9.0,
                change_percent=-1.0,
                change_amount=-0.1,
                open_price=9.5,
                high_price=9.6,
                low_price=8.9,
                prev_close=9.1,
                volume=123,
                amount=456.0,
                update_time="",
            )
        ]

    monkeypatch.setattr(StockService, "get_realtime_quotes", fake_get_realtime_quotes)

    async with async_session_maker() as db:
        await db.execute(delete(FollowedStock))
        await db.execute(delete(Settings))
        db.add(Settings(id=1, open_alert=True, alert_frequency="once"))
        db.add(FollowedStock(stock_code="sh600000", stock_name="浦发银行", alert_price_min=10.0))
        await db.commit()

    caplog.set_level(logging.INFO, logger="app.tasks.scheduler")

    caplog.clear()
    await scheduler_module.refresh_realtime_data()
    assert "触发 1 个价格提醒" in caplog.text

    caplog.clear()
    await scheduler_module.refresh_realtime_data()
    assert "触发" not in caplog.text

