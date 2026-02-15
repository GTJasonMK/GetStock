"""
pytest 全局配置（避免误操作真实数据）：

- 默认 app/config.py 的数据库指向 ./data/stock.db
- 多个测试用例会执行 delete(...) 清库

因此在测试会话启动前强制切换到临时 sqlite 数据库，避免误清空真实数据文件。
"""

import os
import tempfile
import uuid
from pathlib import Path

import asyncio
from contextlib import suppress

import pytest_asyncio


# 测试默认不启动 scheduler，避免后台线程/任务影响用例稳定性
os.environ.setdefault("ENABLE_SCHEDULER", "false")

# 测试用例依赖 monkeypatch/假数据源时，缓存可能导致“命中旧结果”而绕过 patch；
# 因此每个用例前后清空内存缓存，保证可重复、可预测。
@pytest_asyncio.fixture(autouse=True)
async def _clear_memory_cache():
    from app.utils.cache import cache

    await cache.clear()
    yield
    await cache.clear()


@pytest_asyncio.fixture(autouse=True)
async def _reset_datasource_config_and_manager():
    """
    测试隔离：
    - datasource_config 会影响 DataSourceManager 的优先级/启用状态；
    - 若不清理，前序用例可能残留配置，导致后续用例意外走到真实网络数据源。

    这里在每个用例前清空 DataSourceConfig，并重置全局 DataSourceManager 单例。
    """
    from sqlalchemy import delete

    from app.database import async_session_maker
    from app.models.settings import DataSourceConfig
    import app.datasources.manager as manager_module

    async with async_session_maker() as db:
        await db.execute(delete(DataSourceConfig))
        await db.commit()

    manager_module._manager = None
    yield


# 未显式指定 DATABASE_URL 时，强制使用临时数据库文件
if not os.environ.get("DATABASE_URL"):
    db_path = Path(tempfile.gettempdir()) / f"recon-pytest-{uuid.uuid4().hex}.db"
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path}"


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _event_loop_wakeup():
    """
    让事件循环保持“周期性唤醒”，避免在部分受限环境下出现：
    - asyncio 自唤醒通道（self-pipe）无法写入，导致 call_soon_threadsafe 无法唤醒 loop；
    - aiosqlite / SQLAlchemy async 等依赖线程回调的 await 永久阻塞。
    """

    async def _ticker():
        while True:
            await asyncio.sleep(0.01)

    task = asyncio.create_task(_ticker())
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


@pytest_asyncio.fixture(autouse=True)
async def _event_loop_wakeup_function():
    """同上，但覆盖 function-scoped event loop（pytest-asyncio 默认每个用例独立 loop）。"""

    async def _ticker():
        while True:
            await asyncio.sleep(0.01)

    task = asyncio.create_task(_ticker())
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _init_test_db(_event_loop_wakeup):
    """初始化测试数据库表结构（避免新建临时 DB 时出现 no such table）"""
    from app.database import init_db

    await init_db()
    yield
