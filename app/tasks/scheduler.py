# Scheduler 定时任务
"""
APScheduler 定时任务配置 - 门面模块（保持历史导入路径不变）

模块拆分：
- `app/tasks/scheduler_core.py`：调度器实例 + Cron 解析 + 通用任务管理 API；
- `app/tasks/scheduler_jobs.py`：业务任务实现（行情刷新/AI 分析/周报/同步任务等）。

本模块职责：
- 作为“对外稳定 API”的门面：外部仍可 `from app.tasks.scheduler import ...`
- 负责默认任务装配（`init_scheduler`）与应用生命周期启动/关闭（`startup_scheduler/shutdown_scheduler`）
- 保留测试依赖的模块级状态（例如 `_alert_once_state`、`_scheduler_lock_acquired`）
"""

from __future__ import annotations

from app.tasks import scheduler_core as _core
from app.tasks import scheduler_jobs as _jobs
from app.utils.helpers import is_trading_time  # 供测试 monkeypatch（必须存在同名属性）

# 固定 logger 名称，便于 caplog 捕获与排障
logger = _core.logger

# ============ 对外导出：调度器核心能力 ============

scheduler = _core.scheduler
build_cron_trigger = _core.build_cron_trigger

add_job = _core.add_job
remove_job = _core.remove_job
pause_job = _core.pause_job
resume_job = _core.resume_job
get_jobs = _core.get_jobs
get_job = _core.get_job
run_job_now = _core.run_job_now


# ============ 对外导出：业务任务 wrapper ============


async def refresh_daily_data() -> None:
    """每日数据刷新（业务任务 wrapper）"""
    await _jobs.refresh_daily_data_task(logger=logger)


async def refresh_realtime_data() -> None:
    """交易时段实时刷新（业务任务 wrapper）"""
    await _jobs.refresh_realtime_data_task(
        logger=logger,
        is_trading_time_fn=is_trading_time,
        alert_once_state=_alert_once_state,
    )


async def run_ai_stock_analysis(stock_code: str, prompt_template: str = None):
    """运行AI股票分析任务（业务任务 wrapper）"""
    await _jobs.run_ai_stock_analysis_task(stock_code, prompt_template, logger=logger)


async def run_daily_ai_analysis() -> None:
    """每日AI分析（业务任务 wrapper）"""
    await _jobs.run_daily_ai_analysis_task(logger=logger, scheduler=scheduler)


async def run_weekly_summary() -> None:
    """每周市场总结（业务任务 wrapper）"""
    await _jobs.run_weekly_summary_task(logger=logger)


def _schedule_ai_analysis_no_check(stock_code: str, cron_expression: str, prompt_template: str = None) -> str | None:
    """内部调度 helper：不做 leader 判断（供同步任务使用）"""
    return _jobs.schedule_ai_analysis_impl(
        scheduler=scheduler,
        logger=logger,
        build_cron_trigger_fn=build_cron_trigger,
        run_ai_stock_analysis_fn=run_ai_stock_analysis,
        stock_code=stock_code,
        cron_expression=cron_expression,
        prompt_template=prompt_template,
    )


def schedule_ai_analysis(stock_code: str, cron_expression: str, prompt_template: str = None) -> str | None:
    """安排AI分析定时任务（对外 API，带 leader 判断）"""
    if not is_scheduler_leader():
        logger.warning("当前进程未启用 scheduler，无法创建AI分析任务（请确保命中 leader 或使用单 worker）")
        return None
    return _schedule_ai_analysis_no_check(stock_code, cron_expression, prompt_template)


def _schedule_stock_ai_analysis_no_check(stock_code: str, cron_expression: str) -> str | None:
    """内部调度 helper：不做 leader 判断（供同步任务使用）"""
    return _jobs.schedule_stock_ai_analysis_impl(
        scheduler=scheduler,
        logger=logger,
        build_cron_trigger_fn=build_cron_trigger,
        run_ai_stock_analysis_fn=run_ai_stock_analysis,
        stock_code=stock_code,
        cron_expression=cron_expression,
    )


def schedule_stock_ai_analysis(stock_code: str, cron_expression: str) -> str | None:
    """安排股票AI分析定时任务（对外 API，带 leader 判断）"""
    if not is_scheduler_leader():
        logger.warning("当前进程未启用 scheduler，无法创建股票AI分析任务（将由 leader 同步任务收敛）")
        return None
    return _schedule_stock_ai_analysis_no_check(stock_code, cron_expression)


async def sync_stock_ai_jobs() -> None:
    """同步 per-stock AI 分析任务（业务任务 wrapper）"""
    await _jobs.sync_stock_ai_jobs_task(
        logger=logger,
        scheduler=scheduler,
        is_scheduler_leader_fn=is_scheduler_leader,
        schedule_stock_ai_analysis_fn=_schedule_stock_ai_analysis_no_check,
        remove_job_fn=remove_job,
    )


async def restore_stock_ai_jobs() -> None:
    """兼容旧接口：从数据库恢复 per-stock AI 分析任务"""
    await sync_stock_ai_jobs()


# ============ 兼容性状态（测试/业务会读写） ============

# 价格提醒“每日一次”去重状态（进程内内存）
_alert_once_state: dict[str, set[str]] = {}

# 兼容：测试会 monkeypatch 该变量以绕过 leader 判断
_scheduler_lock_acquired: bool = False


def is_scheduler_leader() -> bool:
    """当前进程是否为 scheduler leader（支持测试通过 monkeypatch 强制开启）"""
    return bool(_scheduler_lock_acquired) or _core.is_scheduler_leader()


def init_scheduler() -> None:
    """初始化调度器 - 添加默认定时任务"""
    # 每日盘前数据刷新 (9:00)
    add_job(
        refresh_daily_data,
        trigger="cron",
        job_id="daily_refresh",
        name="每日数据刷新",
        hour=9,
        minute=0,
        day_of_week="mon-fri",
    )

    # 交易时段实时刷新 (每5分钟, 9:30-15:00)
    add_job(
        refresh_realtime_data,
        trigger="cron",
        job_id="realtime_refresh",
        name="实时数据刷新",
        minute="*/5",
        hour="9-11,13-15",
        day_of_week="mon-fri",
    )

    # 每日收盘后AI分析 (15:30) - 只分析未配置独立 cron 的股票
    add_job(
        run_daily_ai_analysis,
        trigger="cron",
        job_id="daily_ai_analysis",
        name="每日AI分析",
        hour=15,
        minute=30,
        day_of_week="mon-fri",
    )

    # 每周末市场总结 (周六10:00)
    add_job(
        run_weekly_summary,
        trigger="cron",
        job_id="weekly_summary",
        name="每周市场总结",
        hour=10,
        minute=0,
        day_of_week="sat",
    )

    # 同步自选股 per-stock AI 分析任务（解决多进程/重启导致的任务丢失与不一致）
    add_job(
        sync_stock_ai_jobs,
        trigger="interval",
        job_id="sync_stock_ai_jobs",
        name="同步自选股AI任务",
        minutes=1,
    )

    logger.info("定时任务初始化完成")


async def startup_scheduler() -> bool:
    """
    应用启动时初始化并启动 scheduler

    - 多 worker 场景下通过文件锁选主：只有 leader 进程启动 scheduler 并执行任务
    - 同步 per-stock AI 任务，确保重启后不丢任务、且 cron 修改能收敛生效
    """
    if scheduler.running:
        return True

    acquired = _core.try_acquire_scheduler_lock()
    global _scheduler_lock_acquired
    _scheduler_lock_acquired = acquired
    if not acquired:
        return False

    init_scheduler()
    await sync_stock_ai_jobs()
    start_scheduler()
    return scheduler.running


def start_scheduler() -> None:
    """启动调度器（仅 leader 进程）"""
    _core.start_scheduler()
    global _scheduler_lock_acquired
    _scheduler_lock_acquired = _core.is_scheduler_leader()


def shutdown_scheduler() -> None:
    """关闭调度器"""
    _core.shutdown_scheduler()
    global _scheduler_lock_acquired
    _scheduler_lock_acquired = False
