import pytest
import httpx
from datetime import datetime

from app.datasources.sina import SinaClient


@pytest.mark.asyncio
async def test_sina_get_news_parses_string_ctime(monkeypatch):
    client = SinaClient()

    async def fake_get(url: str, params=None):
        payload = {
            "result": {
                "data": [
                    {
                        "oid": "n1",
                        "title": "测试标题",
                        "intro": "测试内容",
                        "ctime": "1700000000",
                        "url": "https://example.com/n1",
                        "images": [],
                    }
                ]
            }
        }
        return httpx.Response(200, json=payload)

    monkeypatch.setattr(client.client, "get", fake_get)

    try:
        items = await client.get_news(1)
        assert len(items) == 1
        assert items[0].news_id == "n1"
        assert items[0].source == "sina"
        assert isinstance(items[0].publish_time, datetime)
    finally:
        await client.close()

