import pytest

from app.datasources.eastmoney import EastMoneyClient


class _DummyResp:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class _DummyHttp:
    def __init__(self):
        self.calls = []

    async def get(self, url, params=None):
        self.calls.append((url, params or {}))

        # 模拟 push2 被阻断
        if url.endswith("/api/qt/kamt/get"):
            raise RuntimeError("push2 blocked")

        # 数据中心兜底：返回两天数据，其中最新一天净买额为空，需要回溯
        if (params or {}).get("reportName") == "RPT_MUTUAL_DEAL_HISTORY":
            return _DummyResp({
                "result": {
                    "pages": 1,
                    "data": [
                        # 002/004/006 为净买额组；最新一天为空需要回溯
                        {"MUTUAL_TYPE": "002", "TRADE_DATE": "2026-02-02 00:00:00", "NET_DEAL_AMT": None},
                        {"MUTUAL_TYPE": "004", "TRADE_DATE": "2026-02-02 00:00:00", "NET_DEAL_AMT": None},
                        {"MUTUAL_TYPE": "006", "TRADE_DATE": "2026-02-02 00:00:00", "NET_DEAL_AMT": None},
                        {"MUTUAL_TYPE": "002", "TRADE_DATE": "2026-01-31 00:00:00", "NET_DEAL_AMT": 100.0},
                        {"MUTUAL_TYPE": "004", "TRADE_DATE": "2026-01-31 00:00:00", "NET_DEAL_AMT": 200.0},
                        {"MUTUAL_TYPE": "006", "TRADE_DATE": "2026-01-31 00:00:00", "NET_DEAL_AMT": 300.0},
                    ]
                }
            })

        raise AssertionError(f"Unexpected url: {url} params={params}")

    async def aclose(self):
        return None


@pytest.mark.asyncio
async def test_eastmoney_north_flow_falls_back_to_datacenter_when_push2_blocked():
    em = EastMoneyClient()
    em.client = _DummyHttp()

    resp = await em.get_north_flow(days=5)
    assert resp["current"]["date"] == "2026-01-31"
    # 数据中心 NET_DEAL_AMT 口径为百万元，这里应转换为元
    assert resp["current"]["sh_inflow"] == pytest.approx(100.0 * 1_000_000.0)
    assert resp["current"]["sz_inflow"] == pytest.approx(200.0 * 1_000_000.0)
    assert resp["current"]["total_inflow"] == pytest.approx(300.0 * 1_000_000.0)
    assert resp["history"][0]["date"] == "2026-01-31"
