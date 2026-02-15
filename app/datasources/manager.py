# 数据源管理器
"""
多数据源管理器，支持熔断和自动故障转移
"""

import asyncio
import logging
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any, Callable, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.settings import DataSourceConfig
from app.datasources.registry import load_client_class
from app.utils.helpers import parse_stock_code

logger = logging.getLogger(__name__)

T = TypeVar("T")


class CircuitState(Enum):
    """熔断器状态"""
    CLOSED = "closed"       # 正常工作
    OPEN = "open"           # 熔断中
    HALF_OPEN = "half_open" # 尝试恢复


class CircuitBreaker:
    """熔断器实现"""

    def __init__(
        self,
        name: str,
        failure_threshold: int = 3,
        cooldown_seconds: float = 300,
        half_open_max_calls: int = 1,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.half_open_max_calls = half_open_max_calls

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: Optional[datetime] = None
        self._half_open_calls = 0

    @property
    def state(self) -> CircuitState:
        """获取当前状态，自动检查是否可以转换到半开状态"""
        if self._state == CircuitState.OPEN:
            if self._last_failure_time:
                elapsed = (datetime.now() - self._last_failure_time).total_seconds()
                if elapsed >= self.cooldown_seconds:
                    logger.info(f"熔断器 {self.name} 冷却完成，转换到半开状态")
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_calls = 0
        return self._state

    def record_success(self) -> None:
        """记录成功调用"""
        if self._state == CircuitState.HALF_OPEN:
            logger.info(f"熔断器 {self.name} 半开状态成功，恢复正常")
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._last_failure_time = None
        elif self._state == CircuitState.CLOSED:
            self._failure_count = 0

    def record_failure(self) -> None:
        """记录失败调用"""
        self._failure_count += 1
        self._last_failure_time = datetime.now()

        if self._state == CircuitState.HALF_OPEN:
            logger.warning(f"熔断器 {self.name} 半开状态失败，重新熔断")
            self._state = CircuitState.OPEN
        elif self._state == CircuitState.CLOSED:
            if self._failure_count >= self.failure_threshold:
                logger.warning(f"熔断器 {self.name} 失败次数达到阈值 {self.failure_threshold}，开始熔断")
                self._state = CircuitState.OPEN

    def can_execute(self) -> bool:
        """检查是否可以执行调用"""
        state = self.state  # 触发自动状态检查
        if state == CircuitState.CLOSED:
            return True
        elif state == CircuitState.HALF_OPEN:
            if self._half_open_calls < self.half_open_max_calls:
                self._half_open_calls += 1
                return True
            return False
        else:  # OPEN
            return False

    def reset(self) -> None:
        """重置熔断器"""
        logger.info(f"熔断器 {self.name} 被重置")
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time = None
        self._half_open_calls = 0

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self._failure_count,
            "failure_threshold": self.failure_threshold,
            "cooldown_seconds": self.cooldown_seconds,
            "last_failure_time": self._last_failure_time.isoformat() if self._last_failure_time else None,
        }


class DataSourceManager:
    """数据源管理器 - 支持多数据源自动故障转移"""

    # 默认数据源优先级
    DEFAULT_PRIORITY = ["sina", "eastmoney", "tencent", "tushare"]

    def __init__(self):
        self._breakers: Dict[str, CircuitBreaker] = {}
        self._clients: Dict[str, Any] = {}
        self._priority_order: List[str] = self.DEFAULT_PRIORITY.copy()
        self._initialized = False
        # 数据源 API Key/Token（从 datasource_config.api_key 加载；用于需鉴权的数据源，如 tushare）
        self._api_keys: Dict[str, str] = {}
        # 是否已从数据库加载过 DataSourceConfig（用于区分“未配置”与“已配置但禁用/排序”）
        self._has_db_config: bool = False
        # DB 已出现（显式配置过）的数据源集合；用于解决“只配置了部分数据源导致能力白名单过滤为空”的隐蔽问题
        self._configured_sources: set[str] = set()
        # DB 中显式禁用的数据源集合（缺失行不视为禁用）
        self._disabled_sources: set[str] = set()

    async def initialize(self, db: Optional[AsyncSession] = None) -> None:
        """初始化数据源管理器"""
        # 已初始化：如果提供 db，则刷新配置（避免首次 initialize() 未传 db 导致配置永远不生效）
        if self._initialized:
            if db:
                await self._load_config(db)
            return

        # 初始化默认熔断器
        for source in self.DEFAULT_PRIORITY:
            if source not in self._breakers:
                self._breakers[source] = CircuitBreaker(name=source)

        # 从数据库加载配置
        if db:
            await self._load_config(db)

        self._initialized = True
        logger.info(f"数据源管理器初始化完成，优先级: {self._priority_order}")

    async def _load_config(self, db: AsyncSession) -> None:
        """从数据库加载配置"""
        try:
            result = await db.execute(
                select(DataSourceConfig).order_by(DataSourceConfig.priority)
            )
            all_configs = result.scalars().all()
            self._api_keys = {c.source_name: (c.api_key or "") for c in all_configs}

            # 只要表里有配置，就视为“存在显式配置”。但对某个能力而言：
            # - 若该能力允许的数据源在 DB 中完全未出现，则视为“未配置”，回退到方法级默认顺序；
            # - 若已出现但被禁用，则必须尊重禁用，不得回退绕过。
            self._has_db_config = bool(all_configs)
            self._configured_sources = {c.source_name for c in all_configs}
            self._disabled_sources = {c.source_name for c in all_configs if not c.enabled}

            if not all_configs:
                # 数据库中未配置任何数据源：回退到默认优先级（保持与“未配置”场景一致）
                self._priority_order = self.DEFAULT_PRIORITY.copy()
                self._api_keys = {}
                for source in self.DEFAULT_PRIORITY:
                    if source not in self._breakers:
                        self._breakers[source] = CircuitBreaker(name=source)
                logger.info("数据库中未配置数据源，使用默认优先级")
                return

            enabled_configs = [c for c in all_configs if c.enabled]
            self._priority_order = [c.source_name for c in enabled_configs]

            for config in enabled_configs:
                self._breakers[config.source_name] = CircuitBreaker(
                    name=config.source_name,
                    failure_threshold=config.failure_threshold,
                    cooldown_seconds=config.cooldown_seconds,
                )

            if not enabled_configs:
                logger.warning("数据源配置存在但均为禁用，当前将不尝试任何数据源")
            else:
                logger.info(f"从数据库加载数据源配置: {self._priority_order}")
        except Exception as e:
            logger.warning(f"加载数据源配置失败，使用默认配置: {e}")

    async def _resolve_sources(self, allowed: List[str], default_order: List[str]) -> List[str]:
        """按“数据库优先级/启用配置”解析最终尝试顺序，并限制在能力允许的数据源集合内"""
        if not self._initialized:
            await self.initialize()

        if self._has_db_config:
            allowed_set = set(allowed or [])

            # 隐蔽 bug：DB 里只配置了部分数据源（例如仅 sina），会导致某些能力（如 K 线只允许 tencent/eastmoney）
            # 过滤后得到空列表，从而“明明可用却完全不尝试”。这里按能力维度做回退：
            # - 若 allowed 在 DB 中完全未出现：视为未配置，走 default_order
            # - 若 allowed 中有任一项出现：尊重 DB 的 enabled/priority，并用“未配置项”作为兜底回退
            configured_allowed = [s for s in allowed_set if s in self._configured_sources]
            if not configured_allowed:
                return [s for s in default_order if s in allowed_set]

            resolved: List[str] = [s for s in self._priority_order if s in allowed_set]

            # 将“allowed 但未配置”的数据源追加为兜底（保持 default_order 顺序），但绝不引入被显式禁用的源
            for s in default_order:
                if s not in allowed_set:
                    continue
                if s in resolved:
                    continue
                if s in self._disabled_sources:
                    continue
                resolved.append(s)

            return resolved

        # 未配置时：保持方法级默认顺序，避免“全局默认优先级”影响关键链路默认行为
        allowed_set = set(allowed or [])
        return [s for s in default_order if s in allowed_set]

    def _get_breaker(self, source: str) -> CircuitBreaker:
        """获取/创建熔断器（允许显式调用未在默认优先级中的数据源，如 cls/fund）。"""
        name = (source or "").strip()
        if not name:
            raise ValueError("source 不能为空")
        breaker = self._breakers.get(name)
        if breaker is None:
            breaker = CircuitBreaker(name=name)
            self._breakers[name] = breaker
        return breaker

    @property
    def has_db_config(self) -> bool:
        """是否存在数据库配置（用于区分“未配置”与“已配置但禁用”）。"""
        return self._has_db_config

    @property
    def enabled_priority_order(self) -> List[str]:
        """当前启用的数据源优先级顺序（可能为空）。"""
        return list(self._priority_order)

    @property
    def all_disabled(self) -> bool:
        """数据库已为所有默认数据源做了显式配置，且均为禁用（此时不应静默回退默认数据源）。"""
        return (
            self._has_db_config
            and not self._priority_order
            and set(self.DEFAULT_PRIORITY).issubset(self._configured_sources)
        )

    def _get_client(self, source: str) -> Any:
        """获取数据源客户端实例"""
        if source not in self._clients:
            cls = load_client_class(source)

            # 仅对“需要鉴权”的数据源传参，其它数据源保持零参数构造，减少耦合
            init_kwargs: Dict[str, Any] = {}
            if source == "tushare":
                token = (self._api_keys.get("tushare") or "").strip()
                if token:
                    init_kwargs["token"] = token

            try:
                self._clients[source] = cls(**init_kwargs)
            except TypeError:
                # 兼容：单测 FakeClient 可能不接受 token 参数
                self._clients[source] = cls()

        return self._clients[source]

    async def close_all(self) -> None:
        """关闭所有客户端"""
        for name, client in self._clients.items():
            try:
                if hasattr(client, "close"):
                    await client.close()
            except Exception as e:
                logger.warning(f"关闭客户端 {name} 失败: {e}")
        self._clients.clear()

    async def execute_with_failover(
        self,
        method_name: str,
        *args,
        sources: Optional[List[str]] = None,
        validate: Optional[Callable[[T], bool]] = None,
        **kwargs,
    ) -> T:
        """
        使用故障转移执行数据源方法

        Args:
            method_name: 要调用的方法名
            *args: 方法参数
            sources: 指定数据源列表，默认按优先级尝试所有源
            **kwargs: 方法关键字参数

        Returns:
            方法返回值

        Raises:
            Exception: 所有数据源都失败时抛出最后一个异常
        """
        if not self._initialized:
            await self.initialize()

        # 注意：sources=[] 表示显式“不尝试任何数据源”，不能回退到默认优先级
        sources_to_try = self._priority_order if sources is None else sources
        last_error: Optional[Exception] = None

        for source in sources_to_try:
            breaker = self._get_breaker(source)

            if not breaker.can_execute():
                logger.debug(f"数据源 {source} 处于熔断状态，跳过")
                continue

            try:
                client = self._get_client(source)
                method = getattr(client, method_name, None)
                if not method:
                    logger.debug(f"数据源 {source} 不支持方法 {method_name}")
                    continue

                result = await method(*args, **kwargs)
                if validate and not validate(result):
                    raise ValueError(f"数据源 {source}.{method_name} 返回无效结果")
                # 若返回对象支持 source 字段，则补齐来源，便于前端诊断当前使用的是哪个数据源
                try:
                    if hasattr(result, "source"):
                        cur = getattr(result, "source", "")
                        if not cur:
                            setattr(result, "source", source)
                except Exception:
                    pass
                breaker.record_success()
                logger.debug(f"数据源 {source}.{method_name} 调用成功")
                return result

            except Exception as e:
                breaker.record_failure()
                last_error = e
                logger.warning(f"数据源 {source}.{method_name} 调用失败: {e}")
                continue

        # 所有数据源都失败
        error_msg = f"所有数据源 {sources_to_try} 都失败，方法: {method_name}"
        logger.error(error_msg)
        if last_error:
            raise last_error
        raise Exception(error_msg)

    async def execute_with_failover_map(
        self,
        methods: Dict[str, str],
        *args,
        sources: Optional[List[str]] = None,
        validate: Optional[Callable[[T], bool]] = None,
        **kwargs,
    ) -> T:
        """
        使用故障转移执行“不同数据源不同方法名”的调用。

        典型场景：
        - 东财方法叫 `get_stock_rank_enhanced`，新浪兜底方法叫 `get_stock_rank`；
        - 业务侧希望统一成一个能力：`get_stock_rank()`。
        """
        if not self._initialized:
            await self.initialize()

        # 注意：sources=[] 表示显式“不尝试任何数据源”，不能回退到默认优先级
        sources_to_try = self._priority_order if sources is None else sources
        last_error: Optional[Exception] = None

        for source in sources_to_try:
            method_name = (methods or {}).get(source)
            if not method_name:
                continue

            breaker = self._get_breaker(source)

            if not breaker.can_execute():
                logger.debug(f"数据源 {source} 处于熔断状态，跳过")
                continue

            try:
                client = self._get_client(source)
                method = getattr(client, method_name, None)
                if not method:
                    logger.debug(f"数据源 {source} 不支持方法 {method_name}")
                    continue

                result = await method(*args, **kwargs)
                if validate and not validate(result):
                    raise ValueError(f"数据源 {source}.{method_name} 返回无效结果")

                # 若返回对象支持 source 字段，则补齐来源，便于前端诊断当前使用的是哪个数据源
                try:
                    if hasattr(result, "source"):
                        cur = getattr(result, "source", "")
                        if not cur:
                            setattr(result, "source", source)
                except Exception:
                    pass

                breaker.record_success()
                logger.debug(f"数据源 {source}.{method_name} 调用成功")
                return result

            except Exception as e:
                breaker.record_failure()
                last_error = e
                logger.warning(f"数据源 {source}.{method_name} 调用失败: {e}")
                continue

        error_msg = f"所有数据源 {sources_to_try} 都失败，methods: {methods}"
        logger.error(error_msg)
        if last_error:
            raise last_error
        raise Exception(error_msg)

    # ============ 便捷方法 ============

    async def get_realtime_quotes(self, codes: List[str]) -> List[Any]:
        """获取实时行情（自动故障转移）"""
        sources = await self._resolve_sources(allowed=["sina"], default_order=["sina"])
        return await self.execute_with_failover(
            "get_realtime_quotes",
            codes,
            sources=sources,
        )

    async def get_kline(
        self,
        code: str,
        period: str = "day",
        count: int = 100,
        adjust: str = "qfq",
    ) -> Any:
        """获取K线数据（自动故障转移）"""
        def _validate_kline_response(resp: Any) -> bool:
            return bool(getattr(resp, "data", None))

        market, _ = parse_stock_code(code)
        period_norm = (period or "day").strip().lower()

        # 港/美股：当前仅支持日/周/月（akshare 兜底；腾讯对港股也可能可用）
        if market in {"hk", "us"} and period_norm not in {"day", "week", "month"}:
            raise ValueError("港/美股 K线仅支持 day/week/month")

        if market == "us":
            sources = await self._resolve_sources(
                allowed=["akshare"],
                default_order=["akshare"],
            )
        elif market == "hk":
            sources = await self._resolve_sources(
                allowed=["tencent", "akshare"],
                default_order=["tencent", "akshare"],
            )
        else:
            sources = await self._resolve_sources(
                allowed=["tencent", "eastmoney"],
                default_order=["tencent", "eastmoney"],
            )

        return await self.execute_with_failover(
            "get_kline",
            code,
            period=period,
            count=count,
            adjust=adjust,
            sources=sources,
            validate=_validate_kline_response,
        )

    async def get_minute_data(self, code: str) -> Any:
        """获取分时数据（自动故障转移）"""
        def _validate_minute_response(resp: Any) -> bool:
            return bool(getattr(resp, "data", None))

        # 经验：新浪分时接口在部分网络环境下可能直接返回 Service not found；默认先尝试东财 trends2
        sources = await self._resolve_sources(
            allowed=["eastmoney", "sina"],
            default_order=["eastmoney", "sina"],
        )
        return await self.execute_with_failover(
            "get_minute_data",
            code,
            sources=sources,
            validate=_validate_minute_response,
        )

    async def get_stock_money_flow(self, stock_code: str, days: int = 10) -> List[Any]:
        """获取个股资金流向明细（默认东财）"""
        sources = await self._resolve_sources(allowed=["eastmoney"], default_order=["eastmoney"])
        return await self.execute_with_failover(
            "get_stock_money_flow",
            stock_code,
            days,
            sources=sources,
        )

    async def get_money_trend(self, stock_code: str, days: int = 10) -> List[Any]:
        """获取资金趋势（默认新浪；当前实现为兜底空列表）"""
        sources = await self._resolve_sources(allowed=["sina"], default_order=["sina"])
        return await self.execute_with_failover(
            "get_money_trend",
            stock_code,
            days,
            sources=sources,
        )

    async def get_stock_concepts(self, stock_code: str) -> List[Any]:
        """获取个股概念/板块（默认东财）"""
        sources = await self._resolve_sources(allowed=["eastmoney"], default_order=["eastmoney"])
        return await self.execute_with_failover(
            "get_stock_concepts",
            stock_code,
            sources=sources,
        )

    async def get_hot_stocks(self, market: str = "A", limit: int = 20) -> List[Any]:
        """获取热门股票（默认东财）"""
        sources = await self._resolve_sources(allowed=["eastmoney"], default_order=["eastmoney"])
        return await self.execute_with_failover(
            "get_hot_stocks",
            market,
            limit,
            sources=sources,
        )

    async def get_stock_fundamental(self, stock_code: str) -> Dict[str, Any]:
        """获取个股估值/基本面（默认东财）"""
        sources = await self._resolve_sources(allowed=["eastmoney"], default_order=["eastmoney"])
        return await self.execute_with_failover(
            "get_stock_fundamental",
            stock_code,
            sources=sources,
        )

    async def get_financial_report(self, stock_code: str) -> Dict[str, Any]:
        """获取财务报表（默认东财）"""
        sources = await self._resolve_sources(allowed=["eastmoney"], default_order=["eastmoney"])
        return await self.execute_with_failover(
            "get_financial_report",
            stock_code,
            sources=sources,
        )

    async def get_stock_rank(
        self,
        sort_by: str = "change_percent",
        order: str = "desc",
        limit: int = 50,
        market: str = "all",
    ) -> List[Dict[str, Any]]:
        """获取股票排行榜（东财优先，新浪兜底）"""

        def _validate_rank(resp: Any) -> bool:
            return bool(resp)

        sources = await self._resolve_sources(
            allowed=["eastmoney", "sina"],
            default_order=["eastmoney", "sina"],
        )
        return await self.execute_with_failover_map(
            {
                "eastmoney": "get_stock_rank_enhanced",
                "sina": "get_stock_rank",
            },
            sort_by=sort_by,
            order=order,
            limit=limit,
            market=market,
            sources=sources,
            validate=_validate_rank,
        )

    async def get_industry_research_reports(self, name: str = "", code: str = "", limit: int = 20) -> List[Any]:
        """获取行业研报（默认东财）"""
        sources = await self._resolve_sources(allowed=["eastmoney"], default_order=["eastmoney"])
        return await self.execute_with_failover(
            "get_industry_research_reports",
            name,
            code,
            limit,
            sources=sources,
        )

    async def get_news(self, source: str, limit: int = 20) -> List[Any]:
        """获取资讯列表（支持 cls/sina）。"""
        name = (source or "").strip().lower()
        if not name:
            raise ValueError("source 不能为空")
        return await self.execute_with_failover(
            "get_news",
            int(limit),
            sources=[name],
        )

    async def get_telegraph(self, source: str, page: int = 1, page_size: int = 20) -> Any:
        """获取电报/快讯（cls: get_telegraph；sina: get_live_telegraph）。"""
        name = (source or "").strip().lower()
        if not name:
            raise ValueError("source 不能为空")

        method_map = {
            "cls": "get_telegraph",
            "sina": "get_live_telegraph",
        }
        method = method_map.get(name)
        if not method:
            raise ValueError(f"不支持的电报来源: {source}")

        return await self.execute_with_failover(
            method,
            int(page),
            int(page_size),
            sources=[name],
        )

    async def search_funds(self, keyword: str, fund_type: str | None = None, limit: int = 20) -> Any:
        """搜索基金（默认使用天天基金）。"""
        return await self.execute_with_failover(
            "search_funds",
            keyword,
            fund_type,
            int(limit),
            sources=["fund"],
        )

    async def get_fund_detail(self, fund_code: str) -> Any:
        """获取基金详情（默认使用天天基金）。"""
        return await self.execute_with_failover(
            "get_fund_detail",
            fund_code,
            sources=["fund"],
        )

    async def get_fund_net_value(self, fund_code: str, days: int = 30) -> Any:
        """获取基金净值历史（默认使用天天基金）。"""
        return await self.execute_with_failover(
            "get_fund_net_value",
            fund_code,
            int(days),
            sources=["fund"],
        )

    async def get_stock_rating_summary(self, stock_code: str) -> Dict[str, Any]:
        """获取机构评级汇总（默认东财）"""
        sources = await self._resolve_sources(allowed=["eastmoney"], default_order=["eastmoney"])
        return await self.execute_with_failover(
            "get_stock_rating_summary",
            stock_code,
            sources=sources,
        )

    async def get_stock_money_flow_history(self, stock_code: str, days: int = 30) -> List[Any]:
        """获取个股历史资金流向（默认东财）"""
        sources = await self._resolve_sources(allowed=["eastmoney"], default_order=["eastmoney"])
        return await self.execute_with_failover(
            "get_stock_money_flow_history",
            stock_code,
            days,
            sources=sources,
        )

    async def get_shareholder_count(self, stock_code: str) -> List[Any]:
        """获取股东人数变化（默认东财）"""
        sources = await self._resolve_sources(allowed=["eastmoney"], default_order=["eastmoney"])
        return await self.execute_with_failover(
            "get_shareholder_count",
            stock_code,
            sources=sources,
        )

    async def get_top_holders(self, stock_code: str, holder_type: str = "float") -> List[Any]:
        """获取十大股东/十大流通股东（默认东财）"""
        sources = await self._resolve_sources(allowed=["eastmoney"], default_order=["eastmoney"])
        return await self.execute_with_failover(
            "get_top_holders",
            stock_code,
            holder_type,
            sources=sources,
        )

    async def get_dividend_history(self, stock_code: str) -> List[Any]:
        """获取分红送转历史（默认东财）"""
        sources = await self._resolve_sources(allowed=["eastmoney"], default_order=["eastmoney"])
        return await self.execute_with_failover(
            "get_dividend_history",
            stock_code,
            sources=sources,
        )

    # ============ MarketService 复用方法 ============

    async def get_long_tiger(self, trade_date: Optional[str] = None) -> Any:
        """获取龙虎榜（默认东财）。"""
        sources = await self._resolve_sources(allowed=["eastmoney"], default_order=["eastmoney"])
        return await self.execute_with_failover(
            "get_long_tiger",
            trade_date,
            sources=sources,
        )

    async def get_economic_data(self, indicator: str, count: int = 20) -> Any:
        """获取宏观经济数据（默认东财）。"""
        sources = await self._resolve_sources(allowed=["eastmoney"], default_order=["eastmoney"])
        return await self.execute_with_failover(
            "get_economic_data",
            indicator,
            int(count),
            sources=sources,
        )

    async def get_sector_stocks(self, bk_code: str, limit: int = 50) -> Any:
        """获取板块成分股（默认东财）。"""
        sources = await self._resolve_sources(allowed=["eastmoney"], default_order=["eastmoney"])
        return await self.execute_with_failover(
            "get_sector_stocks",
            bk_code,
            int(limit),
            sources=sources,
        )

    async def get_concept_rank(
        self,
        sort_by: str = "change_percent",
        order: str = "desc",
        limit: int = 20,
    ) -> Any:
        """获取概念板块排名（默认东财）。"""
        sources = await self._resolve_sources(allowed=["eastmoney"], default_order=["eastmoney"])
        return await self.execute_with_failover(
            "get_concept_rank",
            sort_by,
            order,
            int(limit),
            sources=sources,
        )

    async def get_industry_rank(
        self,
        sort_by: str = "change_percent",
        order: str = "desc",
        limit: int = 20,
    ) -> Any:
        """获取行业排名（默认东财）。"""

        def _validate(resp: Any) -> bool:
            try:
                items = getattr(resp, "items", None)
                return bool(items)
            except Exception:
                return False

        sources = await self._resolve_sources(allowed=["eastmoney"], default_order=["eastmoney"])
        return await self.execute_with_failover(
            "get_industry_rank",
            sort_by,
            order,
            int(limit),
            sources=sources,
            validate=_validate,
        )

    async def get_board_money_flow_rank(
        self,
        category: str = "hangye",
        sort_by: str = "main_net_inflow",
        order: str = "desc",
        limit: int = 50,
        sources: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """获取行业/概念板块资金流向排名（东财优先，新浪兜底）。"""

        def _normalize_category(val: str) -> str:
            name = (val or "").strip().lower()
            if name in ("hangye", "industry"):
                return "hangye"
            if name in ("gainian", "concept"):
                return "gainian"
            if name in ("diqu", "region"):
                return "diqu"
            return name or "hangye"

        normalized_category = _normalize_category(category)

        # 兼容前端历史参数
        if sort_by in ("main_inflow", "main_net_inflow", "zjlr", "netamount"):
            em_sort_by = "main_net_inflow"
        else:
            em_sort_by = sort_by

        sina_sort_map = {
            "main_inflow": "netamount",
            "main_net_inflow": "netamount",
            "zjlr": "netamount",
            "netamount": "netamount",
            "change_percent": "avg_changeratio",
            "avg_changeratio": "avg_changeratio",
            "turnover": "turnover",
        }
        sina_sort = sina_sort_map.get(sort_by, "netamount")

        if sources is None:
            sources_to_try = await self._resolve_sources(
                allowed=["eastmoney", "sina"],
                default_order=["eastmoney", "sina"],
            )
        else:
            override: List[str] = []
            for s in sources or []:
                name = (s or "").strip().lower()
                if name in ("eastmoney", "sina") and name not in override:
                    override.append(name)
            if not override:
                raise ValueError("sources 不能为空")
            sources_to_try = await self._resolve_sources(allowed=override, default_order=override)

        last_error: Optional[Exception] = None
        for source in sources_to_try:
            breaker = self._get_breaker(source)
            if not breaker.can_execute():
                logger.debug(f"数据源 {source} 处于熔断状态，跳过")
                continue

            try:
                client = self._get_client(source)
                method = getattr(client, "get_board_money_flow_rank", None)
                if not method:
                    logger.debug(f"数据源 {source} 不支持方法 get_board_money_flow_rank")
                    continue

                if source == "eastmoney":
                    rows = await method(
                        category=normalized_category,
                        sort_by=em_sort_by,
                        order=order,
                        limit=int(limit),
                    )
                elif source == "sina":
                    rows = await method(
                        category=normalized_category,
                        limit=int(limit),
                        sort=sina_sort,
                        order=order,
                    )
                else:
                    continue

                if not rows:
                    raise ValueError(f"数据源 {source}.get_board_money_flow_rank 返回为空")

                breaker.record_success()
                return rows

            except Exception as e:
                breaker.record_failure()
                last_error = e
                logger.warning(f"数据源 {source}.get_board_money_flow_rank 调用失败: {e}")

        if last_error:
            raise last_error
        raise RuntimeError("所有数据源都失败：get_board_money_flow_rank")

    async def get_stock_money_rank(
        self,
        sort_by: str = "main_net_inflow",
        order: str = "desc",
        limit: int = 50,
        sources: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """获取股票资金流入排名（东财优先，新浪兜底）。"""
        em_sort_map = {
            # 兼容前端历史参数
            "main_inflow": "main_net_inflow",
            "main_net_inflow": "main_net_inflow",
            "zjlr": "main_net_inflow",
            "trade": "current_price",
            "current_price": "current_price",
            "changeratio": "change_percent",
            "change_percent": "change_percent",
        }
        em_sort = em_sort_map.get(sort_by, "main_net_inflow")

        sina_sort_map = {
            "main_inflow": "r0_net",
            "main_net_inflow": "r0_net",
            "zjlr": "r0_net",
            "trade": "trade",
            "current_price": "trade",
            "changeratio": "changeratio",
            "change_percent": "changeratio",
        }
        sina_sort = sina_sort_map.get(sort_by, "r0_net")

        if sources is None:
            sources_to_try = await self._resolve_sources(
                allowed=["eastmoney", "sina"],
                default_order=["eastmoney", "sina"],
            )
        else:
            override: List[str] = []
            for s in sources or []:
                name = (s or "").strip().lower()
                if name in ("eastmoney", "sina") and name not in override:
                    override.append(name)
            if not override:
                raise ValueError("sources 不能为空")
            sources_to_try = await self._resolve_sources(allowed=override, default_order=override)

        last_error: Optional[Exception] = None
        for source in sources_to_try:
            breaker = self._get_breaker(source)
            if not breaker.can_execute():
                logger.debug(f"数据源 {source} 处于熔断状态，跳过")
                continue

            try:
                client = self._get_client(source)

                if source == "eastmoney":
                    method = getattr(client, "get_money_flow_rank", None)
                    if not method:
                        logger.debug(f"数据源 {source} 不支持方法 get_money_flow_rank")
                        continue
                    rows = await method(sort_by=em_sort, order=order, limit=int(limit))
                elif source == "sina":
                    method = getattr(client, "get_stock_money_rank", None)
                    if not method:
                        logger.debug(f"数据源 {source} 不支持方法 get_stock_money_rank")
                        continue
                    rows = await method(limit=int(limit), sort=sina_sort, order=order)
                else:
                    continue

                if not rows:
                    raise ValueError(f"数据源 {source}.get_stock_money_rank 返回为空")

                breaker.record_success()
                return rows

            except Exception as e:
                breaker.record_failure()
                last_error = e
                logger.warning(f"数据源 {source}.get_stock_money_rank 调用失败: {e}")

        if last_error:
            raise last_error
        raise RuntimeError("所有数据源都失败：get_stock_money_rank")

    async def get_volume_ratio_rank(self, min_ratio: float = 2.0, limit: int = 50) -> List[Dict[str, Any]]:
        """获取量比排名（默认东财）。"""
        sources = await self._resolve_sources(allowed=["eastmoney"], default_order=["eastmoney"])
        return await self.execute_with_failover(
            "get_volume_ratio_rank",
            float(min_ratio),
            int(limit),
            sources=sources,
        )

    async def get_limit_up_stocks(self) -> List[Dict[str, Any]]:
        """获取涨停股（默认东财）。"""
        sources = await self._resolve_sources(allowed=["eastmoney"], default_order=["eastmoney"])
        return await self.execute_with_failover("get_limit_up_stocks", sources=sources)

    async def get_limit_down_stocks(self) -> List[Dict[str, Any]]:
        """获取跌停股（默认东财）。"""
        sources = await self._resolve_sources(allowed=["eastmoney"], default_order=["eastmoney"])
        return await self.execute_with_failover("get_limit_down_stocks", sources=sources)

    async def get_north_flow(self, days: int = 30) -> Dict[str, Any]:
        """获取北向资金（默认东财）。"""
        sources = await self._resolve_sources(allowed=["eastmoney"], default_order=["eastmoney"])
        return await self.execute_with_failover(
            "get_north_flow",
            int(days),
            sources=sources,
        )

    async def get_bk_dict(self, bk_type: str) -> Any:
        """获取板块字典（默认东财）。"""
        sources = await self._resolve_sources(allowed=["eastmoney"], default_order=["eastmoney"])
        return await self.execute_with_failover(
            "get_bk_dict",
            bk_type,
            sources=sources,
        )

    async def get_stock_research_reports(self, stock_code: str, limit: int = 20) -> List[Dict[str, Any]]:
        """获取股票研究报告（默认东财）。"""
        sources = await self._resolve_sources(allowed=["eastmoney"], default_order=["eastmoney"])
        return await self.execute_with_failover(
            "get_stock_research_reports",
            stock_code,
            int(limit),
            sources=sources,
        )

    async def get_stock_notices(self, stock_code: str, limit: int = 20) -> List[Dict[str, Any]]:
        """获取股票公告（默认东财）。"""
        sources = await self._resolve_sources(allowed=["eastmoney"], default_order=["eastmoney"])
        return await self.execute_with_failover(
            "get_stock_notices",
            stock_code,
            int(limit),
            sources=sources,
        )

    async def get_market_indices(self, index_codes: List[str]) -> List[Any]:
        """获取主要指数行情（默认新浪）。"""
        sources = await self._resolve_sources(allowed=["sina"], default_order=["sina"])
        return await self.execute_with_failover(
            "get_market_indices",
            index_codes,
            sources=sources,
        )

    async def get_a_spot_statistics(self) -> Dict[str, Any]:
        """获取A股快照统计（东财优先，新浪兜底）。"""

        def _validate_stats(resp: Any) -> bool:
            return isinstance(resp, dict) and bool(resp.get("total_amount_yi", None) is not None)

        if not self._initialized:
            await self.initialize()

        # 强制东财优先：与 MarketService.get_market_overview 的历史行为保持一致。
        sources: List[str] = []
        for name in ("eastmoney", "sina"):
            if self._has_db_config and name in self._disabled_sources:
                continue
            sources.append(name)

        return await self.execute_with_failover(
            "get_a_spot_statistics",
            sources=sources,
            validate=_validate_stats,
        )

    async def get_interactive_qa(self, keyword: str, page: int = 1, page_size: int = 20) -> Dict[str, Any]:
        """获取投资者互动问答（默认东财）。"""
        sources = await self._resolve_sources(allowed=["eastmoney"], default_order=["eastmoney"])
        return await self.execute_with_failover(
            "get_interactive_qa",
            keyword,
            int(page),
            int(page_size),
            sources=sources,
        )

    async def get_live_news(self, limit: int = 30) -> List[Any]:
        """获取新浪 7x24 快讯（用于资讯兜底）。"""
        sources = await self._resolve_sources(allowed=["sina"], default_order=["sina"])
        return await self.execute_with_failover(
            "get_live_news",
            int(limit),
            sources=sources,
        )

    async def get_global_indexes(self) -> Any:
        """获取全球指数（默认新浪）。"""
        sources = await self._resolve_sources(allowed=["sina"], default_order=["sina"])
        return await self.execute_with_failover("get_global_indexes", sources=sources)

    async def get_hot_topics(self, size: int = 20) -> List[Dict[str, Any]]:
        """获取热门话题（默认东财）。"""
        sources = await self._resolve_sources(allowed=["eastmoney"], default_order=["eastmoney"])
        return await self.execute_with_failover(
            "get_hot_topics",
            int(size),
            sources=sources,
        )

    async def get_hot_events(self, size: int = 20) -> List[Dict[str, Any]]:
        """获取热门事件（默认东财）。"""
        sources = await self._resolve_sources(allowed=["eastmoney"], default_order=["eastmoney"])
        return await self.execute_with_failover(
            "get_hot_events",
            int(size),
            sources=sources,
        )

    async def get_invest_calendar(self, year_month: str) -> List[Dict[str, Any]]:
        """获取投资日历（默认东财）。"""
        sources = await self._resolve_sources(allowed=["eastmoney"], default_order=["eastmoney"])
        return await self.execute_with_failover(
            "get_invest_calendar",
            year_month,
            sources=sources,
        )

    async def get_money_flow_rank(
        self,
        sort_by: str = "main_net_inflow",
        order: str = "desc",
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """获取资金流向排名（默认东财）。"""
        sources = await self._resolve_sources(allowed=["eastmoney"], default_order=["eastmoney"])
        return await self.execute_with_failover(
            "get_money_flow_rank",
            sort_by,
            order,
            int(limit),
            sources=sources,
        )

    async def get_hot_strategies(self) -> List[Dict[str, Any]]:
        """获取热门选股策略（默认东财）。"""
        sources = await self._resolve_sources(allowed=["eastmoney"], default_order=["eastmoney"])
        return await self.execute_with_failover("get_hot_strategies", sources=sources)

    async def search_concept(self, keyword: str) -> List[Dict[str, Any]]:
        """搜索概念板块（默认东财）。"""
        sources = await self._resolve_sources(allowed=["eastmoney"], default_order=["eastmoney"])
        return await self.execute_with_failover(
            "search_concept",
            keyword,
            sources=sources,
        )

    async def search_industry(self, keyword: str) -> List[Dict[str, Any]]:
        """搜索行业板块（默认东财）。"""
        sources = await self._resolve_sources(allowed=["eastmoney"], default_order=["eastmoney"])
        return await self.execute_with_failover(
            "search_industry",
            keyword,
            sources=sources,
        )

    # ============ 管理方法 ============

    def get_all_status(self) -> List[Dict[str, Any]]:
        """获取所有数据源状态"""
        result = []
        for source in self._priority_order:
            breaker = self._breakers.get(source)
            if breaker:
                status = breaker.to_dict()
                status["priority"] = self._priority_order.index(source)
                result.append(status)
        return result

    def get_status(self, source: str) -> Optional[Dict[str, Any]]:
        """获取指定数据源状态"""
        breaker = self._breakers.get(source)
        if breaker:
            return breaker.to_dict()
        return None

    def reset_breaker(self, source: str) -> bool:
        """重置指定数据源的熔断器"""
        breaker = self._breakers.get(source)
        if breaker:
            breaker.reset()
            return True
        return False

    def set_priority(self, priority: List[str]) -> None:
        """设置数据源优先级"""
        self._priority_order = priority
        logger.info(f"更新数据源优先级: {priority}")


# 全局单例
_manager: Optional[DataSourceManager] = None


def get_datasource_manager() -> DataSourceManager:
    """获取数据源管理器单例"""
    global _manager
    if _manager is None:
        _manager = DataSourceManager()
    return _manager
