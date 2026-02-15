import pytest


@pytest.mark.asyncio
async def test_eastmoney_kline_raises_runtime_error_when_payload_is_string(monkeypatch):
    from app.datasources.eastmoney import EastMoneyClient

    class FakeResponse:
        def __init__(self):
            self.text = '"oops"'

        def json(self):
            # 返回 JSON 字符串（合法 JSON 但不是 object）
            return "oops"

    class FakeHTTPClient:
        async def get(self, url: str, params=None):
            return FakeResponse()

    client = EastMoneyClient()
    monkeypatch.setattr(client, "client", FakeHTTPClient())

    with pytest.raises(RuntimeError) as exc:
        await client.get_kline("sh600000", period="day", count=1, adjust="qfq")

    assert "期望 object" in str(exc.value)

