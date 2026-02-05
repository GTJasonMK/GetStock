# 技术分析数据模型
"""
技术分析相关的 Pydantic 数据模型
"""

from datetime import datetime
from typing import List, Dict, Optional
from enum import Enum

from pydantic import BaseModel, Field


class TrendStatusEnum(str, Enum):
    """趋势状态枚举"""
    STRONG_UP = "strong_up"
    UP = "up"
    WEAK_UP = "weak_up"
    CONSOLIDATION = "consolidation"
    WEAK_DOWN = "weak_down"
    DOWN = "down"
    STRONG_DOWN = "strong_down"


class BuySignalEnum(str, Enum):
    """买卖信号枚举"""
    STRONG_BUY = "strong_buy"
    BUY = "buy"
    WEAK_BUY = "weak_buy"
    HOLD = "hold"
    WEAK_SELL = "weak_sell"
    SELL = "sell"
    STRONG_SELL = "strong_sell"


class MACDSignalEnum(str, Enum):
    """MACD信号枚举"""
    GOLDEN_CROSS = "golden_cross"
    DEATH_CROSS = "death_cross"
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


class RSISignalEnum(str, Enum):
    """RSI信号枚举"""
    OVERSOLD = "oversold"
    OVERBOUGHT = "overbought"
    NEUTRAL = "neutral"


class MACDResponse(BaseModel):
    """MACD响应"""
    dif: float = Field(description="快线DIF")
    dea: float = Field(description="慢线DEA")
    macd: float = Field(description="MACD柱")
    signal: MACDSignalEnum = Field(description="MACD信号")
    dif_history: List[float] = Field(default=[], description="历史DIF值")
    dea_history: List[float] = Field(default=[], description="历史DEA值")
    macd_history: List[float] = Field(default=[], description="历史MACD值")


class RSIResponse(BaseModel):
    """RSI响应"""
    rsi_6: float = Field(description="6日RSI")
    rsi_12: float = Field(description="12日RSI")
    rsi_24: float = Field(description="24日RSI")
    signal: RSISignalEnum = Field(description="RSI信号")


class VolumeAnalysisResponse(BaseModel):
    """成交量分析响应"""
    current_volume: int = Field(description="当日成交量")
    avg_volume_5: float = Field(description="5日均量")
    avg_volume_10: float = Field(description="10日均量")
    volume_ratio: float = Field(description="量比")
    is_volume_breakout: bool = Field(description="是否放量突破")
    volume_trend: str = Field(description="成交量趋势")


class TrendAnalysisResponse(BaseModel):
    """趋势分析响应"""
    status: TrendStatusEnum = Field(description="趋势状态")
    ma_5: float = Field(description="5日均线")
    ma_10: float = Field(description="10日均线")
    ma_20: float = Field(description="20日均线")
    ma_60: float = Field(description="60日均线")
    price_position: str = Field(description="价格位置")
    ma_alignment: str = Field(description="均线排列")
    bias_5: float = Field(description="5日乖离率")
    bias_10: float = Field(description="10日乖离率")


class SupportResistanceResponse(BaseModel):
    """支撑阻力位响应"""
    support_1: float = Field(description="第一支撑位")
    support_2: float = Field(description="第二支撑位")
    resistance_1: float = Field(description="第一阻力位")
    resistance_2: float = Field(description="第二阻力位")
    current_price: float = Field(description="当前价格")
    distance_to_support: float = Field(description="距支撑位百分比")
    distance_to_resistance: float = Field(description="距阻力位百分比")


class TechnicalAnalysisResponse(BaseModel):
    """技术分析完整响应"""
    stock_code: str = Field(description="股票代码")
    name: str = Field(description="股票名称")
    current_price: float = Field(description="当前价格")
    change_percent: float = Field(description="涨跌幅")
    trend: TrendAnalysisResponse = Field(description="趋势分析")
    macd: MACDResponse = Field(description="MACD指标")
    rsi: RSIResponse = Field(description="RSI指标")
    volume: VolumeAnalysisResponse = Field(description="成交量分析")
    support_resistance: SupportResistanceResponse = Field(description="支撑阻力位")
    buy_signal: BuySignalEnum = Field(description="买卖信号")
    score: int = Field(ge=0, le=100, description="综合评分")
    score_details: Dict[str, int] = Field(description="评分明细")
    analysis_time: datetime = Field(description="分析时间")
    summary: str = Field(description="分析摘要")


class BatchTechnicalRequest(BaseModel):
    """批量技术分析请求"""
    codes: List[str] = Field(min_length=1, max_length=20, description="股票代码列表")


class BatchTechnicalResponse(BaseModel):
    """批量技术分析响应"""
    results: List[TechnicalAnalysisResponse] = Field(description="分析结果列表")
    failed: List[str] = Field(default=[], description="分析失败的股票代码")


# ============ 数据源管理相关 ============

class CircuitStateEnum(str, Enum):
    """熔断器状态枚举"""
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class DataSourceStatus(BaseModel):
    """数据源状态"""
    name: str = Field(description="数据源名称")
    state: CircuitStateEnum = Field(description="熔断器状态")
    failure_count: int = Field(description="失败计数")
    failure_threshold: int = Field(description="失败阈值")
    cooldown_seconds: float = Field(description="冷却时间(秒)")
    last_failure_time: Optional[str] = Field(default=None, description="最后失败时间")
    priority: int = Field(description="优先级")


class DataSourceConfigRequest(BaseModel):
    """数据源配置请求"""
    enabled: Optional[bool] = Field(default=None, description="是否启用")
    priority: Optional[int] = Field(default=None, ge=0, description="优先级")
    failure_threshold: Optional[int] = Field(default=None, ge=1, le=10, description="失败阈值")
    cooldown_seconds: Optional[int] = Field(default=None, ge=60, le=3600, description="冷却时间")
    api_key: Optional[str] = Field(default=None, description="API Key")


class DataSourceConfigResponse(BaseModel):
    """数据源配置响应"""
    id: int
    source_name: str
    enabled: bool
    priority: int
    failure_threshold: int
    cooldown_seconds: int
    api_key: Optional[str] = None


# ============ 搜索引擎配置相关 ============

class SearchEngineEnum(str, Enum):
    """搜索引擎枚举"""
    TAVILY = "tavily"
    SERPAPI = "serpapi"
    BOCHA = "bocha"


class SearchEngineConfigRequest(BaseModel):
    """搜索引擎配置请求"""
    engine: SearchEngineEnum = Field(description="引擎类型")
    api_key: str = Field(min_length=1, description="API Key")
    enabled: bool = Field(default=True, description="是否启用")
    weight: int = Field(default=1, ge=1, le=10, description="轮询权重")
    daily_limit: Optional[int] = Field(default=None, ge=0, description="每日限额")


class SearchEngineConfigResponse(BaseModel):
    """搜索引擎配置响应"""
    id: int
    engine: SearchEngineEnum
    enabled: bool
    weight: int
    daily_limit: Optional[int]
    used_today: int
    last_reset_date: Optional[str]


class SearchEngineStatus(BaseModel):
    """搜索引擎状态"""
    engine: SearchEngineEnum
    total_keys: int = Field(description="配置的Key数量")
    enabled_keys: int = Field(description="启用的Key数量")
    total_daily_limit: Optional[int] = Field(default=None, description="总每日限额")
    total_used_today: int = Field(description="今日总使用量")
