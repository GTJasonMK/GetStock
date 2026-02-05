# Settings 数据模型
"""
系统配置和AI配置模型
"""

from datetime import datetime, date
from typing import Optional

from sqlalchemy import String, Text, Boolean, Integer, Float, DateTime, Date
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Settings(Base):
    """系统配置表"""
    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    # 本地股票代码 (逗号分隔)
    local_stock_codes: Mapped[Optional[str]] = mapped_column(Text, default="")

    # 刷新间隔 (秒)
    refresh_interval: Mapped[int] = mapped_column(Integer, default=3)

    # 提醒配置
    alert_frequency: Mapped[str] = mapped_column(String(50), default="always")
    alert_window_duration: Mapped[int] = mapped_column(Integer, default=10)

    # 浏览器配置
    browser_path: Mapped[Optional[str]] = mapped_column(String(500), default="")

    # AI 分析配置
    summary_prompt: Mapped[Optional[str]] = mapped_column(Text, default="")
    question_prompt: Mapped[Optional[str]] = mapped_column(Text, default="")

    # 开盘提醒
    open_alert: Mapped[bool] = mapped_column(Boolean, default=True)

    # Tushare Token
    tushare_token: Mapped[Optional[str]] = mapped_column(String(200), default="")

    # 定时任务
    cron_entry_id: Mapped[int] = mapped_column(Integer, default=0)
    cron_ticker_entry_id: Mapped[int] = mapped_column(Integer, default=0)

    # 语言
    language: Mapped[str] = mapped_column(String(20), default="zh")

    # 版本检查
    version_check: Mapped[bool] = mapped_column(Boolean, default=True)


class AIConfig(Base):
    """AI配置表"""
    __tablename__ = "ai_configs"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    # 配置名称
    name: Mapped[str] = mapped_column(String(100), default="")

    # 是否启用
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    # API配置
    base_url: Mapped[str] = mapped_column(String(500), default="")
    api_key: Mapped[str] = mapped_column(String(500), default="")
    model_name: Mapped[str] = mapped_column(String(100), default="")

    # 模型参数
    max_tokens: Mapped[int] = mapped_column(Integer, default=4096)
    temperature: Mapped[float] = mapped_column(Float, default=0.7)
    timeout: Mapped[int] = mapped_column(Integer, default=60)

    # 代理配置
    http_proxy: Mapped[Optional[str]] = mapped_column(String(500), default="")
    http_proxy_enabled: Mapped[bool] = mapped_column(Boolean, default=False)


class DataSourceConfig(Base):
    """数据源配置表 - 用于多数据源管理和熔断"""
    __tablename__ = "datasource_config"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    # 数据源名称: sina, eastmoney, tencent, tushare
    source_name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)

    # 是否启用
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    # 优先级，数字越小优先级越高
    priority: Mapped[int] = mapped_column(Integer, default=0)

    # 熔断器配置
    failure_threshold: Mapped[int] = mapped_column(Integer, default=3)
    cooldown_seconds: Mapped[int] = mapped_column(Integer, default=300)

    # API Key (部分数据源需要)
    api_key: Mapped[Optional[str]] = mapped_column(String(500), default="")


class SearchEngineConfig(Base):
    """搜索引擎配置表 - 用于多引擎新闻搜索"""
    __tablename__ = "search_engine_config"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    # 引擎类型: tavily, serpapi, bocha
    engine: Mapped[str] = mapped_column(String(50), nullable=False)

    # API Key
    api_key: Mapped[str] = mapped_column(String(500), nullable=False)

    # 是否启用
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    # 轮询权重
    weight: Mapped[int] = mapped_column(Integer, default=1)

    # 每日限额 (可选)
    daily_limit: Mapped[Optional[int]] = mapped_column(Integer, default=None)

    # 今日已用次数
    used_today: Mapped[int] = mapped_column(Integer, default=0)

    # 上次重置日期
    last_reset_date: Mapped[Optional[date]] = mapped_column(Date, default=None)

