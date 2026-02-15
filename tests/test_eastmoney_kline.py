import pytest

from app.datasources.eastmoney import EastMoneyClient


@pytest.mark.asyncio
async def test_eastmoney_get_kline_parses_payload(monkeypatch):
    client = EastMoneyClient()

    payload = {
        "data": {
            "name": "浦发银行",
            "klines": [
                "2026-01-26,10.49,10.35,10.53,10.34,1490771,155000000,0,1.23,0.12,0.45"
            ],
        }
    }

    class DummyResponse:
        def json(self):
            return payload

    async def fake_get(url, params=None):
        return DummyResponse()

    monkeypatch.setattr(client.client, "get", fake_get)

    resp = await client.get_kline("sh600000", period="day", count=1)
    assert resp.stock_code == "sh600000"
    assert resp.stock_name == "浦发银行"
    assert resp.period == "day"
    assert len(resp.data) == 1
    assert resp.data[0].date == "2026-01-26"
    assert resp.data[0].open == 10.49
    assert resp.data[0].close == 10.35
    assert resp.data[0].high == 10.53
    assert resp.data[0].low == 10.34
    assert resp.data[0].volume == 1490771
    assert resp.data[0].amount == 155000000.0
    assert resp.data[0].change_percent == 1.23

    await client.close()


@pytest.mark.asyncio
async def test_eastmoney_get_kline_supports_adjust_and_intraday_period(monkeypatch):
    client = EastMoneyClient()

    captured = {}
    payload = {
        "data": {
            "name": "浦发银行",
            "klines": [
                "2026-01-26 09:35,10.49,10.35,10.53,10.34,1490771,155000000,0,1.23,0.12,0.45"
            ],
        }
    }

    class DummyResponse:
        def json(self):
            return payload

    async def fake_get(url, params=None):
        captured["url"] = url
        captured["params"] = params or {}
        return DummyResponse()

    monkeypatch.setattr(client.client, "get", fake_get)

    resp = await client.get_kline("sh600000", period="5min", count=1, adjust="hfq")
    assert resp.period == "5min"
    assert captured["params"]["klt"] == 5
    assert captured["params"]["fqt"] == 2

    await client.close()
