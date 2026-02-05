# Scheduler Core 调度器核心
"""
调度器核心模块（只做“调度器实例 + 通用管理能力”，不包含具体业务任务实现）。

目的：
- 降低 `app/tasks/scheduler.py` 的体积与认知负担；
- 将锁选主、Cron 解析、任务管理 API 等通用能力集中维护；
- 业务任务（行情刷新/AI 分析等）由 `jobs_*` 模块负责。

注意：
- 日志 logger 名称固定为 `app.tasks.scheduler`，保持与历史行为一致（便于排障与测试捕获日志）。
"""

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List, Callable

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.jobstores.memory import MemoryJobStore

# filelock 是可选依赖：用于多进程部署时的“调度器选主”，避免重复执行任务。
# 若缺失依赖，则自动禁用 scheduler（对交易/任务更安全），并提示用户安装依赖。
try:
    from filelock import FileLock, Timeout  # type: ignore
    _FILELOCK_AVAILABLE = True
except Exception:  # pragma: no cover - 通过单测 reload 场景覆盖
    FileLock = None  # type: ignore
    Timeout = None  # type: ignore
    _FILELOCK_AVAILABLE = False

from app.utils.helpers import get_market_timezone

logger = logging.getLogger("app.tasks.scheduler")


# 全局调度器（进程内单例）
scheduler = AsyncIOScheduler(
    jobstores={"default": MemoryJobStore()},
    job_defaults={
        "coalesce": True,  # 合并错过的执行
        "max_instances": 1,  # 同一任务最大并发实例
        "misfire_grace_time": 60,  # 错过执行的容忍时间
    },
    timezone=get_market_timezone(),
)


def build_cron_trigger(cron_expression: str) -> CronTrigger:
    """
    将 cron 表达式解析为 APScheduler CronTrigger（固定到市场时区）。

    支持：
    - 5 段：分 时 日 月 周（例如: "0 15 * * 1-5"）
    - 6 段：秒 分 时 日 月 周
    - 7 段：秒 分 时 日 月 周 年
    """
    expr = (cron_expression or "").strip()
    parts = [p for p in expr.split() if p]

    if len(parts) == 5:
        minute, hour, day, month, day_of_week = parts
        kwargs = {
            "minute": minute,
            "hour": hour,
            "day": day,
            "month": month,
            "day_of_week": day_of_week,
        }
    elif len(parts) == 6:
        second, minute, hour, day, month, day_of_week = parts
        kwargs = {
            "second": second,
            "minute": minute,
            "hour": hour,
            "day": day,
            "month": month,
            "day_of_week": day_of_week,
        }
    elif len(parts) == 7:
        second, minute, hour, day, month, day_of_week, year = parts
        kwargs = {
            "second": second,
            "minute": minute,
            "hour": hour,
            "day": day,
            "month": month,
            "day_of_week": day_of_week,
            "year": year,
        }
    else:
        raise ValueError(f"cron表达式段数错误: 期望5/6/7段，实际{len(parts)}段")

    return CronTrigger(timezone=get_market_timezone(), **kwargs)


# ============ 多进程调度器锁（避免多 worker 重复执行） ============

_scheduler_lock: Optional[Any] = None
_scheduler_lock_acquired: bool = False


def _is_scheduler_enabled() -> bool:
    """是否启用 scheduler（通过环境变量控制）"""
    value = os.environ.get("ENABLE_SCHEDULER", "true").strip().lower()
    return value not in {"0", "false", "no", "off"}


def _get_scheduler_lock_path() -> Path:
    """获取 scheduler 锁文件路径"""
    return Path(os.environ.get("SCHEDULER_LOCK_PATH", "./data/scheduler.lock"))


def is_scheduler_leader() -> bool:
    """当前进程是否为 scheduler leader（持有进程锁）"""
    return _scheduler_lock_acquired


def try_acquire_scheduler_lock() -> bool:
    """尝试获取 scheduler 进程锁（非阻塞）"""
    global _scheduler_lock, _scheduler_lock_acquired

    if _scheduler_lock_acquired:
        return True

    if not _is_scheduler_enabled():
        logger.info("定时任务调度器已禁用（ENABLE_SCHEDULER=false）")
        return False

    if not _FILELOCK_AVAILABLE:
        logger.warning("缺少依赖 filelock，已自动禁用定时任务调度器（避免多进程重复执行）。")
        logger.warning("请执行 `pip install -r requirements.txt` 安装依赖后再启用 ENABLE_SCHEDULER=true。")
        return False

    lock_path = _get_scheduler_lock_path()
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.error(f"创建 scheduler 锁目录失败: {lock_path.parent}, {e}")
        return False

    try:
        _scheduler_lock = FileLock(str(lock_path))
        _scheduler_lock.acquire(timeout=0)
        _scheduler_lock_acquired = True
        logger.info(f"已获取 scheduler 进程锁: {lock_path}")
        return True
    except Timeout:
        logger.warning(f"未获取到 scheduler 进程锁，跳过启动（可能是多 worker 部署）：{lock_path}")
        return False
    except Exception as e:
        logger.error(f"获取 scheduler 进程锁失败: {lock_path}, {e}")
        return False


def release_scheduler_lock() -> None:
    """释放 scheduler 进程锁"""
    global _scheduler_lock, _scheduler_lock_acquired
    if not _scheduler_lock_acquired or not _scheduler_lock:
        return
    try:
        _scheduler_lock.release()
        logger.info("已释放 scheduler 进程锁")
    except Exception as e:
        logger.warning(f"释放 scheduler 进程锁失败: {e}")
    finally:
        _scheduler_lock = None
        _scheduler_lock_acquired = False


def start_scheduler() -> None:
    """启动调度器（仅 leader 进程）"""
    if scheduler.running:
        return
    if not try_acquire_scheduler_lock():
        return
    scheduler.start()
    logger.info("定时任务调度器已启动")


def shutdown_scheduler() -> None:
    """关闭调度器并释放锁"""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("定时任务调度器已关闭")
    release_scheduler_lock()


# ============ 任务管理 API ============

def add_job(
    func: Callable,
    trigger: str,
    job_id: str,
    name: str = "",
    **trigger_args,
) -> Optional[str]:
    """
    添加定时任务
    trigger: "cron" 或 "interval"
    trigger_args: 触发器参数
        cron: hour, minute, day_of_week, etc.
        interval: seconds, minutes, hours, etc.
    """
    try:
        if trigger == "cron":
            # 默认绑定到市场时区，避免部署机本地时区导致错时
            trigger_args.setdefault("timezone", get_market_timezone())
            trigger_obj = CronTrigger(**trigger_args)
        elif trigger == "interval":
            trigger_obj = IntervalTrigger(**trigger_args)
        else:
            logger.error(f"不支持的触发器类型: {trigger}")
            return None

        job = scheduler.add_job(
            func,
            trigger_obj,
            id=job_id,
            name=name or job_id,
            replace_existing=True,
        )
        logger.info(f"添加定时任务: {job_id}")
        return job.id
    except Exception as e:
        logger.error(f"添加任务失败: {e}")
        return None


def remove_job(job_id: str) -> bool:
    """移除定时任务"""
    try:
        scheduler.remove_job(job_id)
        logger.info(f"移除定时任务: {job_id}")
        return True
    except Exception as e:
        logger.error(f"移除任务失败: {e}")
        return False


def pause_job(job_id: str) -> bool:
    """暂停定时任务"""
    try:
        scheduler.pause_job(job_id)
        logger.info(f"暂停定时任务: {job_id}")
        return True
    except Exception as e:
        logger.error(f"暂停任务失败: {e}")
        return False


def resume_job(job_id: str) -> bool:
    """恢复定时任务"""
    try:
        scheduler.resume_job(job_id)
        logger.info(f"恢复定时任务: {job_id}")
        return True
    except Exception as e:
        logger.error(f"恢复任务失败: {e}")
        return False


def get_jobs() -> List[Dict[str, Any]]:
    """获取所有定时任务"""
    jobs = []
    for job in scheduler.get_jobs():
        jobs.append({
            "id": job.id,
            "name": job.name,
            "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
            "trigger": str(job.trigger),
            "pending": job.pending,
        })
    return jobs


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    """获取指定任务信息"""
    job = scheduler.get_job(job_id)
    if not job:
        return None
    return {
        "id": job.id,
        "name": job.name,
        "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
        "trigger": str(job.trigger),
        "pending": job.pending,
    }


def run_job_now(job_id: str) -> bool:
    """立即执行任务"""
    try:
        job = scheduler.get_job(job_id)
        if job:
            # APScheduler 对 naive datetime 的解释依赖部署机本地时区，可能导致“立即执行”被错误延后。
            # 这里固定使用市场时区，确保行为可预期。
            job.modify(next_run_time=datetime.now(get_market_timezone()))
            logger.info(f"立即执行任务: {job_id}")
            return True
        return False
    except Exception as e:
        logger.error(f"执行任务失败: {e}")
        return False
