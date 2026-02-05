# Stock 数据模型
"""
自选股和分组模型
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, Boolean, Integer, Float, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class FollowedStock(Base):
    """自选股表"""
    __tablename__ = "followed_stocks"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    # 股票代码 (如 sh600000, sz000001)
    stock_code: Mapped[str] = mapped_column(String(20), unique=True, index=True)

    # 股票名称
    stock_name: Mapped[str] = mapped_column(String(50), default="")

    # 成本价
    cost_price: Mapped[float] = mapped_column(Float, default=0.0)

    # 持仓数量
    volume: Mapped[int] = mapped_column(Integer, default=0)

    # 提醒价格
    alert_price_min: Mapped[float] = mapped_column(Float, default=0.0)
    alert_price_max: Mapped[float] = mapped_column(Float, default=0.0)

    # 排序
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    # 备注
    note: Mapped[Optional[str]] = mapped_column(Text, default="")

    # AI定时分析Cron表达式
    cron_expression: Mapped[Optional[str]] = mapped_column(String(100), default=None)

    # 关联的AI配置ID
    ai_config_id: Mapped[Optional[int]] = mapped_column(Integer, default=None)


class Group(Base):
    """分组表"""
    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    # 分组名称
    name: Mapped[str] = mapped_column(String(100), unique=True)

    # 分组描述
    description: Mapped[Optional[str]] = mapped_column(Text, default="")

    # 排序
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    # 关联的股票
    stocks: Mapped[list["GroupStock"]] = relationship("GroupStock", back_populates="group", cascade="all, delete-orphan")


class GroupStock(Base):
    """分组-股票关联表"""
    __tablename__ = "group_stocks"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    # 分组ID
    group_id: Mapped[int] = mapped_column(Integer, ForeignKey("groups.id"), index=True)

    # 股票代码
    stock_code: Mapped[str] = mapped_column(String(20), index=True)

    # 排序
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    # 关联
    group: Mapped["Group"] = relationship("Group", back_populates="stocks")
