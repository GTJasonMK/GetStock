# Scheduler Jobs 业务任务
"""
调度器业务任务实现（纯实现层）。

设计目标：
- **低耦合**：本模块不反向 import `app.tasks.scheduler`，避免隐式全局依赖；
- **高复用**：所有任务逻辑通过显式参数注入（logger/scheduler/状态/函数）；
- **易扩展**：新增任务只需新增纯函数 + 在门面层（`app/tasks/scheduler.py`） wiring。

兼容性说明：
- 对外 API/测试 monkeypatch 由门面层负责：tests 会 monkeypatch `app.tasks.scheduler.is_trading_time`、
  `app.tasks.scheduler._alert_once_state`、`app.tasks.scheduler._scheduler_lock_acquired` 等符号；
  门面层 wrapper 会把这些符号作为依赖注入到本模块，确保语义保持一致。
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, Callable, Awaitable, Any

from apscheduler.jobstores.base import JobLookupError

from app.utils.helpers import normalize_stock_code, get_market_timezone


def _normalize_cron_expression(expr: str) -> str:
    """规范化 cron 表达式（压缩空白）"""
    return " ".join((expr or "").split())


def _schedule_cron_job(
    *,
    scheduler: Any,
    logger: Any,
    build_cron_trigger_fn: Callable[[str], Any],
    job_id: str,
    job_name: str,
    func: Callable,
    args: list,
    cron_expression: str,
) -> Optional[str]:
    """
    统一的“cron job”调度实现：
    - 显式 remove→add，避免 APScheduler pending 任务在部分版本下出现重复视图
    """
    cron_expression = _normalize_cron_expression(cron_expression)
    try:
        try:
            scheduler.remove_job(job_id)
        except JobLookupError:
            pass

        trigger_obj = build_cron_trigger_fn(cron_expression)
        job = scheduler.add_job(
            func,
            trigger_obj,
            args=args,
            id=job_id,
            name=job_name or job_id,
            replace_existing=True,
        )
        logger.info(f"添加定时任务: {job_id}")
        return job.id
    except Exception as e:
        logger.error(f"添加定时任务失败: job_id={job_id}, cron={cron_expression}, err={e}")
        return None


def schedule_ai_analysis_impl(
    *,
    scheduler: Any,
    logger: Any,
    build_cron_trigger_fn: Callable[[str], Any],
    run_ai_stock_analysis_fn: Callable[..., Awaitable[Any]],
    stock_code: str,
    cron_expression: str,
    prompt_template: str | None,
) -> Optional[str]:
    """安排 AI 分析定时任务（不做 leader 判断，由门面层控制）"""
    normalized_code = normalize_stock_code(stock_code)
    if not normalized_code:
        logger.error(f"添加AI分析任务失败: stock_code 无效: {stock_code}")
        return None

    job_id = f"ai_analysis_{normalized_code}"
    return _schedule_cron_job(
        scheduler=scheduler,
        logger=logger,
        build_cron_trigger_fn=build_cron_trigger_fn,
        job_id=job_id,
        job_name=f"AI分析-{normalized_code}",
        func=run_ai_stock_analysis_fn,
        args=[normalized_code, prompt_template],
        cron_expression=cron_expression,
    )


def schedule_stock_ai_analysis_impl(
    *,
    scheduler: Any,
    logger: Any,
    build_cron_trigger_fn: Callable[[str], Any],
    run_ai_stock_analysis_fn: Callable[..., Awaitable[Any]],
    stock_code: str,
    cron_expression: str,
) -> Optional[str]:
    """安排股票 AI 分析定时任务（不做 leader 判断，由门面层控制）"""
    normalized_code = normalize_stock_code(stock_code)
    if not normalized_code:
        logger.warning(f"创建股票AI分析任务失败：stock_code 无效: {stock_code}")
        return None

    job_id = f"stock_ai_{normalized_code}"
    return _schedule_cron_job(
        scheduler=scheduler,
        logger=logger,
        build_cron_trigger_fn=build_cron_trigger_fn,
        job_id=job_id,
        job_name=f"股票AI分析-{normalized_code}",
        func=run_ai_stock_analysis_fn,
        args=[normalized_code],
        cron_expression=cron_expression,
    )


async def sync_stock_ai_jobs_task(
    *,
    logger: Any,
    scheduler: Any,
    is_scheduler_leader_fn: Callable[[], bool],
    schedule_stock_ai_analysis_fn: Callable[[str, str], Optional[str]],
    remove_job_fn: Callable[[str], bool],
) -> None:
    """
    同步 per-stock AI 分析任务（以数据库为准）

    目标：
    - 新增/更新：FollowedStock.cron_expression 非空的股票，确保对应 job 存在且 cron 生效
    - 清理：数据库中已取消 cron 的股票，移除对应 job，避免“看似取消但仍在跑”
    """
    if not is_scheduler_leader_fn():
        return

    from app.database import async_session_maker
    from sqlalchemy import select
    from app.models.stock import FollowedStock

    try:
        async with async_session_maker() as db:
            result = await db.execute(
                select(FollowedStock).where(
                    FollowedStock.cron_expression.isnot(None),
                    FollowedStock.cron_expression != "",
                )
            )
            stocks = result.scalars().all()

            upserted = 0
            desired_job_ids: set[str] = set()
            for stock in stocks:
                normalized_code = normalize_stock_code(stock.stock_code)
                if not normalized_code:
                    logger.warning(f"同步 per-stock AI 任务时发现无效 stock_code: {stock.stock_code}")
                    continue

                job_id = schedule_stock_ai_analysis_fn(normalized_code, stock.cron_expression or "")
                if not job_id:
                    logger.warning(
                        f"同步 per-stock AI 任务失败，将移除旧任务（若存在）: stock_code={normalized_code}, cron={stock.cron_expression}"
                    )
                    continue

                desired_job_ids.add(job_id)
                upserted += 1

            removed = 0
            for job in scheduler.get_jobs():
                if not job.id.startswith("stock_ai_"):
                    continue
                if job.id in desired_job_ids:
                    continue
                if remove_job_fn(job.id):
                    removed += 1

            if upserted or removed:
                logger.info(f"同步 per-stock AI 任务完成: upsert={upserted}, removed={removed}")
    except Exception as e:
        logger.error(f"同步 per-stock AI 任务失败: {e}")


async def refresh_daily_data_task(*, logger: Any) -> None:
    """
    每日数据刷新
    - 刷新股票基础信息表
    - 刷新指数数据
    """
    logger.info("开始每日数据刷新...")

    from app.database import async_session_maker
    from sqlalchemy import select
    from app.models.market import StockBasic

    try:
        async with async_session_maker() as db:
            from app.services.settings_service import get_settings_singleton

            settings = await get_settings_singleton(db, create=False)

            if not settings or not settings.tushare_token:
                logger.warning("未配置Tushare Token，跳过每日数据刷新")
                return

            from app.datasources.tushare import TushareClient

            client = TushareClient(settings.tushare_token)
            try:
                stock_list = await client.get_stock_basic()
                if stock_list:
                    for stock in stock_list:
                        existing = await db.execute(
                            select(StockBasic).where(StockBasic.ts_code == stock.get("ts_code"))
                        )
                        existing_stock = existing.scalar_one_or_none()

                        if existing_stock:
                            existing_stock.name = stock.get("name", existing_stock.name)
                            existing_stock.industry = stock.get("industry", existing_stock.industry)
                        else:
                            db.add(StockBasic(
                                ts_code=stock.get("ts_code"),
                                symbol=stock.get("symbol"),
                                name=stock.get("name"),
                                industry=stock.get("industry"),
                                list_date=stock.get("list_date"),
                                exchange=stock.get("exchange"),
                            ))

                    await db.commit()
                    logger.info(f"已刷新 {len(stock_list)} 只股票的基础数据")
            finally:
                await client.close()
    except Exception as e:
        logger.error(f"每日数据刷新失败: {e}")
    finally:
        logger.info("每日数据刷新完成")


async def refresh_realtime_data_task(
    *,
    logger: Any,
    is_trading_time_fn: Callable[..., bool],
    alert_once_state: dict[str, set[str]],
) -> None:
    """
    实时数据刷新
    - 刷新自选股的实时行情
    - 检查价格提醒
    """
    if not is_trading_time_fn():
        logger.debug("非交易时段，跳过实时数据刷新")
        return

    logger.info("开始实时数据刷新...")

    from app.database import async_session_maker
    from sqlalchemy import select
    from app.models.stock import FollowedStock

    try:
        async with async_session_maker() as db:
            result = await db.execute(select(FollowedStock))
            followed_stocks = result.scalars().all()

            if not followed_stocks:
                logger.info("没有自选股，跳过实时数据刷新")
                return

            codes = [normalize_stock_code(s.stock_code) for s in followed_stocks]
            codes = [c for c in codes if c]

            from app.services.stock_service import StockService

            service = StockService(db)
            quotes = await service.get_realtime_quotes(codes)
            quote_map = {q.stock_code: q for q in quotes}

            alerts = []
            from app.services.settings_service import get_settings_singleton

            settings = await get_settings_singleton(db, create=True)
            alert_enabled = bool(getattr(settings, "open_alert", True))
            alert_frequency = (getattr(settings, "alert_frequency", "always") or "always").strip().lower()
            if alert_frequency not in {"always", "once", "never"}:
                alert_frequency = "always"

            if not alert_enabled or alert_frequency == "never":
                logger.debug("提醒已关闭（open_alert=false 或 alert_frequency=never），跳过价格提醒检查")
            else:
                sent_keys: set[str] | None = None
                if alert_frequency == "once":
                    day_key = datetime.now(get_market_timezone()).date().isoformat()
                    sent_keys = alert_once_state.get(day_key, set())
                    # 只保留当天，避免长期运行导致 key 增长
                    alert_once_state.clear()
                    alert_once_state[day_key] = sent_keys

                for stock in followed_stocks:
                    normalized_code = normalize_stock_code(stock.stock_code)
                    quote = quote_map.get(normalized_code)
                    if not quote:
                        continue

                    if stock.alert_price_min > 0 and quote.current_price <= stock.alert_price_min:
                        alert_key = f"{normalized_code}:price_low:{stock.alert_price_min}"
                        if sent_keys is not None and alert_key in sent_keys:
                            continue
                        alerts.append({
                            "stock_code": stock.stock_code,
                            "stock_name": stock.stock_name,
                            "type": "price_low",
                            "message": f"{stock.stock_name} 价格 {quote.current_price} 跌破设定的 {stock.alert_price_min}"
                        })
                        if sent_keys is not None:
                            sent_keys.add(alert_key)

                    if stock.alert_price_max > 0 and quote.current_price >= stock.alert_price_max:
                        alert_key = f"{normalized_code}:price_high:{stock.alert_price_max}"
                        if sent_keys is not None and alert_key in sent_keys:
                            continue
                        alerts.append({
                            "stock_code": stock.stock_code,
                            "stock_name": stock.stock_name,
                            "type": "price_high",
                            "message": f"{stock.stock_name} 价格 {quote.current_price} 突破设定的 {stock.alert_price_max}"
                        })
                        if sent_keys is not None:
                            sent_keys.add(alert_key)

            if alerts:
                logger.info(f"触发 {len(alerts)} 个价格提醒: {alerts}")

            logger.info(f"已刷新 {len(quotes)} 只自选股的实时行情")
    except Exception as e:
        logger.error(f"实时数据刷新失败: {e}")
    finally:
        logger.info("实时数据刷新完成")


async def run_ai_stock_analysis_task(
    stock_code: str,
    prompt_template: str | None,
    *,
    logger: Any,
) -> None:
    """运行 AI 股票分析任务（具体 Prompt 构建由 AIService 负责）"""
    normalized_code = normalize_stock_code(stock_code) or (stock_code or "").strip()
    logger.info(f"开始AI分析: {normalized_code}")

    from app.database import async_session_maker
    from sqlalchemy import select, func
    from app.models.stock import FollowedStock
    from app.services.ai_service import AIService, select_ai_config

    try:
        async with async_session_maker() as db:
            result = await db.execute(
                select(FollowedStock).where(func.lower(FollowedStock.stock_code) == normalized_code.lower())
            )
            stock = result.scalar_one_or_none()

            stock_name = stock.stock_name if stock else normalized_code
            model_id = stock.ai_config_id if stock else None

            ai_config = await select_ai_config(db, model_id=model_id)
            if not ai_config:
                logger.warning(f"没有可用的AI配置，跳过 {normalized_code} 的分析")
                return

            from app.schemas.ai import StockAnalysisRequest

            ai_service = AIService(db)
            request = StockAnalysisRequest(
                stock_code=normalized_code,
                stock_name=stock_name,
                analysis_type="summary",
                model_id=ai_config.id,
                prompt_template=prompt_template,
            )
            response = await ai_service.analyze_stock(request)
            logger.info(f"AI分析完成: {normalized_code}, 结果长度: {len(response.analysis)}")
    except Exception as e:
        logger.error(f"AI分析 {normalized_code} 失败: {e}")


async def run_daily_ai_analysis_task(*, logger: Any, scheduler: Any) -> None:
    """
    每日 AI 分析
    - 对配置了定时分析的自选股进行 AI 分析
    - 排除已有独立 per-stock cron job 的股票，避免重复执行
    """
    logger.info("开始每日AI分析...")

    from app.database import async_session_maker
    from sqlalchemy import select
    from app.models.stock import FollowedStock
    from app.services.ai_service import AIService, select_ai_config

    try:
        async with async_session_maker() as db:
            result = await db.execute(
                select(FollowedStock).where(FollowedStock.cron_expression.isnot(None))
            )
            all_stocks = result.scalars().all()

            if not all_stocks:
                logger.info("没有配置定时AI分析的自选股")
                return

            stocks_to_analyze = []
            for stock in all_stocks:
                normalized_code = normalize_stock_code(stock.stock_code)
                job_id = f"stock_ai_{normalized_code or stock.stock_code}"
                if scheduler.get_job(job_id):
                    logger.debug(f"股票 {normalized_code or stock.stock_code} 已有独立 cron job，跳过")
                    continue
                stocks_to_analyze.append(stock)

            if not stocks_to_analyze:
                logger.info("所有配置了AI分析的股票都已有独立cron job，跳过批量分析")
                return

            default_config = await select_ai_config(db, model_id=None)
            if not default_config:
                logger.warning("没有启用的AI配置，跳过AI分析")
                return

            from app.schemas.ai import StockAnalysisRequest

            ai_service = AIService(db)
            for stock in stocks_to_analyze:
                try:
                    normalized_code = normalize_stock_code(stock.stock_code)
                    model_id = stock.ai_config_id or default_config.id
                    request = StockAnalysisRequest(
                        stock_code=normalized_code or stock.stock_code,
                        stock_name=stock.stock_name,
                        analysis_type="summary",
                        model_id=model_id,
                    )
                    await ai_service.analyze_stock(request)
                    logger.info(f"完成 {stock.stock_name}({normalized_code or stock.stock_code}) 的AI分析")
                except Exception as e:
                    logger.error(f"分析 {stock.stock_code} 失败: {e}")
                    continue
    except Exception as e:
        logger.error(f"每日AI分析失败: {e}")
    finally:
        logger.info("每日AI分析完成")


def _format_industry_rank(items: list) -> str:
    """格式化行业排名"""
    if not items:
        return "暂无数据"
    lines = []
    for item in items[:10]:
        lines.append(f"- {item.get('name', '')}: {item.get('change_percent', 0):.2f}%")
    return "\n".join(lines)


def _format_north_flow(data: dict) -> str:
    """格式化北向资金数据"""
    if not data:
        return "暂无数据"

    metric = str(data.get("metric") or "成交净买额")
    current = data.get("current") or {}
    if not isinstance(current, dict):
        current = {}
    lines = [
        f"- 当日{metric}: {float(current.get('total_inflow', 0) or 0) / 100000000:.2f}亿",
        f"- 沪股通: {current.get('sh_inflow', 0) / 100000000:.2f}亿",
        f"- 深股通: {current.get('sz_inflow', 0) / 100000000:.2f}亿",
    ]
    return "\n".join(lines)


async def run_weekly_summary_task(*, logger: Any) -> None:
    """
    每周市场总结
    - 生成本周市场总结报告
    """
    logger.info("开始每周市场总结...")

    from app.database import async_session_maker
    from sqlalchemy import select
    from app.models.ai import AIResponseResult
    from app.models.settings import AIConfig

    try:
        async with async_session_maker() as db:
            from app.services.ai_service import select_ai_config

            ai_config: AIConfig | None = await select_ai_config(db, model_id=None)
            if not ai_config:
                logger.warning("没有启用的AI配置，跳过每周市场总结")
                return

            from app.datasources.eastmoney import EastMoneyClient

            async with EastMoneyClient() as client:
                industry_rank = await client.get_industry_rank(sort_by="change_percent", order="desc", limit=50)
                limit_stats = await client.get_limit_stats()
                north_flow = await client.get_north_flow(5)

            prompt = f"""请为本周A股市场生成投资周报:

## 行业表现
{_format_industry_rank(industry_rank[:10]) if industry_rank else "暂无数据"}

## 涨跌停统计
- 今日涨停: {limit_stats.get('limit_up_count', 0)} 家
- 今日跌停: {limit_stats.get('limit_down_count', 0)} 家

## 北向资金
{_format_north_flow(north_flow) if north_flow else "暂无数据"}

请从以下几个方面进行总结:
1. 本周市场回顾
2. 热点板块分析
3. 资金流向分析
4. 下周展望
5. 投资建议

请用专业、简洁的语言撰写。"""

            from app.llm.client import LLMClient
            from app.schemas.ai import ChatMessage

            llm_client = LLMClient(ai_config)
            try:
                response = await llm_client.chat([ChatMessage(role="user", content=prompt)])
            finally:
                await llm_client.close()

            weekly_report = AIResponseResult(
                stock_code="MARKET",
                stock_name="市场周报",
                question="每周市场总结",
                response=response.response,
                model_name=ai_config.model_name,
                prompt_tokens=response.prompt_tokens,
                completion_tokens=response.completion_tokens,
                total_tokens=response.total_tokens,
                analysis_type="weekly_summary",
            )
            db.add(weekly_report)
            await db.commit()
            logger.info("每周市场总结已生成并保存")
    except Exception as e:
        logger.error(f"每周市场总结失败: {e}")
    finally:
        logger.info("每周市场总结完成")
