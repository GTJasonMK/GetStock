# News API
"""
资讯API路由
"""

from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from datetime import datetime

from app.database import get_db
from app.schemas.news import TelegraphResponse, NewsResponse, GlobalIndexResponse
from app.schemas.common import Response

router = APIRouter()


@router.get("/latest", response_model=Response[NewsResponse])
async def get_latest_news(
    source: Optional[str] = Query(None, description="来源: sina/cls/eastmoney"),
    limit: int = Query(20, le=100),
    db: AsyncSession = Depends(get_db)
):
    """获取最新资讯"""
    from app.services.news_service import NewsService

    service = NewsService(db)
    news = await service.get_latest_news(source, limit)

    return Response(data=news)


@router.get("/telegraph", response_model=Response[TelegraphResponse])
async def get_telegraph(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, le=100),
    db: AsyncSession = Depends(get_db)
):
    """获取财联社电报"""
    from app.services.news_service import NewsService

    service = NewsService(db)
    try:
        telegraph = await service.get_telegraph(page, page_size)
        return Response(data=telegraph)
    except Exception as e:
        # 该接口面向前端“快讯”面板；为保证 UI 稳定，异常时返回空数据而不是直接 500
        return Response(
            message=f"获取快讯失败，已返回空数据: {e}",
            data=TelegraphResponse(items=[], total=0, has_more=False, source="fallback", notice=str(e)),
        )


@router.get("/global-indexes", response_model=Response[GlobalIndexResponse])
async def get_global_indexes(db: AsyncSession = Depends(get_db)):
    """获取全球指数"""
    from app.services.news_service import NewsService

    service = NewsService(db)
    try:
        indexes = await service.get_global_indexes()
        return Response(data=indexes)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取全球指数失败: {e}")


# ============ TradingView News ============

class TradingViewNewsItem(BaseModel):
    """TradingView新闻条目"""
    id: str
    title: str
    source: str
    published_at: Optional[datetime] = None
    url: Optional[str] = None


class TradingViewNewsResponse(BaseModel):
    """TradingView新闻响应"""
    items: List[TradingViewNewsItem]
    total: int


@router.get("/tradingview", response_model=Response[TradingViewNewsResponse])
async def get_tradingview_news(
    limit: int = Query(20, le=100),
    db: AsyncSession = Depends(get_db)
):
    """获取TradingView资讯"""
    from app.services.news_service import NewsService

    service = NewsService(db)
    news = await service.get_tradingview_news(limit)

    return Response(data=news)


@router.get("/tradingview/{news_id}")
async def get_tradingview_news_detail(
    news_id: str,
    db: AsyncSession = Depends(get_db)
):
    """获取TradingView新闻详情"""
    from app.services.news_service import NewsService

    service = NewsService(db)
    detail = await service.get_tradingview_news_detail(news_id)

    return Response(data=detail)


# ============ 热门话题/事件 ============

class HotTopicItem(BaseModel):
    """热门话题条目"""
    id: str
    title: str
    hot_score: int
    change_count: int
    create_time: Optional[datetime] = None


class HotTopicsResponse(BaseModel):
    """热门话题响应"""
    items: List[HotTopicItem]


@router.get("/hot-topics", response_model=Response[HotTopicsResponse])
async def get_hot_topics(
    size: int = Query(20, le=50),
    db: AsyncSession = Depends(get_db)
):
    """获取热门话题"""
    from app.services.news_service import NewsService

    service = NewsService(db)
    topics = await service.get_hot_topics(size)

    return Response(data=topics)


class HotEventItem(BaseModel):
    """热门事件条目"""
    id: str
    title: str
    description: str
    event_type: str
    create_time: Optional[datetime] = None


class HotEventsResponse(BaseModel):
    """热门事件响应"""
    items: List[HotEventItem]


@router.get("/hot-events", response_model=Response[HotEventsResponse])
async def get_hot_events(
    size: int = Query(20, le=50),
    db: AsyncSession = Depends(get_db)
):
    """获取热门事件"""
    from app.services.news_service import NewsService

    service = NewsService(db)
    events = await service.get_hot_events(size)

    return Response(data=events)


# ============ 投资日历 ============

class CalendarItem(BaseModel):
    """日历条目"""
    date: str
    event: str
    importance: str
    country: Optional[str] = None
    actual: Optional[str] = None
    forecast: Optional[str] = None
    previous: Optional[str] = None


class InvestCalendarResponse(BaseModel):
    """投资日历响应"""
    items: List[CalendarItem]


@router.get("/calendar", response_model=Response[InvestCalendarResponse])
async def get_invest_calendar(
    year_month: Optional[str] = Query(None, description="年月 YYYY-MM"),
    db: AsyncSession = Depends(get_db)
):
    """获取投资日历"""
    from app.services.news_service import NewsService
    from datetime import datetime

    if not year_month:
        year_month = datetime.now().strftime("%Y-%m")

    service = NewsService(db)
    calendar = await service.get_invest_calendar(year_month)

    return Response(data=calendar)


# ============ 股票公告 ============

class StockNoticeItem(BaseModel):
    """股票公告条目"""
    id: str
    title: str
    stock_code: str
    stock_name: str
    notice_type: str
    publish_date: datetime
    url: Optional[str] = None


class StockNoticesResponse(BaseModel):
    """股票公告响应"""
    items: List[StockNoticeItem]
    total: int


@router.get("/notices/{stock_code}", response_model=Response[StockNoticesResponse])
async def get_stock_notices(
    stock_code: str,
    limit: int = Query(20, le=100),
    db: AsyncSession = Depends(get_db)
):
    """获取股票公告"""
    from app.services.news_service import NewsService

    service = NewsService(db)
    notices = await service.get_stock_notices(stock_code, limit)

    return Response(data=notices)


# ============ 新闻搜索 (多引擎) ============

class NewsSearchItem(BaseModel):
    """新闻搜索结果条目"""
    news_id: str
    title: str
    content: str
    source: str
    publish_time: Optional[datetime] = None
    url: str
    image_url: Optional[str] = None


class NewsSearchResponse(BaseModel):
    """新闻搜索响应"""
    items: List[NewsSearchItem]
    engine: Optional[str] = None


@router.get("/search", response_model=Response[NewsSearchResponse])
async def search_news(
    keyword: str = Query(..., min_length=1, description="搜索关键词"),
    engine: Optional[str] = Query(None, description="搜索引擎: tavily/serpapi/bocha"),
    limit: int = Query(10, le=50),
    db: AsyncSession = Depends(get_db)
):
    """
    搜索新闻 (多引擎支持)

    - **keyword**: 搜索关键词
    - **engine**: 指定搜索引擎，不指定则自动选择
    - **limit**: 返回结果数量
    """
    from app.services.news_search_service import NewsSearchService, SearchEngine

    service = NewsSearchService(db)
    try:
        # 解析引擎类型
        search_engine = None
        if engine:
            try:
                search_engine = SearchEngine(engine.lower())
            except ValueError:
                pass

        results = await service.search(keyword, search_engine, limit)

        items = [
            NewsSearchItem(
                news_id=r.news_id,
                title=r.title,
                content=r.content,
                source=r.source,
                publish_time=r.publish_time,
                url=r.url,
                image_url=r.image_url,
            )
            for r in results
        ]

        resolved_engine: Optional[str] = None
        if results:
            sources = {r.source for r in results if r.source}
            web_sources = {"bocha", "tavily", "serpapi"}
            if sources.issubset(web_sources):
                resolved_engine = sources.pop() if len(sources) == 1 else "mixed"
            elif sources.isdisjoint(web_sources):
                resolved_engine = "local"
            else:
                resolved_engine = "mixed"
        elif search_engine:
            resolved_engine = search_engine.value

        return Response(data=NewsSearchResponse(
            items=items,
            engine=resolved_engine,
        ))
    finally:
        await service.close()


class SearchEngineStatusItem(BaseModel):
    """搜索引擎状态"""
    engine: str
    total_keys: int
    enabled_keys: int
    total_daily_limit: Optional[int] = None
    total_used_today: int


class SearchEngineStatusResponse(BaseModel):
    """搜索引擎状态列表"""
    engines: List[SearchEngineStatusItem]


@router.get("/search/engines", response_model=Response[SearchEngineStatusResponse])
async def get_search_engines(
    db: AsyncSession = Depends(get_db)
):
    """获取搜索引擎状态"""
    from app.services.news_search_service import NewsSearchService

    service = NewsSearchService(db)
    try:
        await service.initialize()
        statuses = service.get_engine_status()

        return Response(data=SearchEngineStatusResponse(
            engines=[
                SearchEngineStatusItem(
                    engine=s["engine"],
                    total_keys=s["total_keys"],
                    enabled_keys=s["enabled_keys"],
                    total_daily_limit=s["total_daily_limit"],
                    total_used_today=s["total_used_today"],
                )
                for s in statuses
            ]
        ))
    finally:
        await service.close()


class AddSearchEngineRequest(BaseModel):
    """添加搜索引擎配置请求"""
    engine: str
    api_key: str
    enabled: bool = True
    weight: int = 1
    daily_limit: Optional[int] = None


@router.post("/search/engines")
async def add_search_engine(
    request: AddSearchEngineRequest,
    db: AsyncSession = Depends(get_db)
):
    """添加搜索引擎配置"""
    from app.services.news_search_service import NewsSearchService, SearchEngine

    try:
        search_engine = SearchEngine(request.engine.lower())
    except ValueError:
        return Response(code=400, message=f"不支持的搜索引擎: {request.engine}")

    service = NewsSearchService(db)
    try:
        config_id = await service.add_engine_config(
            engine=search_engine,
            api_key=request.api_key,
            enabled=request.enabled,
            weight=request.weight,
            daily_limit=request.daily_limit,
        )

        return Response(data={"id": config_id, "message": "配置添加成功"})
    finally:
        await service.close()


@router.delete("/search/engines/{config_id}")
async def delete_search_engine(
    config_id: int,
    db: AsyncSession = Depends(get_db)
):
    """删除搜索引擎配置"""
    from app.services.news_search_service import NewsSearchService

    service = NewsSearchService(db)
    try:
        success = await service.remove_engine_config(config_id)

        if not success:
            return Response(code=404, message="配置不存在")

        return Response(data={"message": "配置删除成功"})
    finally:
        await service.close()

