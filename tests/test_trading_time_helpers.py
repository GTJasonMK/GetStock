from datetime import datetime

from app.utils.helpers import is_trading_time


def test_is_trading_time_morning_session_boundaries():
    # 周五
    assert is_trading_time(datetime(2026, 1, 30, 9, 29)) is False
    assert is_trading_time(datetime(2026, 1, 30, 9, 30)) is True
    assert is_trading_time(datetime(2026, 1, 30, 11, 30)) is True
    assert is_trading_time(datetime(2026, 1, 30, 11, 31)) is False


def test_is_trading_time_lunch_break_and_afternoon_session():
    # 午休
    assert is_trading_time(datetime(2026, 1, 30, 12, 0)) is False
    # 下午开盘
    assert is_trading_time(datetime(2026, 1, 30, 13, 0)) is True
    # 收盘边界
    assert is_trading_time(datetime(2026, 1, 30, 15, 0)) is True
    assert is_trading_time(datetime(2026, 1, 30, 15, 1)) is False


def test_is_trading_time_weekend_is_false():
    # 周六/周日不交易
    assert is_trading_time(datetime(2026, 1, 31, 10, 0)) is False
    assert is_trading_time(datetime(2026, 2, 1, 10, 0)) is False


def test_is_trading_time_holiday_is_false(monkeypatch):
    # 通过 monkeypatch 固定“节假日判断”为 True，避免依赖真实日历数据
    import app.utils.helpers as helpers

    monkeypatch.setattr(helpers, "_is_china_market_holiday", lambda _day: True)
    assert helpers.is_trading_time(datetime(2026, 1, 30, 10, 0)) is False
