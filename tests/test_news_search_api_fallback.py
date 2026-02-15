import pytest
from datetime import datetime

from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.database import async_session_maker
from app.main import app
from app.models.settings import SearchEngineConfig
from app.schemas.news import NewsItem


@pytest.mark.asyncio
async def test_news_search_api_returns_local_engine_when_fallback(monkeypatch):
    import app.services.news_search_service as news_search_service_module

    # 避免开发者环境中配置了搜索 Key 导致该测试走外部引擎，产生不稳定网络依赖
    for k in ["BOCHA_API_KEYS", "BOCHA_API_KEY", "TAVILY_API_KEYS", "TAVILY_API_KEY", "SERPAPI_KEYS", "SERPAPI_KEY"]:
        monkeypatch.delenv(k, raising=False)

    async def fake_local(self, query: str, limit: int):
        return [
            NewsItem(
                news_id="local-1",
                title="本地资讯命中",
                content="测试内容",
                source="cls",
                publish_time=datetime.now(),
                url="https://example.com/local/1",
                image_url="",
            )
        ]

    monkeypatch.setattr(news_search_service_module.NewsSearchService, "_search_local_fallback", fake_local)

    async with async_session_maker() as db:
        await db.execute(delete(SearchEngineConfig))
        await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/news/search", params={"keyword": "浦发银行", "limit": 1})
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["code"] == 0
        assert payload["data"]["engine"] == "local"
        assert len(payload["data"]["items"]) == 1
