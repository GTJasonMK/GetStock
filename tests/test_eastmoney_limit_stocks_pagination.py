import pytest


class _DummyResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


@pytest.mark.asyncio
async def test_eastmoney_limit_up_stocks_paginates_until_threshold():
    from app.datasources.eastmoney import EastMoneyClient

    calls = []

    def _item(cp: float, code: str):
        return {
            "f3": cp,
            "f12": code,
            "f14": "测试股",
            "f2": 10.0,
            "f5": 0,
            "f6": 0.0,
        }

    class DummyHTTP:
        async def get(self, url, params=None):
            pn = int((params or {}).get("pn", 1))
            calls.append(pn)
            if pn == 1:
                # 100 条全部 >=9.9，触发翻页
                diff = [_item(10.0, f"{i:06d}") for i in range(100)]
                return _DummyResponse({"data": {"diff": diff}})
            if pn == 2:
                # 前 5 条仍满足，随后出现 9.8，应该停止继续翻页
                diff = [_item(10.0, f"p2{i:02d}") for i in range(5)]
                diff.append(_item(9.8, "p2break"))
                diff.extend([_item(5.0, f"p2x{i:02d}") for i in range(10)])
                return _DummyResponse({"data": {"diff": diff}})
            raise AssertionError(f"不应继续请求 pn={pn}")

        async def aclose(self):
            return None

    client = EastMoneyClient()
    original_http = client.client
    client.client = DummyHTTP()  # type: ignore[assignment]
    try:
        stocks = await client.get_limit_up_stocks()
    finally:
        await original_http.aclose()

    # 100（第一页） + 5（第二页有效） = 105
    assert len(stocks) == 105
    assert calls == [1, 2]


@pytest.mark.asyncio
async def test_eastmoney_limit_down_stocks_paginates_until_threshold():
    from app.datasources.eastmoney import EastMoneyClient

    calls = []

    def _item(cp: float, code: str):
        return {
            "f3": cp,
            "f12": code,
            "f14": "测试股",
            "f2": 10.0,
            "f5": 0,
            "f6": 0.0,
        }

    class DummyHTTP:
        async def get(self, url, params=None):
            pn = int((params or {}).get("pn", 1))
            calls.append(pn)
            if pn == 1:
                diff = [_item(-10.0, f"{i:06d}") for i in range(100)]
                return _DummyResponse({"data": {"diff": diff}})
            if pn == 2:
                diff = [_item(-10.0, f"p2{i:02d}") for i in range(3)]
                diff.append(_item(-9.8, "p2break"))
                diff.extend([_item(-1.0, f"p2x{i:02d}") for i in range(10)])
                return _DummyResponse({"data": {"diff": diff}})
            raise AssertionError(f"不应继续请求 pn={pn}")

        async def aclose(self):
            return None

    client = EastMoneyClient()
    original_http = client.client
    client.client = DummyHTTP()  # type: ignore[assignment]
    try:
        stocks = await client.get_limit_down_stocks()
    finally:
        await original_http.aclose()

    assert len(stocks) == 103
    assert calls == [1, 2]

