# AI 数据模型
"""
AI分析结果模型
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, Integer, Float, DateTime, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AIResponseResult(Base):
    """AI分析结果表"""
    __tablename__ = "ai_response_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    # 股票代码
    stock_code: Mapped[str] = mapped_column(String(20), index=True)

    # 股票名称
    stock_name: Mapped[str] = mapped_column(String(50), default="")

    # 查询问题
    question: Mapped[str] = mapped_column(Text, default="")

    # AI回复内容
    response: Mapped[str] = mapped_column(Text, default="")

    # 使用的AI模型
    model_name: Mapped[str] = mapped_column(String(100), default="")

    # Token使用量
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)

    # 分析类型 (summary/question/agent)
    analysis_type: Mapped[str] = mapped_column(String(50), default="question")


class AIRecommendStock(Base):
    """AI推荐股票表"""
    __tablename__ = "ai_recommend_stocks"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    # 股票代码
    stock_code: Mapped[str] = mapped_column(String(20), index=True)

    # 股票名称
    stock_name: Mapped[str] = mapped_column(String(50), default="")

    # 推荐分数 (0-100)
    score: Mapped[int] = mapped_column(Integer, default=0)

    # 推荐理由
    reason: Mapped[str] = mapped_column(Text, default="")

    # 推荐类型 (buy/hold/sell)
    recommend_type: Mapped[str] = mapped_column(String(20), default="hold")

    # 目标价
    target_price: Mapped[float] = mapped_column(Float, default=0.0)

    # 止损价
    stop_loss_price: Mapped[float] = mapped_column(Float, default=0.0)

    # 是否有效
    is_valid: Mapped[bool] = mapped_column(Boolean, default=True)

    # AI模型
    model_name: Mapped[str] = mapped_column(String(100), default="")


class PromptTemplate(Base):
    """Prompt模板表"""
    __tablename__ = "prompt_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    # 模板名称
    name: Mapped[str] = mapped_column(String(100), unique=True)

    # 模板类型 (summary/question/analysis/custom)
    template_type: Mapped[str] = mapped_column(String(50), default="custom")

    # Prompt内容
    content: Mapped[str] = mapped_column(Text, default="")

    # 模板描述
    description: Mapped[str] = mapped_column(Text, default="")

    # 是否系统内置
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)

    # 是否启用
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    # 排序
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
