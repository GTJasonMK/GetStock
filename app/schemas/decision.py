# 决策仪表盘 Schemas
"""
决策仪表盘相关的 Pydantic 数据模型。

目标：
- 输出结构化“买卖点位 + 检查清单 + 风险点”
- 主要复用技术分析结果，保持可解释、可回溯
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field

from app.schemas.technical import BuySignalEnum, TechnicalAnalysisResponse


class ChecklistStatusEnum(str, Enum):
    """检查项状态枚举"""

    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


class DecisionChecklistItem(BaseModel):
    """决策检查清单条目"""

    key: str = Field(description="检查项键（用于前端渲染/排序）")
    label: str = Field(description="检查项名称")
    status: ChecklistStatusEnum = Field(description="检查结果：pass/warn/fail")
    message: str = Field(description="简短说明（可直接展示）")


class DecisionPoints(BaseModel):
    """决策点位（精确到价格）"""

    ideal_buy: Optional[float] = Field(default=None, description="理想买入点（MA5 附近）")
    sniper_buy: Optional[float] = Field(default=None, description="狙击买入点（支撑位附近）")
    stop_loss: Optional[float] = Field(default=None, description="止损位（跌破支撑/MA20）")
    target_1: Optional[float] = Field(default=None, description="第一目标位（阻力位）")
    target_2: Optional[float] = Field(default=None, description="第二目标位（强阻力位）")


class DecisionDashboardResponse(BaseModel):
    """决策仪表盘响应"""

    stock_code: str = Field(description="股票代码")
    stock_name: str = Field(description="股票名称")
    buy_signal: BuySignalEnum = Field(description="技术面买卖信号")
    score: int = Field(ge=0, le=100, description="技术面综合评分")
    summary: str = Field(description="一句话摘要（技术面）")

    points: DecisionPoints = Field(description="买卖点位")
    checklist: List[DecisionChecklistItem] = Field(default_factory=list, description="检查清单（✅⚠️❌）")
    risks: List[str] = Field(default_factory=list, description="风险点列表（可直接展示）")

    generated_at: datetime = Field(description="生成时间")
    data_sources: List[str] = Field(default_factory=list, description="本次使用的数据源/工具（可读）")
    technical: Optional[TechnicalAnalysisResponse] = Field(default=None, description="可选：附带技术分析明细")

