import pytest
import httpx
from sqlalchemy import delete, select

from app.database import async_session_maker
from app.models.settings import SearchEngineConfig
from app.services.news_search_service import NewsSearchService, SearchEngine


@pytest.mark.asyncio
async def test_news_search_service_add_remove_config_without_initialize():
    async with async_session_maker() as db:
        service = NewsSearchService(db)
        try:
            config_id = await service.add_engine_config(
                engine=SearchEngine.BOCHA,
                api_key="test-key",
                enabled=True,
                weight=1,
                daily_limit=None,
            )
            assert isinstance(config_id, int)

            ok = await service.remove_engine_config(config_id)
            assert ok is True
        finally:
            await service.close()


@pytest.mark.asyncio
async def test_news_search_service_retries_next_key_on_http_error():
    async with async_session_maker() as db:
        # 清理旧数据
        await db.execute(delete(SearchEngineConfig))
        await db.commit()

        bad = SearchEngineConfig(engine="bocha", api_key="bad", enabled=True, weight=1, daily_limit=None, used_today=0)
        good = SearchEngineConfig(engine="bocha", api_key="good", enabled=True, weight=1, daily_limit=None, used_today=0)
        db.add_all([bad, good])
        await db.commit()
        await db.refresh(bad)
        await db.refresh(good)

        def handler(request: httpx.Request) -> httpx.Response:
            auth = request.headers.get("Authorization", "")
            if auth == "Bearer bad":
                return httpx.Response(401, json={"message": "unauthorized"}, request=request)

            return httpx.Response(
                200,
                json={
                    "data": {
                        "webPages": {
                            "value": [
                                {
                                    "name": "浦发银行 最新消息",
                                    "url": "https://example.com/news/1",
                                    "snippet": "测试摘要",
                                    "datePublished": "2026-02-02T00:00:00Z",
                                }
                            ]
                        }
                    }
                },
                request=request,
            )

        transport = httpx.MockTransport(handler)

        service = NewsSearchService(db)
        # 替换 client 为 MockTransport（先关闭默认 client，避免资源泄漏）
        await service.close()
        service.client = httpx.AsyncClient(transport=transport, timeout=5.0)

        try:
            results = await service.search("600000 最新消息", engine=SearchEngine.BOCHA, limit=1)
            assert results
            assert results[0].source == "bocha"
        finally:
            await service.close()

        # 仅成功的 key 计入 used_today
        refreshed = await db.execute(select(SearchEngineConfig).order_by(SearchEngineConfig.id.asc()))
        rows = refreshed.scalars().all()
        assert len(rows) == 2
        used_by_id = {r.id: r.used_today for r in rows}
        assert used_by_id[bad.id] == 0
        assert used_by_id[good.id] == 1


@pytest.mark.asyncio
async def test_news_search_service_falls_back_to_local_when_no_keys(monkeypatch):
    # 避免开发者环境中配置了搜索 Key 导致该测试走外部引擎，产生不稳定网络依赖
    for k in ["BOCHA_API_KEYS", "BOCHA_API_KEY", "TAVILY_API_KEYS", "TAVILY_API_KEY", "SERPAPI_KEYS", "SERPAPI_KEY"]:
        monkeypatch.delenv(k, raising=False)

    async def fake_local(self, query: str, limit: int):
        from app.schemas.news import NewsItem
        from datetime import datetime

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

    monkeypatch.setattr(NewsSearchService, "_search_local_fallback", fake_local)

    async with async_session_maker() as db:
        await db.execute(delete(SearchEngineConfig))
        await db.commit()

        service = NewsSearchService(db)
        try:
            results = await service.search("600000 最新消息", engine=None, limit=1)
            assert results
            assert results[0].source == "cls"
        finally:
            await service.close()
