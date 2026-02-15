import pytest

from app.datasources.manager import DataSourceManager
from app.schemas.stock import KLineResponse, KLineData


@pytest.mark.asyncio
async def test_get_kline_falls_back_to_eastmoney_when_tencent_returns_empty(monkeypatch):
    from app.datasources import tencent as tencent_module
    from app.datasources import eastmoney as eastmoney_module

    class FakeTencentClient:
        async def get_kline(
            self,
            stock_code: str,
            period: str = "day",
            count: int = 100,
            adjust: str = "qfq",
        ):
            return KLineResponse(
                stock_code=stock_code,
                stock_name="tencent",
                period=period,
                data=[],
            )

        async def close(self):
            return None

    class FakeEastMoneyClient:
        async def get_kline(
            self,
            stock_code: str,
            period: str = "day",
            count: int = 100,
            adjust: str = "qfq",
        ):
            return KLineResponse(
                stock_code=stock_code,
                stock_name="eastmoney",
                period=period,
                data=[
                    KLineData(
                        date="2026-01-26",
                        open=10.0,
                        close=10.1,
                        high=10.2,
                        low=9.9,
                        volume=123,
                        amount=456.0,
                        change_percent=1.0,
                    )
                ],
            )

        async def close(self):
            return None

    monkeypatch.setattr(tencent_module, "TencentClient", FakeTencentClient)
    monkeypatch.setattr(eastmoney_module, "EastMoneyClient", FakeEastMoneyClient)

    manager = DataSourceManager()
    await manager.initialize()

    resp = await manager.get_kline("sh600000", period="day", count=1)
    assert resp.stock_name == "eastmoney"
    assert len(resp.data) == 1


@pytest.mark.asyncio
async def test_get_kline_uses_akshare_for_us(monkeypatch):
    from app.datasources import akshare as akshare_module
    from app.datasources import tencent as tencent_module

    called = []

    class FakeAkShareClient:
        async def get_kline(
            self,
            stock_code: str,
            period: str = "day",
            count: int = 100,
            adjust: str = "qfq",
        ):
            called.append("akshare")
            return KLineResponse(
                stock_code=stock_code,
                stock_name="akshare",
                period=period,
                data=[
                    KLineData(
                        date="2026-01-26",
                        open=10.0,
                        close=10.1,
                        high=10.2,
                        low=9.9,
                        volume=123,
                        amount=456.0,
                        change_percent=1.0,
                    )
                ],
            )

        async def close(self):
            return None

    class FakeTencentClient:
        async def get_kline(
            self,
            stock_code: str,
            period: str = "day",
            count: int = 100,
            adjust: str = "qfq",
        ):
            called.append("tencent")
            return KLineResponse(
                stock_code=stock_code,
                stock_name="tencent",
                period=period,
                data=[
                    KLineData(
                        date="2026-01-26",
                        open=1.0,
                        close=1.0,
                        high=1.0,
                        low=1.0,
                        volume=1,
                        amount=1.0,
                        change_percent=0.0,
                    )
                ],
            )

        async def close(self):
            return None

    monkeypatch.setattr(akshare_module, "AkShareClient", FakeAkShareClient)
    monkeypatch.setattr(tencent_module, "TencentClient", FakeTencentClient)

    manager = DataSourceManager()
    await manager.initialize()

    resp = await manager.get_kline("usAAPL", period="day", count=1)
    assert resp.stock_name == "akshare"
    assert len(resp.data) == 1
    assert called == ["akshare"]


@pytest.mark.asyncio
async def test_get_kline_falls_back_to_akshare_for_hk_when_tencent_returns_empty(monkeypatch):
    from app.datasources import akshare as akshare_module
    from app.datasources import tencent as tencent_module

    called = []

    class FakeTencentClient:
        async def get_kline(
            self,
            stock_code: str,
            period: str = "day",
            count: int = 100,
            adjust: str = "qfq",
        ):
            called.append("tencent")
            return KLineResponse(
                stock_code=stock_code,
                stock_name="tencent",
                period=period,
                data=[],
            )

        async def close(self):
            return None

    class FakeAkShareClient:
        async def get_kline(
            self,
            stock_code: str,
            period: str = "day",
            count: int = 100,
            adjust: str = "qfq",
        ):
            called.append("akshare")
            return KLineResponse(
                stock_code=stock_code,
                stock_name="akshare",
                period=period,
                data=[
                    KLineData(
                        date="2026-01-26",
                        open=10.0,
                        close=10.1,
                        high=10.2,
                        low=9.9,
                        volume=123,
                        amount=456.0,
                        change_percent=1.0,
                    )
                ],
            )

        async def close(self):
            return None

    monkeypatch.setattr(tencent_module, "TencentClient", FakeTencentClient)
    monkeypatch.setattr(akshare_module, "AkShareClient", FakeAkShareClient)

    manager = DataSourceManager()
    await manager.initialize()

    resp = await manager.get_kline("hk00700", period="day", count=1)
    assert resp.stock_name == "akshare"
    assert len(resp.data) == 1
    assert called == ["tencent", "akshare"]
