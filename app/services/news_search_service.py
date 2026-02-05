# 新闻搜索服务
"""
多引擎新闻搜索服务 - 支持 Tavily, SerpAPI, Bocha
"""

import asyncio
import logging
import os
import re
from datetime import datetime, date
from enum import Enum
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx
from sqlalchemy import select, update, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.settings import SearchEngineConfig
from app.schemas.news import NewsItem

logger = logging.getLogger(__name__)


class SearchEngine(Enum):
    """搜索引擎类型"""
    TAVILY = "tavily"
    SERPAPI = "serpapi"
    BOCHA = "bocha"


@dataclass
class SearchKeyState:
    """搜索Key状态"""
    id: int
    api_key: str
    engine: SearchEngine
    enabled: bool
    weight: int
    daily_limit: Optional[int]
    used_today: int


class NewsSearchService:
    """多引擎新闻搜索服务"""

    # API端点配置
    ENDPOINTS = {
        SearchEngine.TAVILY: "https://api.tavily.com/search",
        SearchEngine.SERPAPI: "https://serpapi.com/search",
        # 说明：对标 daily_stock_analysis，优先使用 bocha.cn；保留 bochaai.com 作为兼容回退
        SearchEngine.BOCHA: "https://api.bocha.cn/v1/web-search",
    }

    BOCHA_FALLBACK_ENDPOINTS = [
        "https://api.bocha.cn/v1/web-search",
        "https://api.bochaai.com/v1/web-search",
    ]

    # 默认引擎尝试顺序（更偏向中文检索质量）
    DEFAULT_ENGINE_PRIORITY = [
        SearchEngine.BOCHA,
        SearchEngine.TAVILY,
        SearchEngine.SERPAPI,
    ]

    # Key 失败次数达到阈值后，临时跳过（仅内存态，重启恢复）
    KEY_ERROR_THRESHOLD = 3

    def __init__(self, db: AsyncSession):
        self.db = db
        self._keys: Dict[SearchEngine, List[SearchKeyState]] = {}
        self._current_index: Dict[SearchEngine, int] = {}
        self._initialized = False
        self._lock = asyncio.Lock()  # 保护状态更新（并发请求下避免轮询/计数乱序）
        self._key_errors: Dict[int, int] = {}  # key_id -> error_count
        self.client = httpx.AsyncClient(timeout=30.0)
        self._ensure_engine_maps()

    async def close(self):
        """关闭HTTP客户端"""
        await self.client.aclose()

    def _parse_relative_time(self, time_str: str) -> datetime:
        """
        解析相对时间字符串为datetime
        支持格式: "2 hours ago", "3 days ago", "1 week ago", "5 minutes ago"
        """
        import re
        from datetime import timedelta

        now = datetime.now()
        time_str = time_str.lower().strip()

        # 匹配数字和时间单位
        match = re.match(r'(\d+)\s*(second|minute|hour|day|week|month|year)s?\s*ago', time_str)
        if not match:
            return now

        value = int(match.group(1))
        unit = match.group(2)

        delta_map = {
            'second': timedelta(seconds=value),
            'minute': timedelta(minutes=value),
            'hour': timedelta(hours=value),
            'day': timedelta(days=value),
            'week': timedelta(weeks=value),
            'month': timedelta(days=value * 30),  # 近似值
            'year': timedelta(days=value * 365),  # 近似值
        }

        delta = delta_map.get(unit, timedelta())
        return now - delta

    def _ensure_engine_maps(self) -> None:
        """确保每个引擎在内存里都有容器，避免 add/remove 未 initialize 时 KeyError"""
        for engine in SearchEngine:
            self._keys.setdefault(engine, [])
            self._current_index.setdefault(engine, 0)

    @staticmethod
    def _parse_env_keys(value: str) -> List[str]:
        """解析环境变量中的 Key 列表（逗号分隔）。"""
        return [k.strip() for k in (value or "").split(",") if k and k.strip()]

    def _load_env_engine_keys(self) -> None:
        """
        从环境变量加载搜索 Key（对标 daily_stock_analysis 的使用方式）。

        说明：
        - 仅作为“兜底”补充，不写入数据库；
        - 用负数 id 标记环境变量 Key，避免与 DB 自增 id 冲突；
        - 方便用户零配置即可体验搜索能力（也适配 Docker/部署场景）。
        """
        env_map = {
            SearchEngine.BOCHA: ["BOCHA_API_KEYS", "BOCHA_API_KEY"],
            SearchEngine.TAVILY: ["TAVILY_API_KEYS", "TAVILY_API_KEY"],
            SearchEngine.SERPAPI: ["SERPAPI_KEYS", "SERPAPI_KEY"],
        }

        used_ids = {k.id for keys in self._keys.values() for k in keys}
        next_id = -1
        while next_id in used_ids:
            next_id -= 1

        for engine, names in env_map.items():
            # 若该引擎已存在启用的 DB Key，则不再加载环境变量 Key（避免“混用”造成不可预期轮询）
            existing_keys = self._keys.get(engine, [])
            if any(k.enabled for k in existing_keys):
                continue

            raw = ""
            for n in names:
                raw = os.getenv(n, "") or ""
                if raw.strip():
                    break
            keys = self._parse_env_keys(raw)
            if not keys:
                continue

            existing = {k.api_key for k in self._keys.get(engine, [])}
            for api_key in keys:
                if api_key in existing:
                    continue
                self._keys[engine].append(
                    SearchKeyState(
                        id=next_id,
                        api_key=api_key,
                        engine=engine,
                        enabled=True,
                        weight=1,
                        daily_limit=None,
                        used_today=0,
                    )
                )
                self._key_errors.setdefault(next_id, 0)
                next_id -= 1

    @staticmethod
    def _safe_parse_datetime(value: Any) -> Optional[datetime]:
        """尽可能解析 datetime（ISO 字符串 / datetime），失败返回 None"""
        if not value:
            return None
        if isinstance(value, datetime):
            return value
        if not isinstance(value, str):
            return None
        text = value.strip()
        if not text:
            return None
        # 兼容 Z 结尾
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00"))
        except Exception:
            return None

    @staticmethod
    def _extract_domain(url: str) -> str:
        """从 URL 提取域名作为来源（用于结果排序/展示）"""
        if not url:
            return ""
        try:
            parsed = urlparse(url)
            return (parsed.netloc or "").replace("www.", "")
        except Exception:
            return ""

    async def initialize(self) -> None:
        """从数据库加载搜索引擎配置"""
        if self._initialized:
            return

        try:
            # 检查是否需要重置今日使用量
            await self._reset_daily_usage_if_needed()

            # 加载配置
            result = await self.db.execute(
                # 注意：这里加载所有配置用于统计与启用/禁用切换；实际搜索会再按 enabled 过滤
                select(SearchEngineConfig)
            )
            configs = result.scalars().all()

            self._ensure_engine_maps()
            for engine in SearchEngine:
                self._keys[engine] = []
                self._current_index[engine] = 0

            for config in configs:
                try:
                    engine = SearchEngine(config.engine)
                    self._keys[engine].append(SearchKeyState(
                        id=config.id,
                        api_key=config.api_key,
                        engine=engine,
                        enabled=config.enabled,
                        weight=config.weight,
                        daily_limit=config.daily_limit,
                        used_today=config.used_today,
                    ))
                    # 预置错误计数（不存在则为 0）
                    self._key_errors.setdefault(config.id, 0)
                except ValueError:
                    logger.warning(f"未知搜索引擎类型: {config.engine}")

            # 补充：从环境变量加载 Key（不落库）
            self._load_env_engine_keys()

            self._initialized = True
            logger.info(f"新闻搜索服务初始化完成，加载了 {len(configs)} 个搜索引擎配置")

        except Exception as e:
            logger.error(f"初始化新闻搜索服务失败: {e}")

    async def _reset_daily_usage_if_needed(self) -> None:
        """如果是新的一天，重置使用量"""
        today = date.today()
        # 使用 or_ 处理 last_reset_date 为 NULL 的情况
        # SQL三值逻辑中 NULL != today 返回 UNKNOWN，不会匹配
        await self.db.execute(
            update(SearchEngineConfig)
            .where(
                or_(
                    SearchEngineConfig.last_reset_date.is_(None),
                    SearchEngineConfig.last_reset_date != today
                )
            )
            .values(used_today=0, last_reset_date=today)
        )
        await self.db.commit()

    def _get_next_key(self, engine: SearchEngine) -> Optional[SearchKeyState]:
        """加权轮询获取下一个可用的API Key"""
        keys = self._keys.get(engine, [])
        if not keys:
            return None

        # 过滤出可用的Key（未达到日限额）
        available_keys = [
            k for k in keys
            if k.enabled and (k.daily_limit is None or k.used_today < k.daily_limit)
        ]

        if not available_keys:
            return None

        # 临时跳过错误过多的 key（避免坏 key 反复被选中）
        filtered_keys = [
            k for k in available_keys
            if self._key_errors.get(k.id, 0) < self.KEY_ERROR_THRESHOLD
        ]
        if not filtered_keys:
            # 全部 key 都被判定为“错误过多”时，重置错误计数并继续（避免实例生命周期内被永久锁死）
            for k in available_keys:
                self._key_errors[k.id] = 0
            filtered_keys = available_keys

        # 实现加权轮询：按权重构建选择列表
        weighted_keys = []
        for k in filtered_keys:
            weighted_keys.extend([k] * max(1, k.weight))

        # 从加权列表中轮询选择
        index = self._current_index.get(engine, 0) % len(weighted_keys)
        key = weighted_keys[index]
        self._current_index[engine] = index + 1

        return key

    async def _record_key_error(self, key_id: int) -> None:
        """记录 key 的错误次数（仅内存态）"""
        async with self._lock:
            self._key_errors[key_id] = self._key_errors.get(key_id, 0) + 1

    async def _record_key_success(self, key_id: int) -> None:
        """记录 key 成功（成功后衰减错误计数，避免永久拉黑）"""
        async with self._lock:
            current = self._key_errors.get(key_id, 0)
            if current > 0:
                self._key_errors[key_id] = current - 1

    async def _increment_usage(self, key_id: int) -> None:
        """原子增加使用次数"""
        async with self._lock:
            # 仅对数据库配置的 key 记账；环境变量 key（负数 id）不落库
            if key_id > 0:
                await self.db.execute(
                    update(SearchEngineConfig)
                    .where(SearchEngineConfig.id == key_id)
                    .values(used_today=SearchEngineConfig.used_today + 1)
                )
                await self.db.commit()

            # 同步更新内存状态
            for keys in self._keys.values():
                for key in keys:
                    if key.id == key_id:
                        key.used_today += 1
                        return

    async def _build_query_variants(self, query: str) -> List[str]:
        """
        构建 query 变体（提升命中率与信息密度）

        说明：
        - 用户经常输入纯代码（600000 / sh600000），直接搜容易命中“同名无关内容”；
        - 对标 daily_stock_analysis 的做法：加入“股票/最新消息/公告/业绩”等语义锚点。
        """
        q = " ".join((query or "").strip().split())
        if not q:
            return []

        variants: List[str] = [q]

        # 尝试提取股票代码（A股常见：sh/sz + 6位数字 或 6位数字）
        code = None
        m = re.search(r"\b(?:(sh|sz)\s*)?(\d{6})\b", q, flags=re.IGNORECASE)
        if m:
            prefix = (m.group(1) or "").lower()
            digits = m.group(2)
            if prefix in ("sh", "sz"):
                code = f"{prefix}{digits}"
            else:
                # 6开头常为上证，0/3开头常为深证（仅启发式，用于检索关键词增强）
                if digits.startswith("6"):
                    code = f"sh{digits}"
                elif digits.startswith(("0", "3")):
                    code = f"sz{digits}"
                else:
                    code = digits

        # 若看起来是股票代码或过短关键词，则增强 query
        if code or len(q) <= 6:
            base = code or q
            variants.extend([
                f"{base} 股票 最新消息",
                f"{base} 公告 业绩 预告",
                f"{base} 减持 增持 回购 机构 调研",
            ])

        # 若能查到股票名称，则进一步增强（仅 DB 查询，不触发外部行情）
        if code:
            try:
                from app.models.market import StockBasic
                from sqlalchemy import or_

                digits = re.sub(r"^(sh|sz)", "", code, flags=re.IGNORECASE)
                result = await self.db.execute(
                    select(StockBasic.name).where(
                        or_(
                            StockBasic.symbol == code.lower(),
                            StockBasic.ts_code.contains(digits),
                        )
                    ).limit(1)
                )
                name = result.scalar_one_or_none()
                if name:
                    variants.extend([
                        f"{name} {code} 股票 最新消息",
                        f"{name} {code} 重大 事件 公告",
                        f"{name} 研报 评级 目标价",
                    ])
            except Exception:
                # 查询失败不影响主流程
                pass

        # 去重并保持顺序
        seen = set()
        uniq: List[str] = []
        for v in variants:
            vv = " ".join(v.strip().split())
            if not vv:
                continue
            if vv in seen:
                continue
            seen.add(vv)
            uniq.append(vv)
        return uniq[:5]  # 控制调用成本：最多 5 个变体

    @staticmethod
    def _normalize_url(url: str) -> str:
        if not url:
            return ""
        u = url.strip()
        if not u:
            return ""
        return u.rstrip("/")

    def _dedupe_and_rank(self, query: str, items: List[NewsItem], limit: int) -> List[NewsItem]:
        """对结果去重并按质量排序"""
        if not items:
            return []

        # 去重：优先按 URL，其次按 title
        dedup: Dict[str, NewsItem] = {}
        title_dedup: Dict[str, NewsItem] = {}
        for item in items:
            url_key = self._normalize_url(item.url or "")
            if url_key:
                if url_key in dedup:
                    continue
                dedup[url_key] = item
                continue

            title_key = (item.title or "").strip().lower()
            if not title_key:
                continue
            if title_key in title_dedup:
                continue
            title_dedup[title_key] = item

        merged = list(dedup.values()) + list(title_dedup.values())

        # 打分排序：来源权重 + 关键词命中 + 近似时效
        q_terms = [t for t in re.split(r"[\s/]+", (query or "").strip()) if t]
        focus_terms = ["业绩", "预告", "快报", "减持", "增持", "回购", "调研", "中标", "订单", "处罚", "诉讼", "利好", "利空"]
        trusted_domains = ["cninfo.com.cn", "eastmoney.com", "cls.cn", "sina.com.cn", "wind.com.cn", "10jqka.com.cn"]
        now = datetime.now()

        def score(n: NewsItem) -> float:
            s = 0.0
            s += {"bocha": 3.0, "tavily": 2.0, "serpapi": 1.0}.get((n.source or "").lower(), 0.0)

            text = f"{n.title}\n{n.content or ''}".lower()
            for t in q_terms[:8]:
                tt = t.lower()
                if tt and tt in text:
                    s += 0.6
            for t in focus_terms:
                if t in text:
                    s += 0.2

            domain = self._extract_domain(n.url or "").lower()
            if domain:
                for d in trusted_domains:
                    if domain.endswith(d):
                        s += 0.8
                        break

            # 近似时效：30 天内加分（publish_time 不可靠时也不会扣太多）
            try:
                dt = n.publish_time
                # naive/aware 兼容
                base_now = now if dt.tzinfo is None else datetime.now(tz=dt.tzinfo)
                days = max(0.0, (base_now - dt).total_seconds() / 86400.0)
                s += max(0.0, 1.2 - min(days, 30.0) / 30.0 * 1.2)
            except Exception:
                pass

            return s

        merged.sort(key=lambda x: (score(x), x.publish_time), reverse=True)
        return merged[:limit]

    async def _build_local_keywords(self, query: str) -> str:
        """
        为本地资讯（CLS/Sina）构造更“可命中”的关键词。

        说明：
        - 本地资讯通常不包含 sh/sz 前缀代码，更可能包含公司名称；
        - 因此优先尝试从 DB 推断股票名称，并返回“名称 + 6位代码”作为过滤关键词。
        """
        q = " ".join((query or "").strip().split())
        if not q:
            return ""

        code = None
        m = re.search(r"\b(?:(sh|sz)\s*)?(\d{6})\b", q, flags=re.IGNORECASE)
        if m:
            prefix = (m.group(1) or "").lower()
            digits = m.group(2)
            if prefix in ("sh", "sz"):
                code = f"{prefix}{digits}"
            else:
                if digits.startswith("6"):
                    code = f"sh{digits}"
                elif digits.startswith(("0", "3")):
                    code = f"sz{digits}"
                else:
                    code = digits

        name = ""
        if code:
            try:
                from app.models.market import StockBasic
                from sqlalchemy import or_

                digits = re.sub(r"^(sh|sz)", "", code, flags=re.IGNORECASE)
                result = await self.db.execute(
                    select(StockBasic.name).where(
                        or_(
                            StockBasic.symbol == code.lower(),
                            StockBasic.ts_code.contains(digits),
                        )
                    ).limit(1)
                )
                name = result.scalar_one_or_none() or ""
            except Exception:
                name = ""

        # 去掉明显的“噪声词”
        noise = {"股票", "最新", "消息", "新闻", "公告", "研报", "评级", "目标价", "怎么样", "如何", "为什么", "今天"}
        tokens = [t for t in re.split(r"[\s/]+", q) if t and t not in noise]

        # 优先：名称 + 代码
        if name and code:
            return f"{name} {re.sub(r'^(sh|sz)', '', code, flags=re.IGNORECASE)}"
        if name:
            return name
        if code:
            return re.sub(r"^(sh|sz)", "", code, flags=re.IGNORECASE)

        # 回退：取前 3 个 token，避免过宽泛
        return " ".join(tokens[:3]) if tokens else q

    async def _search_local_fallback(self, query: str, limit: int) -> List[NewsItem]:
        """当外部搜索引擎不可用/无结果时，回退到本地资讯源（CLS/Sina）"""
        try:
            from app.services.news_service import NewsService

            keywords = await self._build_local_keywords(query)
            if not keywords:
                return []

            service = NewsService(self.db)
            # 拉取更多再由 dedupe/rank 截断，避免过滤后数量不足
            fallback_limit = max(30, limit * 5)
            news = await service.search_news(keywords, limit=fallback_limit)
            return news.items or []
        except Exception as e:
            logger.warning(f"本地资讯回退失败: query={query}, err={e}")
            return []

    async def search(
        self,
        query: str,
        engine: Optional[SearchEngine] = None,
        limit: int = 10,
    ) -> List[NewsItem]:
        """
        搜索新闻

        Args:
            query: 搜索关键词
            engine: 指定搜索引擎，不指定则自动选择
            limit: 返回结果数量

        Returns:
            新闻列表
        """
        await self.initialize()

        # 确定使用的引擎
        engines_to_try = [engine] if engine else list(self.DEFAULT_ENGINE_PRIORITY)

        # query 变体（提升命中率）；最多 5 个，避免成本失控
        query_variants = await self._build_query_variants(query)
        if not query_variants:
            return []

        aggregated: List[NewsItem] = []
        had_web_key = False

        for q in query_variants:
            for eng in engines_to_try:
                # 同一个引擎可能有多个 key：逐个尝试，避免坏 key 直接导致引擎“不可用”
                attempt = 0
                while True:
                    attempt += 1
                    key_state = self._get_next_key(eng)
                    if not key_state:
                        logger.debug(f"搜索引擎 {eng.value} 无可用Key")
                        break

                    had_web_key = True
                    try:
                        if eng == SearchEngine.TAVILY:
                            results = await self._search_tavily(q, key_state.api_key, limit)
                        elif eng == SearchEngine.SERPAPI:
                            results = await self._search_serpapi(q, key_state.api_key, limit)
                        elif eng == SearchEngine.BOCHA:
                            results = await self._search_bocha(q, key_state.api_key, limit)
                        else:
                            break

                        # 成功（无论结果多少都计入使用次数；但空结果会继续尝试其它 query/引擎）
                        await self._increment_usage(key_state.id)
                        await self._record_key_success(key_state.id)

                        if results:
                            aggregated.extend(results)
                            logger.info(f"使用 {eng.value} 搜索成功: query={q}, results={len(results)}")

                        # 若已经拿到足够结果，提前结束
                        ranked = self._dedupe_and_rank(query, aggregated, limit)
                        if len(ranked) >= limit:
                            return ranked

                        # 当前引擎有结果但不足，继续其他引擎/变体补齐
                        break

                    except Exception as e:
                        await self._record_key_error(key_state.id)
                        logger.warning(f"搜索引擎 {eng.value} 搜索失败: query={q}, attempt={attempt}, err={e}")
                        # 尝试该引擎的下一个 key（最多尝试配置数量次，避免死循环）
                        if attempt >= max(1, len(self._keys.get(eng, []))):
                            break
                        continue

        if aggregated:
            return self._dedupe_and_rank(query, aggregated, limit)

        # 外部搜索无结果时回退到本地资讯（确保接口尽量返回“可用信息”）
        local_items = await self._search_local_fallback(query, limit)
        if local_items:
            logger.info(
                f"外部搜索无结果，使用本地资讯回退: query={query}, web_key={had_web_key}, local_results={len(local_items)}"
            )
            return self._dedupe_and_rank(query, local_items, limit)

        logger.error(f"所有搜索引擎都失败或无结果: {query} (web_key={had_web_key})")
        return []

    async def _search_tavily(self, query: str, api_key: str, limit: int) -> List[NewsItem]:
        """Tavily搜索"""
        url = self.ENDPOINTS[SearchEngine.TAVILY]

        payload = {
            "api_key": api_key,
            "query": query,
            # 对标 daily_stock_analysis：更深的检索更容易拿到“有用信息”（代价是更慢/更贵）
            "search_depth": "advanced",
            "include_domains": [],
            "exclude_domains": [],
            "max_results": limit,
            # Tavily 支持 days（部分版本/接口可能忽略该字段；若报错会被上层兜底到其他引擎）
            "days": 7,
        }

        response = await self.client.post(url, json=payload)
        response.raise_for_status()
        data = response.json()

        results = []
        for item in data.get("results", []):
            pub = self._safe_parse_datetime(item.get("published_date")) or datetime.now()
            content = item.get("content", "") or ""
            results.append(NewsItem(
                news_id=item.get("url", ""),
                title=item.get("title", ""),
                content=content[:800],
                source="tavily",
                publish_time=pub,
                url=item.get("url", ""),
                image_url="",
            ))

        return results

    async def _search_serpapi(self, query: str, api_key: str, limit: int) -> List[NewsItem]:
        """SerpAPI搜索（默认使用百度引擎更适配中文环境；兼容解析 news_results/organic_results）"""
        url = self.ENDPOINTS[SearchEngine.SERPAPI]

        # 对标 daily_stock_analysis：中文场景更建议使用 baidu engine
        params = {"api_key": api_key, "engine": "baidu", "q": query}

        response = await self.client.get(url, params=params)
        response.raise_for_status()
        data = response.json()

        results = []

        # 兼容：Google News (news_results) 与 Baidu/Google (organic_results)
        if data.get("news_results"):
            rows = data.get("news_results", [])[:limit]
            for item in rows:
                pub_time = datetime.now()
                if "date" in item:
                    pub_time = self._parse_relative_time(str(item["date"]))
                results.append(NewsItem(
                    news_id=item.get("link", ""),
                    title=item.get("title", ""),
                    content=(item.get("snippet", "") or "")[:800],
                    source="serpapi",
                    publish_time=pub_time,
                    url=item.get("link", ""),
                    image_url=item.get("thumbnail", ""),
                ))
        else:
            rows = data.get("organic_results", [])[:limit]
            for item in rows:
                pub_time = datetime.now()
                if "date" in item:
                    pub_time = self._parse_relative_time(str(item["date"]))
                link = item.get("link", "")
                results.append(NewsItem(
                    news_id=link,
                    title=item.get("title", ""),
                    content=(item.get("snippet", "") or "")[:800],
                    source="serpapi",
                    publish_time=pub_time,
                    url=link,
                    image_url="",
                ))

        return results

    async def _search_bocha(self, query: str, api_key: str, limit: int) -> List[NewsItem]:
        """博查搜索"""
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "query": query,
            # 对标 daily_stock_analysis：近一个月更适合覆盖财报/公告/重大事项
            "freshness": "oneMonth",
            "summary": True,
            "count": limit,
        }

        last_exc: Optional[Exception] = None
        data: Dict[str, Any] = {}
        for url in self.BOCHA_FALLBACK_ENDPOINTS:
            try:
                response = await self.client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
                last_exc = None
                break
            except httpx.HTTPStatusError as e:
                last_exc = e
                status = e.response.status_code
                # 401/403 多半是 key 问题，换域名通常无意义，直接抛给上层触发换 key/引擎
                if status in (401, 403):
                    raise
                continue
            except Exception as e:
                last_exc = e
                continue

        if last_exc is not None and not data:
            raise last_exc

        results = []
        for item in data.get("data", {}).get("webPages", {}).get("value", []):
            # 解析发布时间
            pub_time = datetime.now()
            if "datePublished" in item:
                try:
                    pub_time = datetime.fromisoformat(item["datePublished"].replace("Z", "+00:00"))
                except Exception:
                    pass

            content = item.get("summary") or item.get("snippet") or ""
            results.append(NewsItem(
                news_id=item.get("url", ""),
                title=item.get("name", ""),
                content=str(content)[:800],
                source="bocha",
                publish_time=pub_time,
                url=item.get("url", ""),
                image_url="",
            ))

        return results

    async def search_as_context(
        self,
        query: str,
        engine: Optional[SearchEngine] = None,
        limit: int = 8,
        max_items_in_context: int = 5,
    ) -> str:
        """搜索并格式化为可直接喂给 LLM 的上下文文本"""
        items = await self.search(query=query, engine=engine, limit=limit)
        return self.format_as_context(query=query, items=items, max_items=max_items_in_context)

    @staticmethod
    def format_as_context(query: str, items: List[NewsItem], max_items: int = 5) -> str:
        """将搜索结果转换为“信息密度更高”的上下文文本"""
        q = (query or "").strip()
        if not items:
            return f"【检索结果】query={q}\n未找到相关结果。"

        lines = [f"【检索结果】query={q}"]
        for i, item in enumerate(items[:max_items], 1):
            t = item.publish_time.strftime("%Y-%m-%d %H:%M") if item.publish_time else "未知时间"
            url = item.url or ""
            title = (item.title or "").strip()
            content = (item.content or "").strip()
            if len(content) > 220:
                content = content[:220] + "..."
            lines.append(f"\n{i}. [{item.source}] {title} ({t})")
            if content:
                lines.append(content)
            if url:
                lines.append(url)
        return "\n".join(lines)

    def get_engine_status(self) -> List[Dict[str, Any]]:
        """获取所有搜索引擎状态"""
        status = []

        for engine in SearchEngine:
            keys = self._keys.get(engine, [])
            enabled_keys = [k for k in keys if k.enabled]

            total_daily_limit = None
            if all(k.daily_limit is not None for k in enabled_keys):
                total_daily_limit = sum(k.daily_limit for k in enabled_keys)

            total_used = sum(k.used_today for k in enabled_keys)

            status.append({
                "engine": engine.value,
                "total_keys": len(keys),
                "enabled_keys": len(enabled_keys),
                "total_daily_limit": total_daily_limit,
                "total_used_today": total_used,
            })

        return status

    async def add_engine_config(
        self,
        engine: SearchEngine,
        api_key: str,
        enabled: bool = True,
        weight: int = 1,
        daily_limit: Optional[int] = None,
    ) -> int:
        """添加搜索引擎配置"""
        config = SearchEngineConfig(
            engine=engine.value,
            api_key=api_key,
            enabled=enabled,
            weight=weight,
            daily_limit=daily_limit,
            used_today=0,
            last_reset_date=date.today(),
        )
        self.db.add(config)
        await self.db.commit()
        await self.db.refresh(config)

        # 更新内存状态
        self._ensure_engine_maps()
        self._keys[engine].append(SearchKeyState(
            id=config.id,
            api_key=api_key,
            engine=engine,
            enabled=enabled,
            weight=weight,
            daily_limit=daily_limit,
            used_today=0,
        ))
        self._key_errors.setdefault(config.id, 0)

        return config.id

    async def remove_engine_config(self, config_id: int) -> bool:
        """删除搜索引擎配置"""
        result = await self.db.execute(
            select(SearchEngineConfig).where(SearchEngineConfig.id == config_id)
        )
        config = result.scalar_one_or_none()

        if not config:
            return False

        await self.db.delete(config)
        await self.db.commit()

        # 更新内存状态
        try:
            engine = SearchEngine(config.engine)
            self._ensure_engine_maps()
            self._keys[engine] = [k for k in self._keys.get(engine, []) if k.id != config_id]
            self._key_errors.pop(config_id, None)
        except ValueError:
            pass

        return True
