import pytest

from app.datasources.sina import SinaClient


@pytest.mark.asyncio
async def test_sina_realtime_quotes_normalizes_us_stock_code(monkeypatch):
    client = SinaClient()

    class FakeResponse:
        def __init__(self, text: str):
            self.text = text
            self.encoding = None

    async def fake_get(url: str):
        # var 名称刻意使用小写 ticker，模拟线上常见返回（避免 join 时出现大小写不一致）
        return FakeResponse(
            'var hq_str_gb_aapl="Apple,10,0.5,5%,9.5,10.2,9.4,12,8,1000";\n'
        )

    monkeypatch.setattr(client.client, "get", fake_get)

    quotes = await client.get_realtime_quotes(["usAAPL"])
    assert len(quotes) == 1
    assert quotes[0].stock_code == "usAAPL"

    await client.close()
