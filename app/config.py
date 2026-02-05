# 配置管理模块
"""
使用 pydantic-settings 管理应用配置
"""

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


# 版本信息
VERSION = "1.0.0"
VERSION_COMMIT = "Python后端重构版本"
OFFICIAL_STATEMENT = "本软件仅供学习和研究使用，不构成投资建议。股市有风险，投资需谨慎。"


class Settings(BaseSettings):
    """应用配置"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # 应用配置
    app_name: str = "Go-Stock Python Backend"
    debug: bool = False
    version: str = VERSION

    # 服务器配置
    host: str = "0.0.0.0"
    port: int = 8001

    # 数据库配置
    database_url: str = "sqlite+aiosqlite:///./data/stock.db"

    # CORS配置
    cors_origins: list[str] = ["*"]

    # 日志配置
    log_level: str = "INFO"

    # 市场时区（A股默认 Asia/Shanghai）。用于交易时段判断与定时任务触发时间。
    market_timezone: str = "Asia/Shanghai"

    # 数据目录
    data_dir: Path = Path("./data")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # 确保数据目录存在
        self.data_dir.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    """获取配置单例"""
    return Settings()
