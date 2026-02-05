# Market Schemas
"""
市场数据相关的Pydantic模型
"""

from datetime import datetime
from typing import Optional, List, Dict, Any

from pydantic import BaseModel


# ============ Industry/Sector Schemas ============

class IndustryRank(BaseModel):
    """行业排名"""
    bk_code: str
    bk_name: str
    change_percent: float
    turnover: float  # 换手率(%)
    leader_stock_code: str = ""
    leader_stock_name: str = ""
    leader_change_percent: float = 0.0
    stock_count: int = 0


class IndustryRankResponse(BaseModel):
    """行业排名响应"""
    items: List[IndustryRank]
    update_time: str


# ============ Money Flow Schemas ============

class MoneyFlowItem(BaseModel):
    """资金流向"""
    stock_code: str
    stock_name: str
    current_price: float
    change_percent: float
    main_net_inflow: float  # 主力净流入(万)
    main_net_inflow_percent: float  # 主力净流入占比
    super_large_net_inflow: float  # 超大单净流入(万)
    large_net_inflow: float  # 大单净流入(万)
    medium_net_inflow: float  # 中单净流入(万)
    small_net_inflow: float  # 小单净流入(万)


class MoneyFlowResponse(BaseModel):
    """资金流向响应"""
    items: List[MoneyFlowItem]
    update_time: str


# ============ Long Tiger Rank Schemas ============

class LongTigerItem(BaseModel):
    """龙虎榜条目"""
    trade_date: str
    stock_code: str
    stock_name: str
    close_price: float
    change_percent: float
    net_buy_amount: float  # 净买入额(万)
    buy_amount: float  # 买入总额(万)
    sell_amount: float  # 卖出总额(万)
    reason: str


class LongTigerResponse(BaseModel):
    """龙虎榜响应"""
    items: List[LongTigerItem]
    trade_date: str


# ============ Economic Data Schemas ============

class EconomicDataItem(BaseModel):
    """宏观经济数据"""
    report_date: str
    indicator_name: str
    value: float
    yoy_change: float = 0.0  # 同比变化
    mom_change: float = 0.0  # 环比变化


class EconomicDataResponse(BaseModel):
    """宏观经济数据响应"""
    indicator: str  # GDP/CPI/PPI/PMI
    items: List[EconomicDataItem]


# ============ Concept/Sector Stocks Schemas ============

class SectorStock(BaseModel):
    """板块成分股"""
    stock_code: str
    stock_name: str
    current_price: float
    change_percent: float
    turnover_rate: float = 0.0
    market_value: float = 0.0  # 市值(亿)


class SectorStockResponse(BaseModel):
    """板块成分股响应"""
    bk_code: str
    bk_name: str
    stocks: List[SectorStock]


# ============ 市场概览（大盘复盘口径）===========

class MarketIndex(BaseModel):
    """市场指数行情（用于大盘概览）"""
    code: str
    name: str
    current: float = 0.0
    change_percent: float = 0.0
    change_amount: float = 0.0
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    prev_close: float = 0.0
    volume: float = 0.0
    amount: float = 0.0
    amplitude: float = 0.0
    update_time: str = ""


class MarketOverview(BaseModel):
    """市场概览（涨跌家数/两市成交额/板块榜等）"""
    date: str
    indices: List[MarketIndex] = []

    # 数据可用性（避免数据源异常时“全为0”误导）
    available: bool = True
    reason: str = ""

    up_count: int = 0
    down_count: int = 0
    flat_count: int = 0

    limit_up_count: int = 0
    limit_down_count: int = 0

    # 两市成交额（亿元）
    total_amount: float = 0.0

    # 北向资金净流入（亿元，可能为空）
    north_flow: Optional[float] = None

    # 板块涨跌榜（用于复盘摘要）
    top_sectors: List[Dict[str, Any]] = []
    bottom_sectors: List[Dict[str, Any]] = []
