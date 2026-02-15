import pytest


@pytest.mark.asyncio
async def test_tencent_kline_raises_runtime_error_when_data_field_is_string(monkeypatch):
    from app.datasources.tencent import TencentClient

    class FakeResponse:
        def __init__(self, text: str):
            self.text = text

    class FakeHTTPClient:
        async def get(self, url: str):
            # 模拟腾讯接口返回 {"data": "..."} 这类非预期结构，历史代码会触发 `'str' object has no attribute 'get'`
            return FakeResponse('kline_data={"data":"oops"}')

    client = TencentClient()
    monkeypatch.setattr(client, "client", FakeHTTPClient())

    with pytest.raises(RuntimeError) as exc:
        await client.get_kline("sh600000", period="day", count=1)

    assert "data 字段不是对象" in str(exc.value)


@pytest.mark.asyncio
async def test_tencent_kline_does_not_crash_when_volume_field_is_dict(monkeypatch):
    """
    回归：线上偶发 `float() argument must be a string or a real number, not 'dict'`。
    这通常意味着 K 线数组里的某个字段被包了一层 dict，旧实现会直接 float(dict) 崩溃。
    """
    from app.datasources.tencent import TencentClient

    class FakeResponse:
        def __init__(self, text: str):
            self.text = text

    class FakeHTTPClient:
        async def get(self, url: str):
            _ = url
            return FakeResponse(
                'kline_data={"code":0,"msg":"","data":{"sh600000":{"qfqday":[["2026-02-03","10.0","10.1","10.2","9.9",{"v":"100"}]]}}}'
            )

    client = TencentClient()
    monkeypatch.setattr(client, "client", FakeHTTPClient())

    resp = await client.get_kline("sh600000", period="day", count=1)
    assert resp.data and resp.data[0].volume == 100
