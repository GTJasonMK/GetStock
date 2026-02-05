# 数据库连接模块
"""
SQLAlchemy 异步数据库连接配置
"""

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings


settings = get_settings()

# 创建异步引擎
engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    future=True,
)

# 创建异步会话工厂
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    """SQLAlchemy 基类"""
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """获取数据库会话依赖"""
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """初始化数据库表"""
    # 重要：确保所有模型都被导入，才能被 Base.metadata.create_all() 正确创建
    # 项目中部分 service/router 采用延迟 import，直接 create_all 可能遗漏新表。
    try:
        import app.models  # noqa: F401
    except Exception:
        # 导入失败不应阻塞启动（后续访问相关表时会暴露问题）
        pass
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db():
    """关闭数据库连接"""
    await engine.dispose()
