# News Service
"""
资讯服务
"""

import logging
import hashlib
import re
from datetime import datetime
from typing import Optional, List, Any, Dict

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.news import TelegraphResponse, NewsResponse, GlobalIndexResponse, NewsItem
from app.utils.cache import cached, CacheTTL

logger = logging.getLogger(__name__)


class NewsService:
    """资讯服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def _get_datasource_manager(self):
        """获取数据源管理器（按 DB 配置初始化）。"""
        from app.datasources.manager import get_datasource_manager

        manager = get_datasource_manager()
        await manager.initialize(self.db)
        return manager

    async def get_latest_news(
        self,
        source: Optional[str] = None,
        limit: int = 20
    ) -> NewsResponse:
        """获取最新资讯"""
        manager = await self._get_datasource_manager()
        items: List[NewsItem] = []

        if not source or source == "cls":
            try:
                cls_news = await manager.get_news("cls", limit)
                items.extend(cls_news or [])
            except Exception as e:
                logger.warning(f"从财联社获取资讯失败: {e}")

        if not source or source == "sina":
            try:
                try:
                    sina_news = await manager.get_news("sina", limit)
                    items.extend(sina_news or [])
                except Exception as e:
                    logger.warning(f"从新浪 feed 获取资讯失败: {e}")

                # 新浪 7x24 快讯作为兜底/补充（在部分网络环境更稳定）
                if not items or len(items) < max(5, limit // 3):
                    try:
                        live_news = await manager.get_live_news(limit)
                        items.extend(live_news or [])
                    except Exception as e:
                        logger.warning(f"从新浪7x24获取资讯失败: {e}")
            except Exception as e:
                logger.warning(f"从新浪获取资讯失败: {e}")

        # 兜底：若主流来源全部失败，使用 AkShare 的“财新主要新闻”保证至少返回可读信息
        # 注意：该源不一定覆盖A股实时要闻，但在部分网络环境更稳定，可避免“页面永远空白”。
        if not items:
            try:
                from app.datasources.akshare_bridge import get_news_main_cx_df

                df = await get_news_main_cx_df()
                if df is not None and not getattr(df, "empty", True):
                    for r in (df.to_dict("records") or [])[:limit]:  # type: ignore[call-arg]
                        url = str(r.get("url", "") or "")
                        summary = str(r.get("summary", "") or "")
                        tag = str(r.get("tag", "") or "").strip()

                        # 尽量从 url 中解析日期（示例：.../2026-02-02/...）
                        dt = datetime.now()
                        m = re.search(r"(20\\d{2}-\\d{2}-\\d{2})", url)
                        if m:
                            try:
                                dt = datetime.strptime(m.group(1), "%Y-%m-%d")
                            except Exception:
                                dt = datetime.now()

                        title = summary.strip()
                        if tag:
                            title = f"[{tag}] {title}"
                        if not title:
                            title = url or "财新要闻"

                        news_id = hashlib.md5((url or title).encode("utf-8")).hexdigest()
                        items.append(
                            NewsItem(
                                news_id=news_id,
                                title=title[:200],
                                content=summary[:2000],
                                source="caixin",
                                publish_time=dt,
                                url=url,
                                image_url="",
                            )
                        )
            except Exception as e:
                logger.warning(f"从AkShare/财新获取资讯失败: {e}")

        # 按时间排序
        items.sort(key=lambda x: x.publish_time, reverse=True)

        return NewsResponse(items=items[:limit], total=len(items))

    async def get_telegraph(self, page: int = 1, page_size: int = 20) -> TelegraphResponse:
        """获取财联社电报"""
        manager = await self._get_datasource_manager()
        try:
            telegraph = await manager.get_telegraph("cls", page, page_size)
            # 若数据为空，常见原因是接口变更/被拦截；此时降级到其他来源，避免前端一直空白
            if telegraph and getattr(telegraph, "items", None):
                return telegraph
        except Exception as e:
            logger.warning(f"获取财联社电报失败，将降级: {e}")

        # 降级优先：新浪 7x24 快讯（通常比 CLS 更稳定）
        try:
            telegraph = await manager.get_telegraph("sina", page, page_size)
            if telegraph and getattr(telegraph, "items", None):
                return telegraph
        except Exception as e:
            logger.warning(f"降级源（新浪7x24）获取失败，将继续降级: {e}")

        # 最后降级：使用新浪 feed.mix 资讯模拟“快讯”流（保证接口不 500，且尽量返回可用信息）
        # 由于新浪接口不支持 page 参数，这里通过扩大抓取数量后切片实现粗粒度分页。
        # 上限 200：避免 page 较大时请求过重。
        limit = min(max(page * page_size, page_size), 200)
        try:
            news = await manager.get_news("sina", limit)
        except Exception as e:
            logger.warning(f"降级源（新浪feed）获取失败: {e}")
            return TelegraphResponse(items=[], total=0, has_more=False, source="fallback", notice="快讯数据源暂不可用")

        # 按时间倒序，切片得到当前页
        news.sort(key=lambda x: x.publish_time, reverse=True)
        start = (page - 1) * page_size
        end = start + page_size
        page_news = news[start:end] if start < len(news) else []

        from app.schemas.news import TelegraphItem

        items = [
            TelegraphItem(
                telegraph_id=f"sina-{n.news_id}",
                publish_time=n.publish_time,
                title=n.title,
                content=n.content or "",
                source="sina",
                importance=1,
                tags=[],
            )
            for n in page_news
        ]

        return TelegraphResponse(
            items=items,
            total=len(news),
            has_more=end < len(news),
            source="sina",
            notice="财联社接口不可用，已降级为新浪资讯",
        )

    @cached(ttl_seconds=CacheTTL.GLOBAL_INDEX, prefix="global_indexes")
    async def get_global_indexes(self) -> GlobalIndexResponse:
        """获取全球指数"""
        manager = await self._get_datasource_manager()
        return await manager.get_global_indexes()

    async def search_news(self, keywords: str, limit: int = 20) -> NewsResponse:
        """搜索新闻"""
        manager = await self._get_datasource_manager()
        items: List[NewsItem] = []
        kw_list = (keywords or "").split()

        try:
            # 从财联社获取新闻并过滤
            cls_news = await manager.get_news("cls", 50)
            for item in cls_news or []:
                if any(kw in item.title or kw in (item.content or "") for kw in kw_list):
                    items.append(item)
        except Exception as e:
            logger.warning(f"从财联社获取新闻失败: {e}")

        try:
            sina_news = await manager.get_news("sina", 50)
            for item in sina_news or []:
                if any(kw in item.title or kw in (item.content or "") for kw in kw_list):
                    items.append(item)
        except Exception as e:
            logger.warning(f"从新浪 feed 获取新闻失败: {e}")

        # 兜底：新浪 7x24 快讯（更偏“快讯流”，但能保证有用信息）
        try:
            live_news = await manager.get_live_news(80)
            for item in live_news or []:
                if any(kw in item.title or kw in (item.content or "") for kw in kw_list):
                    items.append(item)
        except Exception as e:
            logger.warning(f"从新浪7x24获取新闻失败: {e}")

        # 按时间排序
        items.sort(key=lambda x: x.publish_time, reverse=True)

        return NewsResponse(items=items[:limit], total=len(items))

    # ============ TradingView News ============

    async def get_tradingview_news(self, limit: int = 20) -> Dict[str, Any]:
        """获取TradingView资讯"""
        # TradingView API 需要特殊处理，这里提供模拟实现
        # 实际应用中需要调用TradingView API或爬虫
        import httpx
        from datetime import datetime

        try:
            async with httpx.AsyncClient() as client:
                # TradingView新闻API
                response = await client.get(
                    "https://news-headlines.tradingview.com/v2/headlines",
                    params={
                        "category": "stock",
                        "locale": "zh_CN",
                        "count": limit
                    },
                    timeout=10.0
                )

                if response.status_code == 200:
                    data = response.json()
                    items = []
                    for item in data.get("items", [])[:limit]:
                        items.append({
                            "id": str(item.get("id", "")),
                            "title": item.get("title", ""),
                            "source": item.get("provider", "TradingView"),
                            "published_at": item.get("published"),
                            "url": item.get("storyPath")
                        })
                    return {"items": items, "total": len(items)}
        except Exception:
            pass

        return {"items": [], "total": 0}

    async def get_tradingview_news_detail(self, news_id: str) -> Dict[str, Any]:
        """获取TradingView新闻详情"""
        import httpx

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"https://news-headlines.tradingview.com/v2/story/{news_id}",
                    timeout=10.0
                )

                if response.status_code == 200:
                    return response.json()
        except Exception:
            pass

        return {"id": news_id, "title": "", "content": ""}

    # ============ 热门话题/事件 ============

    @cached(ttl_seconds=CacheTTL.HOT_TOPICS, prefix="hot_topics")
    async def get_hot_topics(self, size: int = 20) -> Dict[str, Any]:
        """获取热门话题"""
        manager = await self._get_datasource_manager()

        try:
            topics = await manager.get_hot_topics(size)
            return {"items": topics}
        except Exception as e:
            logger.warning(f"获取热门话题失败: {e}")
            return {"items": []}

    @cached(ttl_seconds=CacheTTL.HOT_TOPICS, prefix="hot_events")
    async def get_hot_events(self, size: int = 20) -> Dict[str, Any]:
        """获取热门事件"""
        manager = await self._get_datasource_manager()

        try:
            events = await manager.get_hot_events(size)
            return {"items": events}
        except Exception as e:
            logger.warning(f"获取热门事件失败: {e}")
            return {"items": []}

    # ============ 投资日历 ============

    async def get_invest_calendar(self, year_month: str) -> Dict[str, Any]:
        """获取投资日历"""
        manager = await self._get_datasource_manager()

        try:
            calendar = await manager.get_invest_calendar(year_month)
            return {"items": calendar}
        except Exception as e:
            logger.warning(f"获取投资日历失败: {e}")
            return {"items": []}

    # ============ 股票公告 ============

    async def get_stock_notices(self, stock_code: str, limit: int = 20) -> Dict[str, Any]:
        """获取股票公告"""
        manager = await self._get_datasource_manager()

        try:
            raw_notices = await manager.get_stock_notices(stock_code, limit)

            # 映射数据源字段到 StockNoticeItem 所需格式
            notices = []
            for item in raw_notices:
                # 生成稳定的ID (基于URL或title+date的哈希)
                id_source = item.get("url") or f"{item.get('title', '')}{item.get('notice_date', '')}"
                notice_id = hashlib.md5(id_source.encode()).hexdigest()[:16]

                # 解析日期
                notice_date_str = item.get("notice_date", "")
                try:
                    publish_date = datetime.strptime(notice_date_str, "%Y-%m-%d")
                except (ValueError, TypeError):
                    publish_date = datetime.now()

                notices.append({
                    "id": notice_id,
                    "title": item.get("title", ""),
                    "stock_code": stock_code,
                    "stock_name": "",  # 数据源未提供，留空
                    "notice_type": item.get("notice_type", ""),
                    "publish_date": publish_date,
                    "url": item.get("url"),
                })

            return {"items": notices, "total": len(notices)}
        except Exception as e:
            logger.warning(f"获取股票公告失败: {e}")
            return {"items": [], "total": 0}
