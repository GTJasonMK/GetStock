# Market 数据模型
"""
股票基础信息和指数模型
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, Boolean, Integer, Float, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class StockInfo(Base):
    """股票实时信息缓存表"""
    __tablename__ = "stock_info"

    id: Mapped[int] = mapped_column(primary_key=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    # 股票代码
    stock_code: Mapped[str] = mapped_column(String(20), unique=True, index=True)

    # 股票名称
    stock_name: Mapped[str] = mapped_column(String(50), default="")

    # 价格信息
    current_price: Mapped[float] = mapped_column(Float, default=0.0)
    change_percent: Mapped[float] = mapped_column(Float, default=0.0)
    change_amount: Mapped[float] = mapped_column(Float, default=0.0)
    open_price: Mapped[float] = mapped_column(Float, default=0.0)
    high_price: Mapped[float] = mapped_column(Float, default=0.0)
    low_price: Mapped[float] = mapped_column(Float, default=0.0)
    prev_close: Mapped[float] = mapped_column(Float, default=0.0)

    # 成交信息
    volume: Mapped[int] = mapped_column(Integer, default=0)
    amount: Mapped[float] = mapped_column(Float, default=0.0)


class StockBasic(Base):
    """股票基础信息表 (A股)"""
    __tablename__ = "stock_basic"

    id: Mapped[int] = mapped_column(primary_key=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    # 股票代码 (不含前缀)
    ts_code: Mapped[str] = mapped_column(String(20), unique=True, index=True)

    # 股票代码 (含前缀，如 sh600000)
    symbol: Mapped[str] = mapped_column(String(20), index=True)

    # 股票名称
    name: Mapped[str] = mapped_column(String(50), default="")

    # 所属行业
    industry: Mapped[str] = mapped_column(String(50), default="")

    # 上市日期
    list_date: Mapped[Optional[str]] = mapped_column(String(20), default="")

    # 交易所 (SSE/SZSE)
    exchange: Mapped[str] = mapped_column(String(10), default="")

    # 状态 (L-上市, D-退市, P-暂停上市)
    status: Mapped[str] = mapped_column(String(10), default="L")


class IndexBasic(Base):
    """指数基础信息表"""
    __tablename__ = "index_basic"

    id: Mapped[int] = mapped_column(primary_key=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    # 指数代码
    ts_code: Mapped[str] = mapped_column(String(20), unique=True, index=True)

    # 指数名称
    name: Mapped[str] = mapped_column(String(100), default="")

    # 指数全称
    fullname: Mapped[Optional[str]] = mapped_column(String(200), default="")

    # 市场 (SSE/SZSE/CSI)
    market: Mapped[str] = mapped_column(String(10), default="")

    # 发布机构
    publisher: Mapped[Optional[str]] = mapped_column(String(100), default="")

    # 基期
    base_date: Mapped[Optional[str]] = mapped_column(String(20), default="")

    # 基点
    base_point: Mapped[float] = mapped_column(Float, default=1000.0)


class StockInfoHK(Base):
    """港股基础信息表"""
    __tablename__ = "stock_info_hk"

    id: Mapped[int] = mapped_column(primary_key=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    # 股票代码
    ts_code: Mapped[str] = mapped_column(String(20), unique=True, index=True)

    # 股票名称
    name: Mapped[str] = mapped_column(String(100), default="")

    # 英文名称
    enname: Mapped[Optional[str]] = mapped_column(String(200), default="")

    # 上市日期
    list_date: Mapped[Optional[str]] = mapped_column(String(20), default="")

    # 状态
    status: Mapped[str] = mapped_column(String(10), default="L")


class StockInfoUS(Base):
    """美股基础信息表"""
    __tablename__ = "stock_info_us"

    id: Mapped[int] = mapped_column(primary_key=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    # 股票代码
    ts_code: Mapped[str] = mapped_column(String(20), unique=True, index=True)

    # 股票名称
    name: Mapped[str] = mapped_column(String(100), default="")

    # 英文名称
    enname: Mapped[Optional[str]] = mapped_column(String(200), default="")

    # 交易所 (NYSE/NASDAQ/AMEX)
    exchange: Mapped[str] = mapped_column(String(20), default="")

    # 上市日期
    list_date: Mapped[Optional[str]] = mapped_column(String(20), default="")

    # 状态
    status: Mapped[str] = mapped_column(String(10), default="L")
