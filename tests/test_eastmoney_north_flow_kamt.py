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
async def test_eastmoney_north_flow_uses_kamt_get_and_converts_units():
    payload = {
        "data": {
            "hk2sh": {"date2": "2026-02-02", "dayNetAmtIn": 12.34, "dayAmtRemain": 100.0},
            "hk2sz": {"date2": "2026-02-02", "dayNetAmtIn": -1.0, "dayAmtRemain": 200.0},
        }
    }

    em = EastMoneyClient()
    em.client = _DummyHttp(payload)

    # days=1 仅验证 push2 current（避免触发数据中心 history 拉取）
    resp = await em.get_north_flow(days=1)
    assert resp["history"] == []
    current = resp["current"]
    assert current["date"] == "2026-02-02"
    assert current["sh_inflow"] == pytest.approx(12.34 * 10000.0)
    assert current["sz_inflow"] == pytest.approx(-1.0 * 10000.0)
    assert current["total_inflow"] == pytest.approx((12.34 - 1.0) * 10000.0)
    assert current["sh_balance"] == pytest.approx(100.0 * 10000.0)
    assert current["sz_balance"] == pytest.approx(200.0 * 10000.0)

    url, _ = em.client.calls[0]
    assert url.endswith("/api/qt/kamt/get")
