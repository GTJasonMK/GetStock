# News 数据模型
"""
资讯和电报模型
"""

from datetime import datetime
from typing import Optional, List

from sqlalchemy import String, Text, Integer, DateTime, ForeignKey, Table, Column
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


# 电报-标签关联表
telegraph_tags = Table(
    "telegraph_tags",
    Base.metadata,
    Column("telegraph_id", Integer, ForeignKey("telegraphs.id"), primary_key=True),
    Column("tag_id", Integer, ForeignKey("tags.id"), primary_key=True),
)


class Telegraph(Base):
    """财联社电报表"""
    __tablename__ = "telegraphs"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    # 电报ID (源站ID)
    telegraph_id: Mapped[str] = mapped_column(String(50), unique=True, index=True)

    # 发布时间
    publish_time: Mapped[datetime] = mapped_column(DateTime, index=True)

    # 标题
    title: Mapped[str] = mapped_column(String(500), default="")

    # 内容
    content: Mapped[str] = mapped_column(Text, default="")

    # 来源
    source: Mapped[str] = mapped_column(String(50), default="cls")

    # 重要程度 (1-5)
    importance: Mapped[int] = mapped_column(Integer, default=1)

    # 关联标签
    tags: Mapped[List["Tag"]] = relationship("Tag", secondary=telegraph_tags, back_populates="telegraphs")


class Tag(Base):
    """标签表"""
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    # 标签名称
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)

    # 标签类型 (industry/concept/stock)
    tag_type: Mapped[str] = mapped_column(String(20), default="concept")

    # 关联电报
    telegraphs: Mapped[List["Telegraph"]] = relationship("Telegraph", secondary=telegraph_tags, back_populates="tags")


class TelegraphTag(Base):
    """电报-标签详细关联表 (包含额外字段)"""
    __tablename__ = "telegraph_tag_details"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegraph_id: Mapped[int] = mapped_column(Integer, ForeignKey("telegraphs.id"), index=True)
    tag_id: Mapped[int] = mapped_column(Integer, ForeignKey("tags.id"), index=True)

    # 关联强度
    relevance: Mapped[float] = mapped_column(Integer, default=1.0)
