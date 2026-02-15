# Stock Schemas
"""
股票相关的Pydantic模型
"""

from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, ConfigDict, Field


# ============ FollowedStock Schemas ============

class FollowedStockBase(BaseModel):
    """自选股基础字段"""
    stock_code: str
    stock_name: str = ""
    cost_price: float = 0.0
    volume: int = 0
    alert_price_min: float = 0.0
    alert_price_max: float = 0.0
    sort_order: int = 0
    note: Optional[str] = ""


class FollowedStockCreate(BaseModel):
    """添加自选股"""
    stock_code: str
    stock_name: str = ""
    cost_price: float = 0.0
    volume: int = 0


class FollowedStockUpdate(BaseModel):
    """更新自选股"""
    stock_name: Optional[str] = None
    cost_price: Optional[float] = None
    volume: Optional[int] = None
    alert_price_min: Optional[float] = None
    alert_price_max: Optional[float] = None
    sort_order: Optional[int] = None
    note: Optional[str] = None


class FollowedStockResponse(FollowedStockBase):
    """自选股响应"""
    id: int
    created_at: datetime
    updated_at: datetime
    # 实时行情字段 (可选，用于合并实时数据)
    current_price: Optional[float] = None
    change_percent: Optional[float] = None

    model_config = ConfigDict(from_attributes=True)


# ============ Group Schemas ============

class GroupBase(BaseModel):
    """分组基础字段"""
    name: str
    description: Optional[str] = ""
    sort_order: int = 0


class GroupCreate(GroupBase):
    """创建分组"""
    pass


class GroupUpdate(BaseModel):
    """更新分组"""
    name: Optional[str] = None
    description: Optional[str] = None
    sort_order: Optional[int] = None


class GroupStockItem(BaseModel):
    """分组中的股票"""
    stock_code: str
    sort_order: int = 0


class GroupResponse(GroupBase):
    """分组响应"""
    id: int
    created_at: datetime
    updated_at: datetime
    stocks: List[GroupStockItem] = []

    model_config = ConfigDict(from_attributes=True)


# ============ Stock Search Schemas ============

class StockSearchResult(BaseModel):
    """股票搜索结果"""
    stock_code: str
    stock_name: str
    exchange: str = ""
    industry: str = ""


class StockSearchResponse(BaseModel):
    """股票搜索响应"""
    results: List[StockSearchResult]
    total: int


# ============ Realtime Quote Schemas ============

class StockQuote(BaseModel):
    """股票实时行情"""
    stock_code: str
    stock_name: str
    current_price: float
    change_percent: float
    change_amount: float
    open_price: float
    high_price: float
    low_price: float
    prev_close: float
    volume: int
    amount: float
    update_time: Optional[str] = ""


class StockQuoteResponse(BaseModel):
    """实时行情响应"""
    quotes: List[StockQuote]


# ============ K-Line Schemas ============

class KLineData(BaseModel):
    """K线数据"""
    date: str
    open: float
    close: float
    high: float
    low: float
    volume: int
    amount: float
    change_percent: float = 0.0


class KLineResponse(BaseModel):
    """K线响应"""
    stock_code: str
    stock_name: str
    period: str  # day/week/month
    # 数据可用性：避免“空数组”在前端表现为“图表空白”
    available: bool = True
    reason: str = ""
    source: str = ""
    data: List[KLineData]


# ============ Minute Data Schemas ============

class MinuteData(BaseModel):
    """分钟数据"""
    time: str
    price: float
    volume: int
    avg_price: float


class MinuteDataResponse(BaseModel):
    """分钟数据响应"""
    stock_code: str
    stock_name: str
    # 数据可用性：避免“空数组”误导为“该股无分时数据”
    available: bool = True
    reason: str = ""
    source: str = ""
    data: List[MinuteData]


# ============ 筹码分布（成本分布/获利比例/集中度）===========

class ChipDistribution(BaseModel):
    """筹码分布数据（用于辅助判断成本区间与获利盘）"""
    date: str = ""
    profit_ratio: float = Field(default=0.0, description="获利比例(0-1)")
    avg_cost: float = Field(default=0.0, description="平均成本")

    cost_90_low: float = Field(default=0.0, description="90%筹码成本下限")
    cost_90_high: float = Field(default=0.0, description="90%筹码成本上限")
    concentration_90: float = Field(default=0.0, description="90%筹码集中度（越小越集中）")

    cost_70_low: float = Field(default=0.0, description="70%筹码成本下限")
    cost_70_high: float = Field(default=0.0, description="70%筹码成本上限")
    concentration_70: float = Field(default=0.0, description="70%筹码集中度（越小越集中）")

    source: str = Field(default="akshare", description="数据来源")


class ChipDistributionResponse(BaseModel):
    """筹码分布响应"""
    stock_code: str
    stock_name: str = ""
    available: bool = True
    reason: str = ""
    data: Optional[ChipDistribution] = None
