# AI 会话模型
"""
AI 多轮对话会话与消息持久化模型

说明：
- 仅用于“会话级别”的多轮记忆/恢复，不替代 ai_response_results（单次分析历史）。
- 采用新增表方式实现，避免对既有表结构做 ALTER（项目无迁移工具）。
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AISession(Base):
    """AI 会话表（支持 chat/agent）。"""

    __tablename__ = "ai_sessions"

    # 使用 uuid4().hex 作为主键，避免自增在多端同步时冲突
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    # 会话模式：chat / agent
    mode: Mapped[str] = mapped_column(String(20), default="agent", index=True)

    # 上下文信息（可空）
    stock_code: Mapped[str] = mapped_column(String(20), default="", index=True)
    stock_name: Mapped[str] = mapped_column(String(50), default="")
    title: Mapped[str] = mapped_column(String(200), default="")
    model_name: Mapped[str] = mapped_column(String(100), default="")

    # 统计字段（便于列表页快速展示）
    message_count: Mapped[int] = mapped_column(Integer, default=0)

    # 预留：长会话可将早期内容总结为摘要，降低后续推理 Token 压力
    memory_summary: Mapped[str] = mapped_column(Text, default="")


class AISessionMessage(Base):
    """AI 会话消息表（user/assistant/system/tool 等）。"""

    __tablename__ = "ai_session_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("ai_sessions.id", ondelete="CASCADE"),
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)

    # user / assistant / system / tool
    role: Mapped[str] = mapped_column(String(20), index=True)
    content: Mapped[str] = mapped_column(Text, default="")

    # 可选字段：当 role=tool 时记录工具名；或用于其他扩展
    name: Mapped[str] = mapped_column(String(100), default="")

    # 额外信息（JSON 字符串），用于调试/重放（可空）
    extra: Mapped[str] = mapped_column(Text, default="")

    __table_args__ = (
        Index("ix_ai_session_messages_session_id_id", "session_id", "id"),
    )

