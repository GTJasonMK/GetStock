import types

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
        params = params or {}
        self.calls.append((url, params))

        # 模拟 push2 被阻断：stock/get 空响应或断连
        if url.endswith("/api/qt/stock/get"):
            raise RuntimeError("push2 blocked")

        if url == "https://datacenter-web.eastmoney.com/api/data/v1/get":
            if params.get("reportName") == "RPT_LICO_FN_CPD":
                return _DummyResp(
                    {
                        "result": {
                            "data": [
                                {
                                    "REPORTDATE": "2025-09-30 00:00:00",
                                    "BASIC_EPS": 2.0,
                                    "BPS": 8.0,
                                    "WEIGHTAVG_ROE": 6.0,
                                    "YSTZ": 1.0,
                                    "SJLTZ": 2.0,
                                    "XSMLL": 30.0,
                                }
                            ]
                        }
                    }
                )

        raise AssertionError(f"Unexpected url: {url} params={params}")

    async def aclose(self):
        return None


@pytest.mark.asyncio
async def test_eastmoney_stock_fundamental_falls_back_to_datacenter_and_sina(monkeypatch):
    # patch SinaClient used in fallback
    from app.datasources import sina as sina_mod

    class _DummySinaClient:
        async def get_realtime_quotes(self, codes):
            return [types.SimpleNamespace(stock_name="浦发银行", current_price=10.0)]

        async def close(self):
            return None

    monkeypatch.setattr(sina_mod, "SinaClient", _DummySinaClient)

    em = EastMoneyClient()
    dummy_http = _DummyHttp()
    em.client = dummy_http

    data = await em.get_stock_fundamental("sh600000")
    assert data["stock_code"] == "sh600000"
    assert data["stock_name"] == "浦发银行"
    assert data["current_price"] == 10.0
    # PB=price/BPS=10/8=1.25
    assert data["pb"] == pytest.approx(1.25)
    # 静态PE=price/EPS=10/2=5
    assert data["pe_static"] == pytest.approx(5.0)
    assert data["roe"] == pytest.approx(6.0)
    assert data["eps"] == pytest.approx(2.0)
    assert data["bvps"] == pytest.approx(8.0)

    # datacenter filter 必须等号（禁止 like）
    dc_call = next(p for (u, p) in dummy_http.calls if u == "https://datacenter-web.eastmoney.com/api/data/v1/get")
    assert "like" not in str(dc_call.get("filter", "")).lower()
    assert 'SECUCODE="600000.SH"' in str(dc_call.get("filter", ""))

