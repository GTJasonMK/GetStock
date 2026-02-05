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

            # 只要表里有配置，就视为“存在显式配置”。但对某个能力而言：
            # - 若该能力允许的数据源在 DB 中完全未出现，则视为“未配置”，回退到方法级默认顺序；
            # - 若已出现但被禁用，则必须尊重禁用，不得回退绕过。
            self._has_db_config = bool(all_configs)
            self._configured_sources = {c.source_name for c in all_configs}
            self._disabled_sources = {c.source_name for c in all_configs if not c.enabled}

            if not all_configs:
                # 数据库中未配置任何数据源：回退到默认优先级（保持与“未配置”场景一致）
                self._priority_order = self.DEFAULT_PRIORITY.copy()
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
            if source == "sina":
                from app.datasources.sina import SinaClient
                self._clients[source] = SinaClient()
            elif source == "eastmoney":
                from app.datasources.eastmoney import EastMoneyClient
                self._clients[source] = EastMoneyClient()
            elif source == "tencent":
                from app.datasources.tencent import TencentClient
                self._clients[source] = TencentClient()
            elif source == "tushare":
                from app.datasources.tushare import TushareClient
                self._clients[source] = TushareClient()
            else:
                raise ValueError(f"未知数据源: {source}")

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
            breaker = self._breakers.get(source)
            if not breaker:
                continue

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
