# News Schemas
"""
资讯相关的Pydantic模型
"""

from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel


class TelegraphItem(BaseModel):
    """电报条目"""
    telegraph_id: str
    publish_time: datetime
    title: str
    content: str
    source: str = "cls"
    importance: int = 1
    tags: List[str] = []


class TelegraphResponse(BaseModel):
    """电报列表响应"""
    items: List[TelegraphItem]
    total: int
    has_more: bool
    # 实际数据来源（cls/sina/...），用于前端判断是否降级
    source: str = "cls"
    # 降级提示（可选）
    notice: str = ""


class NewsItem(BaseModel):
    """新闻条目"""
    news_id: str
    title: str
    content: str
    source: str
    publish_time: datetime
    url: Optional[str] = ""
    image_url: Optional[str] = ""


class NewsResponse(BaseModel):
    """新闻列表响应"""
    items: List[NewsItem]
    total: int


class GlobalIndex(BaseModel):
    """全球指数"""
    code: str
    name: str
    current: float
    change_percent: float
    change_amount: float
    update_time: str


class GlobalIndexResponse(BaseModel):
    """全球指数响应"""
    indexes: List[GlobalIndex]
