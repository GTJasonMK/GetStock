# Settings Service
"""
系统配置（Settings）服务：

- Settings 在产品语义上是“单例配置”，但数据库层未强制约束。
- 历史数据或并发初始化可能导致出现多行，从而让 scalar_one_or_none() 抛 MultipleResultsFound，造成核心链路 500。

本模块提供“可收敛”的读取/创建逻辑：
- 读取时始终 limit(1) + order_by，避免多行时崩溃；
- 创建时固定使用 id=1（主键约束天然保证单例），并在并发冲突时回退为重新读取。
"""

import logging

from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.settings import Settings

logger = logging.getLogger(__name__)


async def get_settings_singleton(db: AsyncSession, *, create: bool = True) -> Settings | None:
    """获取 Settings 单例（必要时创建）"""
    result = await db.execute(
        select(Settings)
        .order_by(Settings.updated_at.desc(), Settings.id.desc())
        .limit(1)
    )
    settings = result.scalar_one_or_none()

    if settings:
        # 仅在发现多行时记录告警，避免线上“静默选择”导致排障困难
        count_result = await db.execute(select(func.count(Settings.id)))
        count = int(count_result.scalar() or 0)
        if count > 1:
            logger.warning(f"检测到 Settings 表存在 {count} 行，当前使用 id={settings.id} 作为单例配置")
        return settings

    if not create:
        return None

    # 通过固定 id=1 的方式强制单例（并发时若已存在会触发 IntegrityError）
    settings = Settings(id=1)
    db.add(settings)
    try:
        await db.flush()
        return settings
    except IntegrityError:
        # 并发场景：另一事务已创建 id=1
        await db.rollback()
        result = await db.execute(
            select(Settings)
            .order_by(Settings.updated_at.desc(), Settings.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

