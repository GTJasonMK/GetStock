# Fund 数据模型
"""
基金相关模型
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, Integer, Float, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class FollowedFund(Base):
    """关注的基金表"""
    __tablename__ = "followed_funds"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    # 基金代码
    fund_code: Mapped[str] = mapped_column(String(20), unique=True, index=True)

    # 基金名称
    fund_name: Mapped[str] = mapped_column(String(100), default="")

    # 持仓成本
    cost_price: Mapped[float] = mapped_column(Float, default=0.0)

    # 持仓份额
    shares: Mapped[float] = mapped_column(Float, default=0.0)

    # 排序
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    # 备注
    note: Mapped[Optional[str]] = mapped_column(Text, default="")


class FundBasic(Base):
    """基金基础信息表"""
    __tablename__ = "fund_basic"

    id: Mapped[int] = mapped_column(primary_key=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    # 基金代码
    fund_code: Mapped[str] = mapped_column(String(20), unique=True, index=True)

    # 基金名称
    name: Mapped[str] = mapped_column(String(200), default="")

    # 基金简称
    short_name: Mapped[str] = mapped_column(String(100), default="")

    # 基金类型 (股票型/债券型/混合型/货币型/QDII/FOF)
    fund_type: Mapped[str] = mapped_column(String(50), default="")

    # 成立日期
    establish_date: Mapped[Optional[str]] = mapped_column(String(20), default="")

    # 基金公司
    company: Mapped[str] = mapped_column(String(100), default="")

    # 基金经理
    manager: Mapped[str] = mapped_column(String(200), default="")

    # 基金规模 (亿)
    fund_scale: Mapped[float] = mapped_column(Float, default=0.0)

    # 最新净值
    net_value: Mapped[float] = mapped_column(Float, default=0.0)

    # 累计净值
    total_value: Mapped[float] = mapped_column(Float, default=0.0)

    # 日涨跌幅
    day_growth: Mapped[float] = mapped_column(Float, default=0.0)
