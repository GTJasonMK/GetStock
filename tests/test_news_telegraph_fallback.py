import pytest
from datetime import datetime

from httpx import ASGITransport, AsyncClient

from app.main import app
from app.schemas.news import TelegraphItem, TelegraphResponse


@pytest.mark.asyncio
async def test_news_telegraph_falls_back_when_cls_unavailable(monkeypatch):
    import app.datasources.cls as cls_module
    import app.datasources.sina as sina_module

    async def fake_get_telegraph(self, page: int = 1, page_size: int = 20):
        raise Exception("cls unavailable")

    async def fake_get_live_telegraph(self, page: int = 1, page_size: int = 20):
        return TelegraphResponse(
            items=[
                TelegraphItem(
                    telegraph_id="sina7x24-1",
                    publish_time=datetime.now(),
                    title="降级快讯标题",
                    content="降级快讯内容",
                    source="sina7x24",
                    importance=1,
                    tags=[],
                )
            ],
            total=1,
            has_more=False,
            source="sina7x24",
            notice="财联社接口不可用，已降级为新浪7x24快讯",
        )

    monkeypatch.setattr(cls_module.CLSClient, "get_telegraph", fake_get_telegraph)
    monkeypatch.setattr(sina_module.SinaClient, "get_live_telegraph", fake_get_live_telegraph)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/news/telegraph", params={"page": 1, "page_size": 30})
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["code"] == 0

        data = payload["data"]
        assert data["source"] == "sina7x24"
        assert "降级" in (data.get("notice") or "")
        assert len(data["items"]) == 1
        assert data["items"][0]["source"] == "sina7x24"
        assert data["items"][0]["title"] == "降级快讯标题"
