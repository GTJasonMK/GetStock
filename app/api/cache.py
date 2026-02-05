# 缓存管理API
"""
缓存状态查看和管理
"""

from pydantic import BaseModel
from fastapi import APIRouter

from app.utils.cache import cache
from app.schemas.common import Response

router = APIRouter(prefix="/cache", tags=["缓存管理"])


class CacheStats(BaseModel):
    """缓存统计信息"""
    total: int
    active: int
    expired: int


@router.get("/stats", response_model=Response[CacheStats])
async def get_cache_stats():
    """
    获取缓存统计信息

    返回:
    - total: 总缓存条目数
    - active: 有效缓存条目数
    - expired: 已过期缓存条目数
    """
    stats = cache.stats()
    return Response(data=CacheStats(
        total=stats.get("total", 0),
        active=stats.get("active", 0),
        expired=stats.get("expired", 0),
    ))


@router.post("/clear", response_model=Response)
async def clear_cache():
    """
    清空所有缓存
    """
    await cache.clear()
    return Response(message="缓存已清空")


@router.post("/clear-expired", response_model=Response)
async def clear_expired_cache():
    """
    清理已过期的缓存条目
    """
    await cache.clear_expired()
    return Response(message="过期缓存已清理")
