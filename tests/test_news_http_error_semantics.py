import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_news_telegraph_returns_empty_payload_on_exception(monkeypatch):
    import app.services.news_service as news_service_module

    async def boom(self, page: int, page_size: int):
        raise Exception("boom")

    monkeypatch.setattr(news_service_module.NewsService, "get_telegraph", boom)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/news/telegraph")
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["code"] == 0
        assert payload["data"]["source"] == "fallback"
        assert payload["data"]["items"] == []


@pytest.mark.asyncio
async def test_news_global_indexes_returns_http_500_on_exception(monkeypatch):
    import app.services.news_service as news_service_module

    async def boom(self):
        raise Exception("boom")

    monkeypatch.setattr(news_service_module.NewsService, "get_global_indexes", boom)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/news/global-indexes")
        assert resp.status_code == 500
        assert "获取全球指数失败" in resp.json()["detail"]
