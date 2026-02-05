# Cache Module
"""
简单的内存缓存系统，支持TTL过期
"""

import asyncio
import hashlib
import inspect
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Callable, Optional
from functools import wraps

logger = logging.getLogger(__name__)


class CacheEntry:
    """缓存条目"""
    def __init__(self, value: Any, expire_at: datetime):
        self.value = value
        self.expire_at = expire_at

    def is_expired(self) -> bool:
        return datetime.now() > self.expire_at


class MemoryCache:
    """内存缓存"""

    def __init__(self):
        self._cache: dict[str, CacheEntry] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[Any]:
        """获取缓存"""
        async with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            if entry.is_expired():
                del self._cache[key]
                return None
            return entry.value

    async def set(self, key: str, value: Any, ttl_seconds: int = 60):
        """设置缓存"""
        async with self._lock:
            expire_at = datetime.now() + timedelta(seconds=ttl_seconds)
            self._cache[key] = CacheEntry(value, expire_at)

    async def delete(self, key: str):
        """删除缓存"""
        async with self._lock:
            self._cache.pop(key, None)

    async def clear(self):
        """清空所有缓存"""
        async with self._lock:
            self._cache.clear()

    async def clear_expired(self):
        """清理过期缓存"""
        async with self._lock:
            expired_keys = [
                key for key, entry in self._cache.items()
                if entry.is_expired()
            ]
            for key in expired_keys:
                del self._cache[key]
            if expired_keys:
                logger.debug(f"清理了 {len(expired_keys)} 个过期缓存")

    def stats(self) -> dict:
        """缓存统计"""
        total = len(self._cache)
        expired = sum(1 for entry in self._cache.values() if entry.is_expired())
        return {
            "total": total,
            "active": total - expired,
            "expired": expired,
        }


# 全局缓存实例
cache = MemoryCache()


# 缓存TTL配置（秒）
class CacheTTL:
    """缓存过期时间配置"""
    REALTIME_QUOTE = 10      # 实时行情 10秒
    MINUTE_DATA = 30         # 分时数据 30秒
    STOCK_LIST = 300         # 股票列表 5分钟
    INDUSTRY_RANK = 60       # 行业排名 1分钟
    CONCEPT_RANK = 60        # 概念排名 1分钟
    MONEY_FLOW = 60          # 资金流向 1分钟
    LIMIT_STATS = 30         # 涨跌停统计 30秒
    NORTH_FLOW = 60          # 北向资金 1分钟
    KLINE = 300              # K线数据 5分钟
    TECHNICAL = 60           # 技术分析 1分钟
    NEWS = 120               # 新闻 2分钟
    SETTINGS = 600           # 设置 10分钟
    CONCEPTS = 300           # 概念板块 5分钟
    HOT_STOCKS = 60          # 热门股票 1分钟
    HOT_TOPICS = 120         # 热门话题 2分钟
    GLOBAL_INDEX = 60        # 全球指数 1分钟


def make_cache_key(prefix: str, *args, **kwargs) -> str:
    """生成缓存键"""
    key_data = {
        "args": args,
        "kwargs": kwargs,
    }
    key_hash = hashlib.md5(json.dumps(key_data, sort_keys=True, default=str).encode()).hexdigest()[:8]
    return f"{prefix}:{key_hash}"


def cached(ttl_seconds: int, prefix: Optional[str] = None):
    """
    缓存装饰器

    用法:
        @cached(ttl_seconds=60, prefix="market")
        async def get_data():
            ...
    """
    def decorator(func: Callable):
        # 预先检查函数签名，判断是否为实例方法或类方法
        sig = inspect.signature(func)
        params = list(sig.parameters.keys())
        is_method = params and params[0] in ('self', 'cls')

        @wraps(func)
        async def wrapper(*args, **kwargs):
            # 生成缓存键
            cache_prefix = prefix or func.__name__
            # 如果是实例方法/类方法，跳过 self/cls 参数
            cache_args = args[1:] if is_method and args else args
            key = make_cache_key(cache_prefix, *cache_args, **kwargs)

            # 尝试获取缓存
            cached_value = await cache.get(key)
            if cached_value is not None:
                logger.debug(f"缓存命中: {key}")
                return cached_value

            # 执行函数
            result = await func(*args, **kwargs)

            # 存入缓存
            await cache.set(key, result, ttl_seconds)
            logger.debug(f"缓存写入: {key}")

            return result
        return wrapper
    return decorator
