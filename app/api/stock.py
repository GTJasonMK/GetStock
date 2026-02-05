# Stock API
"""
股票数据API路由 - 完整实现
"""

from typing import List, Optional, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, delete, update, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.stock import FollowedStock
from app.utils.helpers import normalize_stock_code
from app.schemas.stock import (
    FollowedStockCreate,
    FollowedStockUpdate,
    FollowedStockResponse,
    StockSearchResult,
    StockSearchResponse,
    StockQuote,
    StockQuoteResponse,
    KLineResponse,
    MinuteDataResponse,
    ChipDistributionResponse,
)
from app.schemas.common import Response

router = APIRouter()


# ============ Stock Info API (Greet) ============

@router.get("/info/{stock_code}")
async def get_stock_info(
    stock_code: str,
    db: AsyncSession = Depends(get_db)
):
    """
    获取股票详细信息 (对应Go的Greet方法)
    包括实时行情、基本面数据等
    """
    from app.services.stock_service import StockService

    service = StockService(db)
    info = await service.get_stock_info(stock_code)

    return Response(data=info)


@router.get("/detail/{stock_code}")
async def get_stock_detail(
    stock_code: str,
    db: AsyncSession = Depends(get_db)
):
    """获取股票完整详情，包含所有可用信息"""
    from app.services.stock_service import StockService

    service = StockService(db)
    detail = await service.get_stock_detail(stock_code)

    return Response(data=detail)


# ============ Followed Stocks API ============

@router.get("/follow", response_model=Response[List[FollowedStockResponse]])
async def get_followed_stocks(
    with_realtime: bool = Query(False, description="是否包含实时行情"),
    db: AsyncSession = Depends(get_db)
):
    """获取自选股列表"""
    result = await db.execute(
        select(FollowedStock).order_by(FollowedStock.sort_order, FollowedStock.id)
    )
    stocks = result.scalars().all()

    stock_list = [FollowedStockResponse.model_validate(s) for s in stocks]

    # 统一返回 stock_code 为规范格式（sh/sz/hk/us 前缀 + 小写市场前缀）
    # 目的：避免历史大写/非规范数据导致前端 quotesMap key 不一致，从而出现“行情不展示”的隐蔽故障
    for stock in stock_list:
        normalized = normalize_stock_code(stock.stock_code)
        if normalized:
            stock.stock_code = normalized

    # 获取实时行情
    if with_realtime and stock_list:
        from app.services.stock_service import StockService
        service = StockService(db)
        codes = [normalize_stock_code(s.stock_code) for s in stock_list]
        quotes = await service.get_realtime_quotes(codes)
        quote_map = {q.stock_code: q for q in quotes}

        # 合并实时数据
        for stock in stock_list:
            quote = quote_map.get(normalize_stock_code(stock.stock_code))
            if quote:
                stock.current_price = quote.current_price
                stock.change_percent = quote.change_percent

    return Response(data=stock_list)


@router.post("/follow", response_model=Response[FollowedStockResponse])
async def add_followed_stock(
    data: FollowedStockCreate,
    db: AsyncSession = Depends(get_db)
):
    """添加自选股"""
    data.stock_code = normalize_stock_code(data.stock_code)
    if not data.stock_code:
        raise HTTPException(status_code=400, detail="股票代码不能为空")

    # 检查是否已存在
    result = await db.execute(
        select(FollowedStock).where(func.lower(FollowedStock.stock_code) == data.stock_code.lower())
    )
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="股票已在自选列表中")

    # 获取股票名称
    if not data.stock_name:
        from app.services.stock_service import StockService
        service = StockService(db)
        quotes = await service.get_realtime_quotes([data.stock_code])
        if quotes:
            data.stock_name = quotes[0].stock_name

    stock = FollowedStock(**data.model_dump())
    db.add(stock)
    await db.commit()
    await db.refresh(stock)

    return Response(data=FollowedStockResponse.model_validate(stock))


@router.put("/follow/sort", response_model=Response)
async def sort_followed_stocks(
    stock_codes: List[str],
    db: AsyncSession = Depends(get_db)
):
    """排序自选股"""
    for idx, code in enumerate(stock_codes):
        code = normalize_stock_code(code)
        if not code:
            continue
        result = await db.execute(
            select(FollowedStock).where(func.lower(FollowedStock.stock_code) == code.lower())
        )
        stock = result.scalar_one_or_none()
        if stock:
            stock.sort_order = idx

    await db.commit()
    return Response(message="排序成功")


@router.put("/follow/{stock_code}", response_model=Response[FollowedStockResponse])
async def update_followed_stock(
    stock_code: str,
    data: FollowedStockUpdate,
    db: AsyncSession = Depends(get_db)
):
    """更新自选股"""
    stock_code = normalize_stock_code(stock_code)
    result = await db.execute(
        select(FollowedStock).where(func.lower(FollowedStock.stock_code) == stock_code.lower())
    )
    stock = result.scalar_one_or_none()

    if not stock:
        raise HTTPException(status_code=404, detail="自选股不存在")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(stock, key, value)

    await db.commit()
    await db.refresh(stock)

    return Response(data=FollowedStockResponse.model_validate(stock))


@router.delete("/follow/{stock_code}", response_model=Response)
async def delete_followed_stock(
    stock_code: str,
    db: AsyncSession = Depends(get_db)
):
    """删除自选股"""
    stock_code = normalize_stock_code(stock_code)
    result = await db.execute(
        select(FollowedStock).where(func.lower(FollowedStock.stock_code) == stock_code.lower())
    )
    stock = result.scalar_one_or_none()

    if not stock:
        raise HTTPException(status_code=404, detail="自选股不存在")

    await db.delete(stock)
    await db.commit()

    return Response(message="删除成功")


# ============ Cost Price and Volume ============

@router.put("/follow/{stock_code}/cost")
async def set_cost_price_and_volume(
    stock_code: str,
    cost_price: float = Query(..., description="成本价"),
    volume: int = Query(..., description="持仓数量"),
    db: AsyncSession = Depends(get_db)
):
    """设置成本价和持仓数量"""
    stock_code = normalize_stock_code(stock_code)
    result = await db.execute(
        select(FollowedStock).where(func.lower(FollowedStock.stock_code) == stock_code.lower())
    )
    stock = result.scalar_one_or_none()

    if not stock:
        raise HTTPException(status_code=404, detail="自选股不存在")

    stock.cost_price = cost_price
    stock.volume = volume

    await db.commit()
    return Response(message="设置成功")


# ============ Alert Settings ============

@router.put("/follow/{stock_code}/alert")
async def set_stock_alert(
    stock_code: str,
    alert_price_min: float = Query(0, description="最低提醒价"),
    alert_price_max: float = Query(0, description="最高提醒价"),
    db: AsyncSession = Depends(get_db)
):
    """设置股票告警"""
    stock_code = normalize_stock_code(stock_code)
    result = await db.execute(
        select(FollowedStock).where(func.lower(FollowedStock.stock_code) == stock_code.lower())
    )
    stock = result.scalar_one_or_none()

    if not stock:
        raise HTTPException(status_code=404, detail="自选股不存在")

    stock.alert_price_min = alert_price_min
    stock.alert_price_max = alert_price_max

    await db.commit()
    return Response(message="设置成功")


# ============ Stock Search API ============

@router.get("/list", response_model=Response[StockSearchResponse])
async def search_stocks(
    keyword: str = Query(..., min_length=1),
    market: Optional[str] = Query(None, description="市场: A/HK/US"),
    limit: int = Query(20, le=100),
    db: AsyncSession = Depends(get_db)
):
    """搜索股票"""
    from app.services.stock_service import StockService

    service = StockService(db)
    results = await service.search_stocks(keyword, market, limit)

    return Response(data=StockSearchResponse(results=results, total=len(results)))


@router.get("/search")
async def search_stock_nlp(
    words: str = Query(..., description="自然语言搜索条件"),
    db: AsyncSession = Depends(get_db)
):
    """
    自然语言选股 (对应Go的SearchStock方法)
    支持条件如: "涨停股", "主力资金流入", "MACD金叉" 等
    """
    from app.services.search_service import SearchService

    service = SearchService(db)
    results = await service.search_by_words(words)

    return Response(data=results)


# ============ Realtime Data API ============

@router.get("/realtime", response_model=Response[StockQuoteResponse])
async def get_realtime_quotes(
    codes: str = Query(..., description="股票代码，逗号分隔"),
    db: AsyncSession = Depends(get_db)
):
    """获取实时行情"""
    from app.services.stock_service import StockService

    service = StockService(db)
    code_list = [c.strip() for c in codes.split(",") if c.strip()]
    quotes = await service.get_realtime_quotes(code_list)

    return Response(data=StockQuoteResponse(quotes=quotes))


# ============ K-Line API ============

@router.get("/{stock_code}/kline", response_model=Response[KLineResponse])
async def get_kline(
    stock_code: str,
    period: str = Query("day", description="周期: day/week/month/5min/15min/30min/60min"),
    count: int = Query(100, le=500),
    adjust: str = Query("qfq", description="复权类型: qfq(前复权)/hfq(后复权)/none"),
    db: AsyncSession = Depends(get_db)
):
    """获取K线数据"""
    from app.services.stock_service import StockService

    period = (period or "").strip().lower()
    adjust = (adjust or "").strip().lower()

    allowed_periods = {"day", "week", "month", "5min", "15min", "30min", "60min"}
    if period not in allowed_periods:
        raise HTTPException(status_code=400, detail=f"不支持的周期: {period}")

    allowed_adjust = {"qfq", "hfq", "none"}
    if adjust not in allowed_adjust:
        raise HTTPException(status_code=400, detail=f"不支持的复权类型: {adjust}")

    service = StockService(db)
    kline_data = await service.get_kline(stock_code, period, count, adjust)

    return Response(data=kline_data)


# ============ Minute Data API ============

@router.get("/{stock_code}/minute", response_model=Response[MinuteDataResponse])
async def get_minute_data(
    stock_code: str,
    db: AsyncSession = Depends(get_db)
):
    """获取分时数据"""
    from app.services.stock_service import StockService

    service = StockService(db)
    minute_data = await service.get_minute_data(stock_code)

    return Response(data=minute_data)


# ============ Money Flow API ============

@router.get("/{stock_code}/money-flow")
async def get_stock_money_flow(
    stock_code: str,
    days: int = Query(10, le=60),
    db: AsyncSession = Depends(get_db)
):
    """获取股票资金流向"""
    from app.services.stock_service import StockService

    service = StockService(db)
    data = await service.get_money_flow(stock_code, days)

    return Response(data=data)


@router.get("/{stock_code}/money-trend")
async def get_stock_money_trend(
    stock_code: str,
    days: int = Query(10, le=60),
    db: AsyncSession = Depends(get_db)
):
    """获取股票资金流向趋势"""
    from app.services.stock_service import StockService

    service = StockService(db)
    data = await service.get_money_trend(stock_code, days)

    return Response(data=data)


# ============ Research Report API ============

@router.get("/{stock_code}/research-reports")
async def get_stock_research_reports(
    stock_code: str,
    limit: int = Query(20, le=100),
    db: AsyncSession = Depends(get_db)
):
    """获取股票研究报告"""
    from app.services.market_service import MarketService

    service = MarketService(db)
    reports = await service.get_stock_research_reports(stock_code, limit)

    return Response(data=reports)


@router.get("/{stock_code}/notices")
async def get_stock_notices(
    stock_code: str,
    limit: int = Query(20, le=100),
    db: AsyncSession = Depends(get_db)
):
    """获取股票公告"""
    from app.services.market_service import MarketService

    service = MarketService(db)
    notices = await service.get_stock_notices(stock_code, limit)

    return Response(data=notices)


# ============ Concept/Industry Info ============

@router.get("/{stock_code}/concept")
async def get_stock_concept_info(
    stock_code: str,
    db: AsyncSession = Depends(get_db)
):
    """获取股票所属概念/板块信息"""
    from app.services.stock_service import StockService

    service = StockService(db)
    concepts = await service.get_stock_concepts(stock_code)

    return Response(data=concepts)


# ============ Interactive Q&A ============

@router.get("/interactive-qa")
async def get_interactive_qa(
    keyword: str = Query(..., description="搜索关键词"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, le=100),
    db: AsyncSession = Depends(get_db)
):
    """获取投资者互动问答"""
    from app.services.market_service import MarketService

    service = MarketService(db)
    data = await service.get_interactive_qa(keyword, page, page_size)

    return Response(data=data)


# ============ Hot Stocks ============

@router.get("/hot")
async def get_hot_stocks(
    market: str = Query("A", description="市场: A/HK/US"),
    limit: int = Query(20, le=100),
    db: AsyncSession = Depends(get_db)
):
    """获取热门股票"""
    from app.services.stock_service import StockService

    service = StockService(db)
    stocks = await service.get_hot_stocks(market, limit)

    return Response(data=stocks)


# ============ Hot Strategy ============

@router.get("/hot-strategy")
async def get_hot_strategy(db: AsyncSession = Depends(get_db)):
    """获取热门选股策略"""
    from app.services.search_service import SearchService

    service = SearchService(db)
    strategies = await service.get_hot_strategies()

    return Response(data=strategies)


# ============ 基本面数据 ============

@router.get("/{stock_code}/fundamental")
async def get_stock_fundamental(
    stock_code: str,
    db: AsyncSession = Depends(get_db)
):
    """
    获取个股基本面数据

    返回: PE(动态/TTM/静态), PB, ROE, 总市值, 流通市值,
    每股收益, 每股净资产, 净利润同比, 营收同比, 毛利率等
    """
    from app.services.stock_service import StockService

    service = StockService(db)
    data = await service.get_stock_fundamental(stock_code)

    return Response(data=data)


@router.get("/{stock_code}/financial")
async def get_financial_report(
    stock_code: str,
    db: AsyncSession = Depends(get_db)
):
    """
    获取财务报表数据

    返回: 最近4期的利润表(营收/净利润/EPS)和资产负债表(总资产/总负债/股东权益)
    """
    from app.services.stock_service import StockService

    service = StockService(db)
    data = await service.get_financial_report(stock_code)

    return Response(data=data)


# ============ 股票排行榜 ============

@router.get("/rank")
async def get_stock_rank(
    sort_by: str = Query("change_percent", description="排序字段: change_percent/volume/amount/turnover_rate/pe/pb/market_cap"),
    order: str = Query("desc", description="排序方向: asc/desc"),
    limit: int = Query(50, le=200),
    market: str = Query("all", description="市场: all/main/cyb/kcb/bj"),
    db: AsyncSession = Depends(get_db)
):
    """
    获取股票排行榜(含估值指标)

    返回: 股票代码, 名称, 价格, 涨跌幅, 成交量, 成交额,
    换手率, PE(动态/TTM), PB, 总市值, 流通市值, ROE, 行业
    """
    from app.services.stock_service import StockService

    service = StockService(db)
    data = await service.get_stock_rank(sort_by, order, limit, market)

    return Response(data=data)


# ============ 行业研报 ============

@router.get("/industry-reports")
async def get_industry_research_reports(
    name: str = Query("", description="行业名称"),
    code: str = Query("", description="行业代码"),
    limit: int = Query(20, le=100),
    db: AsyncSession = Depends(get_db)
):
    """获取行业研究报告"""
    from app.services.stock_service import StockService

    service = StockService(db)
    data = await service.get_industry_research_reports(name, code, limit)

    return Response(data=data)


# ============ 持仓收益分析 ============

@router.get("/portfolio/analysis")
async def get_portfolio_analysis(db: AsyncSession = Depends(get_db)):
    """
    分析自选股持仓收益

    返回: 总成本, 总市值, 总收益, 总收益率,
    每只持仓股的成本价/现价/收益/收益率
    """
    from app.services.stock_service import StockService

    service = StockService(db)
    data = await service.get_portfolio_analysis()

    return Response(data=data)


# ============ 机构评级汇总 ============

@router.get("/{stock_code}/rating")
async def get_stock_rating_summary(
    stock_code: str,
    db: AsyncSession = Depends(get_db)
):
    """
    获取机构评级汇总

    返回: 评级分布(买入/增持/中性等数量), 一致预期目标价(平均/最高/最低),
    各机构最新评级详情列表
    """
    from app.services.stock_service import StockService

    service = StockService(db)
    data = await service.get_rating_summary(stock_code)

    return Response(data=data)


# ============ 历史资金流向明细 ============

@router.get("/{stock_code}/money-flow-history")
async def get_stock_money_flow_history(
    stock_code: str,
    days: int = Query(30, le=120, description="天数"),
    db: AsyncSession = Depends(get_db)
):
    """
    获取个股历史资金流向明细

    返回: 每日主力/超大单/大单/中单/小单净流入金额和占比
    """
    from app.services.stock_service import StockService

    service = StockService(db)
    data = await service.get_money_flow_history(stock_code, days)

    return Response(data=data)


# ============ 股东人数变化 ============

@router.get("/{stock_code}/shareholders")
async def get_shareholder_count(
    stock_code: str,
    db: AsyncSession = Depends(get_db)
):
    """
    获取股东人数变化

    返回: 近期各报告期股东人数、变动比例、人均持股量
    反映筹码集中度趋势
    """
    from app.services.stock_service import StockService

    service = StockService(db)
    data = await service.get_shareholder_count(stock_code)

    return Response(data=data)


# ============ 十大股东 ============

@router.get("/{stock_code}/top-holders")
async def get_top_holders(
    stock_code: str,
    holder_type: str = Query("float", description="股东类型: float=流通股东, total=全部股东"),
    db: AsyncSession = Depends(get_db)
):
    """
    获取十大股东或十大流通股东

    返回: 股东名称、持股数量、持股比例、变动情况
    """
    from app.services.stock_service import StockService

    service = StockService(db)
    data = await service.get_top_holders(stock_code, holder_type)

    return Response(data=data)


# ============ 分红送转历史 ============

@router.get("/{stock_code}/dividend")
async def get_dividend_history(
    stock_code: str,
    db: AsyncSession = Depends(get_db)
):
    """
    获取分红送转历史

    返回: 各年度分红方案、除权除息日、送股/转增比例、每股分红金额
    """
    from app.services.stock_service import StockService

    service = StockService(db)
    data = await service.get_dividend_history(stock_code)

    return Response(data=data)


# ============ 筹码分布（成本分布/获利比例/集中度）===========

@router.get("/{stock_code}/chip-distribution", response_model=Response[ChipDistributionResponse])
async def get_chip_distribution(
    stock_code: str,
    db: AsyncSession = Depends(get_db)
):
    """
    获取筹码分布（对标 daily_stock_analysis）

    返回：获利比例、平均成本、70/90 成本区间与集中度。
    注：ETF/指数/非A股可能无数据，会返回 available=false 并给出原因。
    """
    from app.services.stock_service import StockService

    service = StockService(db)
    data = await service.get_chip_distribution(stock_code)

    return Response(data=data)


# ============ Stock AI Cron ============

@router.put("/follow/{stock_code}/cron")
async def set_stock_ai_cron(
    stock_code: str,
    cron_expression: str = Query(..., description="Cron表达式，如: 0 15 * * 1-5"),
    db: AsyncSession = Depends(get_db)
):
    """设置股票AI定时分析任务"""
    stock_code = normalize_stock_code(stock_code)
    cron_expression = " ".join((cron_expression or "").split())

    # 写库前先校验 cron 表达式，避免“返回成功但任务永远不跑”的隐蔽故障
    from app.tasks.scheduler import build_cron_trigger
    try:
        build_cron_trigger(cron_expression)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"cron表达式无效: {e}")

    result = await db.execute(
        select(FollowedStock).where(func.lower(FollowedStock.stock_code) == stock_code.lower())
    )
    stock = result.scalar_one_or_none()

    if not stock:
        raise HTTPException(status_code=404, detail="自选股不存在")

    stock.cron_expression = cron_expression

    await db.commit()

    # 如果当前进程为 scheduler leader，则立即更新内存任务；否则由 leader 的同步任务收敛生效
    from app.tasks.scheduler import is_scheduler_leader, schedule_stock_ai_analysis
    if is_scheduler_leader():
        schedule_stock_ai_analysis(stock_code, cron_expression)

    return Response(message="设置成功")


@router.delete("/follow/{stock_code}/cron")
async def remove_stock_ai_cron(
    stock_code: str,
    db: AsyncSession = Depends(get_db)
):
    """移除股票AI定时分析任务"""
    stock_code = normalize_stock_code(stock_code)
    result = await db.execute(
        select(FollowedStock).where(func.lower(FollowedStock.stock_code) == stock_code.lower())
    )
    stock = result.scalar_one_or_none()

    if not stock:
        raise HTTPException(status_code=404, detail="自选股不存在")

    stock.cron_expression = None

    await db.commit()

    # 仅在 scheduler leader 中移除内存任务；多进程下由 leader 的同步任务最终收敛
    from app.tasks.scheduler import is_scheduler_leader, remove_job
    if is_scheduler_leader():
        remove_job(f"stock_ai_{stock_code}")

    return Response(message="移除成功")
