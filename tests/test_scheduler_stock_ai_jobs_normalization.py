import pytest
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import delete

from app.database import async_session_maker
from app.models.stock import FollowedStock
from app.tasks import scheduler as scheduler_module


@pytest.mark.asyncio
async def test_sync_stock_ai_jobs_uses_normalized_job_id(monkeypatch):
    monkeypatch.setattr(scheduler_module, "_scheduler_lock_acquired", True)
    scheduler_module.scheduler.remove_all_jobs()

    async with async_session_maker() as db:
        await db.execute(delete(FollowedStock))
        db.add(FollowedStock(stock_code="SH600000", stock_name="Test", cron_expression="0 15 * * 1-5"))
        await db.commit()

    await scheduler_module.sync_stock_ai_jobs()

    assert scheduler_module.scheduler.get_job("stock_ai_sh600000") is not None
    assert scheduler_module.scheduler.get_job("stock_ai_SH600000") is None

    scheduler_module.scheduler.remove_all_jobs()


@pytest.mark.asyncio
async def test_sync_stock_ai_jobs_removes_job_when_cron_invalid(monkeypatch):
    monkeypatch.setattr(scheduler_module, "_scheduler_lock_acquired", True)
    scheduler_module.scheduler.remove_all_jobs()

    async with async_session_maker() as db:
        await db.execute(delete(FollowedStock))
        db.add(FollowedStock(stock_code="sh600001", stock_name="Test", cron_expression="bad-cron"))
        await db.commit()

    scheduler_module.scheduler.add_job(
        lambda: None,
        IntervalTrigger(minutes=1),
        id="stock_ai_sh600001",
        replace_existing=True,
    )
    assert scheduler_module.scheduler.get_job("stock_ai_sh600001") is not None

    await scheduler_module.sync_stock_ai_jobs()
    assert scheduler_module.scheduler.get_job("stock_ai_sh600001") is None

    scheduler_module.scheduler.remove_all_jobs()

