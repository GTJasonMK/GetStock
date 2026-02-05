# Market Data 数据模型
"""
市场数据模型 (龙虎榜、板块等)
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, Integer, Float, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class LongTigerRankData(Base):
    """龙虎榜数据表"""
    __tablename__ = "long_tiger_rank_data"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    # 交易日期
    trade_date: Mapped[str] = mapped_column(String(20), index=True)

    # 股票代码
    stock_code: Mapped[str] = mapped_column(String(20), index=True)

    # 股票名称
    stock_name: Mapped[str] = mapped_column(String(50), default="")

    # 收盘价
    close_price: Mapped[float] = mapped_column(Float, default=0.0)

    # 涨跌幅
    change_percent: Mapped[float] = mapped_column(Float, default=0.0)

    # 龙虎榜净买入额 (万)
    net_buy_amount: Mapped[float] = mapped_column(Float, default=0.0)

    # 买入总额 (万)
    buy_amount: Mapped[float] = mapped_column(Float, default=0.0)

    # 卖出总额 (万)
    sell_amount: Mapped[float] = mapped_column(Float, default=0.0)

    # 上榜原因
    reason: Mapped[str] = mapped_column(Text, default="")

    # 详情JSON (营业部买卖信息)
    detail_json: Mapped[Optional[str]] = mapped_column(Text, default="")


class BKDict(Base):
    """板块字典表"""
    __tablename__ = "bk_dict"

    id: Mapped[int] = mapped_column(primary_key=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    # 板块代码
    bk_code: Mapped[str] = mapped_column(String(20), unique=True, index=True)

    # 板块名称
    bk_name: Mapped[str] = mapped_column(String(100), default="")

    # 板块类型 (industry/concept/region)
    bk_type: Mapped[str] = mapped_column(String(20), default="industry")

    # 成分股数量
    stock_count: Mapped[int] = mapped_column(Integer, default=0)

    # 平均涨跌幅
    avg_change_percent: Mapped[float] = mapped_column(Float, default=0.0)

    # 总市值 (亿)
    total_market_value: Mapped[float] = mapped_column(Float, default=0.0)

    # 成交额 (亿)
    turnover: Mapped[float] = mapped_column(Float, default=0.0)

    # 领涨股代码
    leader_stock_code: Mapped[Optional[str]] = mapped_column(String(20), default="")

    # 领涨股名称
    leader_stock_name: Mapped[Optional[str]] = mapped_column(String(50), default="")
