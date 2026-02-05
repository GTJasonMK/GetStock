# Market API
"""
市场数据API路由
"""

from typing import Optional, List

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.database import get_db
from app.schemas.market import (
    IndustryRankResponse,
    MoneyFlowResponse,
    LongTigerResponse,
    EconomicDataResponse,
    SectorStockResponse,
    MarketOverview,
)
from app.schemas.common import Response

router = APIRouter()


@router.get("/industry-rank", response_model=Response[IndustryRankResponse])
async def get_industry_rank(
    sort_by: str = Query("change_percent", description="排序字段: change_percent/turnover"),
    order: str = Query("desc", description="排序方向: asc/desc"),
    limit: int = Query(20, le=100),
    db: AsyncSession = Depends(get_db)
):
    """获取行业排名"""
    from app.services.market_service import MarketService

    service = MarketService(db)
    data = await service.get_industry_rank(sort_by, order, limit)

    return Response(data=data)


@router.get("/money-flow", response_model=Response[MoneyFlowResponse])
async def get_money_flow(
    sort_by: str = Query("main_net_inflow", description="排序字段"),
    order: str = Query("desc"),
    limit: int = Query(20, le=100),
    db: AsyncSession = Depends(get_db)
):
    """获取资金流向"""
    from app.services.market_service import MarketService

    service = MarketService(db)
    data = await service.get_money_flow(sort_by, order, limit)

    return Response(data=data)


@router.get("/long-tiger", response_model=Response[LongTigerResponse])
async def get_long_tiger(
    trade_date: Optional[str] = Query(None, description="交易日期 YYYY-MM-DD"),
    db: AsyncSession = Depends(get_db)
):
    """获取龙虎榜"""
    from app.services.market_service import MarketService

    service = MarketService(db)
    data = await service.get_long_tiger(trade_date)

    return Response(data=data)


@router.get("/economic", response_model=Response[EconomicDataResponse])
async def get_economic_data(
    indicator: str = Query(..., description="指标: GDP/CPI/PPI/PMI"),
    count: int = Query(20, le=100),
    db: AsyncSession = Depends(get_db)
):
    """获取宏观经济数据"""
    from app.services.market_service import MarketService

    service = MarketService(db)
    data = await service.get_economic_data(indicator, count)

    return Response(data=data)


@router.get("/sector/{bk_code}/stocks", response_model=Response[SectorStockResponse])
async def get_sector_stocks(
    bk_code: str,
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db)
):
    """获取板块成分股"""
    from app.services.market_service import MarketService

    service = MarketService(db)
    data = await service.get_sector_stocks(bk_code, limit)

    return Response(data=data)


# ============ 概念板块排名 ============

@router.get("/concept-rank", response_model=Response[IndustryRankResponse])
async def get_concept_rank(
    sort_by: str = Query("change_percent", description="排序字段: change_percent/turnover"),
    order: str = Query("desc"),
    limit: int = Query(20, le=100),
    db: AsyncSession = Depends(get_db)
):
    """获取概念板块排名"""
    from app.services.market_service import MarketService

    service = MarketService(db)
    data = await service.get_concept_rank(sort_by, order, limit)

    return Response(data=data)


# ============ 行业资金流入排名 ============

@router.get("/industry-money-flow")
async def get_industry_money_flow(
    category: str = Query("hangye", description="分类: hangye(行业)/gainian(概念)"),
    sort_by: str = Query("main_inflow", description="排序字段"),
    db: AsyncSession = Depends(get_db)
):
    """获取行业/概念资金流向排名"""
    from app.services.market_service import MarketService

    service = MarketService(db)
    data = await service.get_industry_money_flow(category, sort_by)

    return Response(data=data)


# ============ 股票资金流入排名 ============

@router.get("/stock-money-rank")
async def get_stock_money_rank(
    sort_by: str = Query("main_inflow", description="排序字段"),
    limit: int = Query(20, le=100),
    db: AsyncSession = Depends(get_db)
):
    """获取股票资金流入排名"""
    from app.services.market_service import MarketService

    service = MarketService(db)
    data = await service.get_stock_money_rank(sort_by, limit)

    return Response(data=data)


# ============ 量比排名 ============

@router.get("/volume-ratio-rank")
async def get_volume_ratio_rank(
    min_ratio: float = Query(2.0, description="最小量比"),
    limit: int = Query(20, le=100),
    db: AsyncSession = Depends(get_db)
):
    """获取量比排名"""
    from app.services.market_service import MarketService

    service = MarketService(db)
    data = await service.get_volume_ratio_rank(min_ratio, limit)

    return Response(data=data)


# ============ 涨跌停统计 ============

class LimitUpDownStats(BaseModel):
    """涨跌停统计"""
    limit_up_count: int
    limit_down_count: int
    limit_up_stocks: List[dict]
    limit_down_stocks: List[dict]


@router.get("/limit-stats", response_model=Response[LimitUpDownStats])
async def get_limit_stats(db: AsyncSession = Depends(get_db)):
    """获取涨跌停统计"""
    from app.services.market_service import MarketService

    service = MarketService(db)
    data = await service.get_limit_stats()

    return Response(data=data)


# ============ 北向资金 ============

class NorthFlowData(BaseModel):
    """北向资金数据"""
    date: str
    sh_inflow: float
    sz_inflow: float
    total_inflow: float
    sh_balance: float
    sz_balance: float


class NorthFlowResponse(BaseModel):
    """北向资金响应"""
    # 口径说明：避免把“成交净买额/净流入”等概念混用造成误导
    metric: str = "成交净买额"
    unit: str = "元"
    source: str = ""
    asof_date: str = ""
    current: Optional[NorthFlowData] = None
    history: List[NorthFlowData]


@router.get("/north-flow", response_model=Response[NorthFlowResponse])
async def get_north_flow(
    days: int = Query(30, le=365),
    db: AsyncSession = Depends(get_db)
):
    """获取北向资金数据"""
    from app.services.market_service import MarketService

    service = MarketService(db)
    data = await service.get_north_flow(days)

    return Response(data=data)


# ============ 板块字典 ============

@router.get("/bk-dict")
async def get_bk_dict(
    bk_type: str = Query("all", description="板块类型: all/industry/concept/area"),
    db: AsyncSession = Depends(get_db)
):
    """获取板块字典"""
    from app.services.market_service import MarketService

    service = MarketService(db)
    data = await service.get_bk_dict(bk_type)

    return Response(data=data)


# ============ 市场概览（大盘复盘口径）===========

@router.get("/overview", response_model=Response[MarketOverview])
async def get_market_overview(db: AsyncSession = Depends(get_db)):
    """获取市场概览（涨跌家数/成交额/指数/板块榜等）"""
    from app.services.market_service import MarketService

    service = MarketService(db)
    data = await service.get_market_overview()

    return Response(data=data)
