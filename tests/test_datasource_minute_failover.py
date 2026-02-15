import pytest

from app.datasources.manager import DataSourceManager
from app.schemas.stock import MinuteDataResponse, MinuteData


@pytest.mark.asyncio
async def test_get_minute_data_uses_eastmoney_first_by_default(monkeypatch):
    from app.datasources import eastmoney as eastmoney_module
    from app.datasources import sina as sina_module

    called: list[str] = []

    class FakeEastMoneyClient:
        async def get_minute_data(self, stock_code: str):
            called.append("eastmoney")
            return MinuteDataResponse(
                stock_code=stock_code,
                stock_name="eastmoney",
                data=[
                    MinuteData(time="09:30", price=10.0, volume=1, avg_price=10.0),
                ],
            )

        async def close(self):
            return None

    class FakeSinaClient:
        async def get_minute_data(self, stock_code: str):
            called.append("sina")
            return MinuteDataResponse(
                stock_code=stock_code,
                stock_name="sina",
                data=[
                    MinuteData(time="09:30", price=10.0, volume=1, avg_price=10.0),
                ],
            )

        async def close(self):
            return None

    monkeypatch.setattr(eastmoney_module, "EastMoneyClient", FakeEastMoneyClient)
    monkeypatch.setattr(sina_module, "SinaClient", FakeSinaClient)

    manager = DataSourceManager()
    await manager.initialize()

    resp = await manager.get_minute_data("sh600000")
    assert resp.stock_name == "eastmoney"
    assert called == ["eastmoney"]


@pytest.mark.asyncio
async def test_get_minute_data_falls_back_to_sina_when_eastmoney_errors(monkeypatch):
    from app.datasources import eastmoney as eastmoney_module
    from app.datasources import sina as sina_module

    called: list[str] = []

    class FakeEastMoneyClient:
        async def get_minute_data(self, stock_code: str):
            called.append("eastmoney")
            raise RuntimeError("eastmoney down")

        async def close(self):
            return None

    class FakeSinaClient:
        async def get_minute_data(self, stock_code: str):
            called.append("sina")
            return MinuteDataResponse(
                stock_code=stock_code,
                stock_name="sina",
                data=[
                    MinuteData(time="09:30", price=10.0, volume=1, avg_price=10.0),
                ],
            )

        async def close(self):
            return None

    monkeypatch.setattr(eastmoney_module, "EastMoneyClient", FakeEastMoneyClient)
    monkeypatch.setattr(sina_module, "SinaClient", FakeSinaClient)

    manager = DataSourceManager()
    await manager.initialize()

    resp = await manager.get_minute_data("sh600000")
    assert resp.stock_name == "sina"
    assert called == ["eastmoney", "sina"]


@pytest.mark.asyncio
async def test_get_minute_data_falls_back_when_first_source_returns_empty(monkeypatch):
    from app.datasources import eastmoney as eastmoney_module
    from app.datasources import sina as sina_module

    called: list[str] = []

    class FakeEastMoneyClient:
        async def get_minute_data(self, stock_code: str):
            called.append("eastmoney")
            return MinuteDataResponse(stock_code=stock_code, stock_name="eastmoney", data=[])

        async def close(self):
            return None

    class FakeSinaClient:
        async def get_minute_data(self, stock_code: str):
            called.append("sina")
            return MinuteDataResponse(
                stock_code=stock_code,
                stock_name="sina",
                data=[
                    MinuteData(time="09:30", price=10.0, volume=1, avg_price=10.0),
                ],
            )

        async def close(self):
            return None

    monkeypatch.setattr(eastmoney_module, "EastMoneyClient", FakeEastMoneyClient)
    monkeypatch.setattr(sina_module, "SinaClient", FakeSinaClient)

    manager = DataSourceManager()
    await manager.initialize()

    resp = await manager.get_minute_data("sh600000")
    assert resp.stock_name == "sina"
    assert called == ["eastmoney", "sina"]

