import pytest

from app.datasources.eastmoney import EastMoneyClient


class _DummyResp:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class _DummyHttp:
    def __init__(self, payload):
        self._payload = payload
        self.calls = []

    async def get(self, url, params=None):
        self.calls.append((url, params or {}))
        return _DummyResp(self._payload)

    async def aclose(self):
        return None


@pytest.mark.asyncio
async def test_eastmoney_long_tiger_uses_new_fields_and_sort_column():
    payload = {
        "result": {
            "data": [
                {
                    "TRADE_DATE": "2026-02-02 00:00:00",
                    "SECUCODE": "002471.SZ",
                    "SECURITY_CODE": "002471",
                    "SECURITY_NAME_ABBR": "中超控股",
                    "CLOSE_PRICE": 8.61,
                    "CHANGE_RATE": 9.9617,
                    "BILLBOARD_NET_AMT": 511977037.17,
                    "BILLBOARD_BUY_AMT": 700069311.35,
                    "BILLBOARD_SELL_AMT": 188092274.18,
                    "EXPLANATION": "测试原因",
                }
            ]
        }
    }

    em = EastMoneyClient()
    em.client = _DummyHttp(payload)

    resp = await em.get_long_tiger("2026-02-02")
    assert resp.trade_date == "2026-02-02"
    assert len(resp.items) == 1
    item = resp.items[0]
    assert item.stock_code == "002471"
    assert item.net_buy_amount == pytest.approx(511977037.17 / 10000, rel=1e-6)
    assert item.buy_amount == pytest.approx(700069311.35 / 10000, rel=1e-6)
    assert item.sell_amount == pytest.approx(188092274.18 / 10000, rel=1e-6)

    # 确保使用新排序字段，避免东财接口返回 9501
    _, params = em.client.calls[0]
    assert params.get("sortColumns") == "BILLBOARD_NET_AMT"

