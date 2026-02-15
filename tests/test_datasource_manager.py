import pytest
from sqlalchemy import delete

from app.database import async_session_maker
from app.datasources.manager import DataSourceManager
from app.models.settings import DataSourceConfig
from app.schemas.stock import KLineResponse, KLineData


@pytest.mark.asyncio
async def test_datasource_manager_initialize_refreshes_db_config():
    async with async_session_maker() as db:
        await db.execute(delete(DataSourceConfig))
        db.add(DataSourceConfig(
            source_name="tencent",
            enabled=True,
            priority=0,
            failure_threshold=2,
            cooldown_seconds=60,
        ))
        db.add(DataSourceConfig(
            source_name="sina",
            enabled=True,
            priority=1,
            failure_threshold=3,
            cooldown_seconds=120,
        ))
        await db.commit()

        manager = DataSourceManager()
        await manager.initialize()
        assert manager._priority_order == manager.DEFAULT_PRIORITY

        await manager.initialize(db)
        assert manager._priority_order == ["tencent", "sina"]


@pytest.mark.asyncio
async def test_get_kline_respects_priority_order_from_db_config(monkeypatch):
    from app.datasources import tencent as tencent_module
    from app.datasources import eastmoney as eastmoney_module

    called = []

    class FakeTencentClient:
        async def get_kline(
            self,
            stock_code: str,
            period: str = "day",
            count: int = 100,
            adjust: str = "qfq",
        ):
            called.append("tencent")
            return KLineResponse(
                stock_code=stock_code,
                stock_name="tencent",
                period=period,
                data=[
                    KLineData(
                        date="2026-01-26",
                        open=10.0,
                        close=10.1,
                        high=10.2,
                        low=9.9,
                        volume=123,
                        amount=456.0,
                        change_percent=1.0,
                    )
                ],
            )

        async def close(self):
            return None

    class FakeEastMoneyClient:
        async def get_kline(
            self,
            stock_code: str,
            period: str = "day",
            count: int = 100,
            adjust: str = "qfq",
        ):
            called.append("eastmoney")
            return KLineResponse(
                stock_code=stock_code,
                stock_name="eastmoney",
                period=period,
                data=[
                    KLineData(
                        date="2026-01-26",
                        open=10.0,
                        close=10.1,
                        high=10.2,
                        low=9.9,
                        volume=123,
                        amount=456.0,
                        change_percent=1.0,
                    )
                ],
            )

        async def close(self):
            return None

    monkeypatch.setattr(tencent_module, "TencentClient", FakeTencentClient)
    monkeypatch.setattr(eastmoney_module, "EastMoneyClient", FakeEastMoneyClient)

    async with async_session_maker() as db:
        await db.execute(delete(DataSourceConfig))
        db.add(DataSourceConfig(
            source_name="eastmoney",
            enabled=True,
            priority=0,
            failure_threshold=3,
            cooldown_seconds=60,
        ))
        db.add(DataSourceConfig(
            source_name="tencent",
            enabled=True,
            priority=1,
            failure_threshold=3,
            cooldown_seconds=60,
        ))
        await db.commit()

        manager = DataSourceManager()
        await manager.initialize(db)

        resp = await manager.get_kline("sh600000", period="day", count=1)
        assert resp.stock_name == "eastmoney"
        assert called == ["eastmoney"]


@pytest.mark.asyncio
async def test_execute_with_failover_respects_explicit_empty_sources(monkeypatch):
    """
    回归：sources=[] 代表显式“不尝试任何数据源”，不能回退到默认优先级。
    这类隐蔽 bug 会导致“能力白名单过滤失效/禁用配置不生效”。
    """
    from app.datasources import tencent as tencent_module

    called = []

    class FakeTencentClient:
        async def get_kline(
            self,
            stock_code: str,
            period: str = "day",
            count: int = 100,
            adjust: str = "qfq",
        ):
            called.append("tencent")
            return "should-not-be-called"

        async def close(self):
            return None

    monkeypatch.setattr(tencent_module, "TencentClient", FakeTencentClient)

    manager = DataSourceManager()
    await manager.initialize()
    manager._priority_order = ["tencent"]

    with pytest.raises(Exception):
        await manager.execute_with_failover(
            "get_kline",
            "sh600000",
            period="day",
            count=1,
            sources=[],
        )

    assert called == []


@pytest.mark.asyncio
async def test_all_disabled_datasource_config_does_not_fallback_to_default_priority():
    """
    回归：datasource_config 全部禁用时，不能被当作“未配置”从而回退默认优先级继续取数。
    这会让运维侧的禁用意图被静默绕过。
    """
    async with async_session_maker() as db:
        await db.execute(delete(DataSourceConfig))
        db.add(DataSourceConfig(
            source_name="sina",
            enabled=False,
            priority=0,
            failure_threshold=3,
            cooldown_seconds=60,
        ))
        await db.commit()

        manager = DataSourceManager()
        await manager.initialize(db)

        assert manager._has_db_config is True
        assert manager._priority_order == []

        resolved = await manager._resolve_sources(
            allowed=["sina"],
            default_order=["sina"],
        )
        assert resolved == []


@pytest.mark.asyncio
async def test_partial_db_config_does_not_disable_unconfigured_capabilities():
    """
    回归：DB 里只配置了部分数据源（例如仅 sina）时，不能把其它能力允许的数据源（如 K 线允许的 tencent/eastmoney）
    误判为“已配置但不可用”，从而过滤成空列表导致“明明可以取数却完全不尝试”。
    """
    async with async_session_maker() as db:
        await db.execute(delete(DataSourceConfig))
        db.add(DataSourceConfig(
            source_name="sina",
            enabled=True,
            priority=0,
            failure_threshold=3,
            cooldown_seconds=60,
        ))
        await db.commit()

        manager = DataSourceManager()
        await manager.initialize(db)

        resolved = await manager._resolve_sources(
            allowed=["tencent", "eastmoney"],
            default_order=["tencent", "eastmoney"],
        )
        assert resolved == ["tencent", "eastmoney"]
