# Fund Schemas
"""
基金相关的Pydantic模型
"""

from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, ConfigDict


# ============ FollowedFund Schemas ============

class FollowedFundBase(BaseModel):
    """关注基金基础字段"""
    fund_code: str
    fund_name: str = ""
    cost_price: float = 0.0
    shares: float = 0.0
    sort_order: int = 0
    note: Optional[str] = ""


class FollowedFundCreate(BaseModel):
    """添加关注基金"""
    fund_code: str
    fund_name: str = ""


class FollowedFundUpdate(BaseModel):
    """更新关注基金"""
    fund_name: Optional[str] = None
    cost_price: Optional[float] = None
    shares: Optional[float] = None
    sort_order: Optional[int] = None
    note: Optional[str] = None


class FollowedFundResponse(FollowedFundBase):
    """关注基金响应"""
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ============ Fund Search Schemas ============

class FundSearchResult(BaseModel):
    """基金搜索结果"""
    fund_code: str
    fund_name: str
    fund_type: str
    company: str


class FundSearchResponse(BaseModel):
    """基金搜索响应"""
    results: List[FundSearchResult]
    total: int


# ============ Fund Detail Schemas ============

class FundDetail(BaseModel):
    """基金详情"""
    fund_code: str
    name: str
    short_name: str
    fund_type: str
    establish_date: str
    company: str
    manager: str
    fund_scale: float
    net_value: float
    total_value: float
    day_growth: float
    week_growth: float = 0.0
    month_growth: float = 0.0
    three_month_growth: float = 0.0
    six_month_growth: float = 0.0
    year_growth: float = 0.0


class FundNetValueHistory(BaseModel):
    """基金净值历史"""
    date: str
    net_value: float
    total_value: float
    day_growth: float


class FundNetValueResponse(BaseModel):
    """基金净值历史响应"""
    fund_code: str
    fund_name: str
    data: List[FundNetValueHistory]
