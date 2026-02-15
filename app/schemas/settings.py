# Settings Schemas
"""
配置相关的Pydantic模型
"""

from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, ConfigDict, Field


# ============ AIConfig Schemas ============

class AIConfigBase(BaseModel):
    """AI配置基础字段"""
    name: str = ""
    enabled: bool = True
    base_url: str = ""
    api_key: str = ""
    model_name: str = ""
    max_tokens: int = 4096
    temperature: float = 0.7
    timeout: int = 60
    http_proxy: Optional[str] = ""
    http_proxy_enabled: bool = False


class AIConfigCreate(AIConfigBase):
    """创建AI配置"""
    pass


class AIConfigUpdate(BaseModel):
    """更新AI配置"""
    name: Optional[str] = None
    enabled: Optional[bool] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    model_name: Optional[str] = None
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    timeout: Optional[int] = None
    http_proxy: Optional[str] = None
    http_proxy_enabled: Optional[bool] = None


class AIConfigResponse(AIConfigBase):
    """AI配置响应"""
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ============ Settings Schemas ============

class SettingsBase(BaseModel):
    """系统配置基础字段"""
    local_stock_codes: Optional[str] = ""
    refresh_interval: int = 3
    alert_frequency: str = "always"
    alert_window_duration: int = 10
    browser_path: Optional[str] = ""
    summary_prompt: Optional[str] = ""
    question_prompt: Optional[str] = ""
    open_alert: bool = True
    tushare_token: Optional[str] = ""
    language: str = "zh"
    version_check: bool = True


class SettingsUpdate(BaseModel):
    """更新系统配置"""
    local_stock_codes: Optional[str] = None
    refresh_interval: Optional[int] = None
    alert_frequency: Optional[str] = None
    alert_window_duration: Optional[int] = None
    browser_path: Optional[str] = None
    summary_prompt: Optional[str] = None
    question_prompt: Optional[str] = None
    open_alert: Optional[bool] = None
    tushare_token: Optional[str] = None
    language: Optional[str] = None
    version_check: Optional[bool] = None


class SettingsResponse(SettingsBase):
    """系统配置响应"""
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SettingsWithAIConfigs(SettingsResponse):
    """带AI配置的系统配置响应"""
    ai_configs: List[AIConfigResponse] = []


# ============ Export/Import Schemas ============

class ExportData(BaseModel):
    """导出数据结构"""
    settings: SettingsBase
    ai_configs: List[AIConfigBase]
    followed_stocks: List[str]
    groups: List[dict]


class ImportData(BaseModel):
    """导入数据结构"""
    settings: Optional[SettingsBase] = None
    ai_configs: Optional[List[AIConfigBase]] = None
    followed_stocks: Optional[List[str]] = None
    groups: Optional[List[dict]] = None
