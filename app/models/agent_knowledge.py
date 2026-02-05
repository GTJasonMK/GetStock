# Agent 知识库模型
"""
对齐 LearningSelfAgent/docs/agent 的“知识层/检索”范式：

- 图谱节点（Graph）：记录事实/约束/依赖（用于检索注入）
- 领域（Domain）：第一层筛选器
- 技能（Skill）：方法论/通用解法
- 方案（Solution）：完成某类任务的完整步骤参考
- 工具文档（ToolDoc）：对工具的使用说明与注意事项

说明：
- 本项目没有迁移工具（Alembic），因此只新增表，不做 ALTER。
- 以可落地为优先：字段以“可检索/可注入/可审计”为目标。
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AgentGraphNode(Base):
    """知识图谱节点（事实/约束/依赖）。"""

    __tablename__ = "agent_graph_nodes"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    title: Mapped[str] = mapped_column(String(200), default="", index=True)
    content: Mapped[str] = mapped_column(Text, default="")

    # 用于简单检索的关键词（JSON 字符串数组或空格分隔均可）
    keywords: Mapped[str] = mapped_column(Text, default="")

    # 可选归属领域（便于域过滤）
    domain_id: Mapped[str] = mapped_column(String(64), default="", index=True)

    # 置信度（0-1）：用于排序/过滤
    confidence: Mapped[float] = mapped_column(Float, default=0.6)

    # 来源：如 code/review/user/run 等
    source: Mapped[str] = mapped_column(String(100), default="")

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)


class AgentDomain(Base):
    """领域（Domain）：用于第一层筛选，避免全量注入污染上下文。"""

    __tablename__ = "agent_domains"

    # 领域标识建议使用层级 id，如：finance.stock
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    name: Mapped[str] = mapped_column(String(100), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    # 关键词（JSON 字符串数组）
    keywords: Mapped[str] = mapped_column(Text, default="")

    parent_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    is_system: Mapped[bool] = mapped_column(Boolean, default=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    is_deprecated: Mapped[bool] = mapped_column(Boolean, default=False, index=True)


class AgentSkill(Base):
    """技能（Skill）：可复用的方法论。"""

    __tablename__ = "agent_skills"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    name: Mapped[str] = mapped_column(String(120), default="", index=True)
    domain_id: Mapped[str] = mapped_column(String(64), ForeignKey("agent_domains.id"), index=True)

    description: Mapped[str] = mapped_column(Text, default="")
    triggers: Mapped[str] = mapped_column(Text, default="")  # JSON 数组
    prerequisites: Mapped[str] = mapped_column(Text, default="")  # JSON 数组
    steps: Mapped[str] = mapped_column(Text, default="")  # JSON 数组/或文本
    failure_modes: Mapped[str] = mapped_column(Text, default="")  # JSON 数组
    validation: Mapped[str] = mapped_column(Text, default="")  # JSON 数组

    version: Mapped[str] = mapped_column(String(40), default="1.0.0")
    status: Mapped[str] = mapped_column(String(20), default="approved", index=True)  # draft/approved/deprecated

    source: Mapped[str] = mapped_column(String(120), default="system")
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)


class AgentSolution(Base):
    """方案（Solution）：完成某类任务的完整流程参考。"""

    __tablename__ = "agent_solutions"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    name: Mapped[str] = mapped_column(String(120), default="", index=True)
    domain_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    description: Mapped[str] = mapped_column(Text, default="")

    # 关联技能 ID 列表（JSON 数组），用于匹配/检索
    skill_ids: Mapped[str] = mapped_column(Text, default="")
    # 推荐工具名列表（JSON 数组）
    tool_names: Mapped[str] = mapped_column(Text, default="")
    # 方案步骤（JSON 数组），可与 do/think 的 plan 结构相近
    steps: Mapped[str] = mapped_column(Text, default="")

    status: Mapped[str] = mapped_column(String(20), default="approved", index=True)
    source: Mapped[str] = mapped_column(String(120), default="system")
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)


class AgentToolDoc(Base):
    """工具文档（ToolDoc）：描述工具如何用、注意事项与常见失败。"""

    __tablename__ = "agent_tool_docs"

    tool_name: Mapped[str] = mapped_column(String(80), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    description: Mapped[str] = mapped_column(Text, default="")
    parameters_schema: Mapped[str] = mapped_column(Text, default="")  # JSON schema
    usage: Mapped[str] = mapped_column(Text, default="")
    tips: Mapped[str] = mapped_column(Text, default="")

    status: Mapped[str] = mapped_column(String(20), default="approved", index=True)
    source: Mapped[str] = mapped_column(String(120), default="system")
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)


class AgentRun(Base):
    """Agent 执行记录（用于评估与知识沉淀的“原料层”）。"""

    __tablename__ = "agent_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)

    session_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    mode: Mapped[str] = mapped_column(String(20), default="agent", index=True)

    stock_code: Mapped[str] = mapped_column(String(20), default="", index=True)
    stock_name: Mapped[str] = mapped_column(String(50), default="")

    question: Mapped[str] = mapped_column(Text, default="")
    plan_json: Mapped[str] = mapped_column(Text, default="")
    used_tools: Mapped[str] = mapped_column(Text, default="")  # JSON 数组

    answer: Mapped[str] = mapped_column(Text, default="")
    model_name: Mapped[str] = mapped_column(String(100), default="")
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)

    # 检索注入（用于复盘/审计）
    retrieval_context: Mapped[str] = mapped_column(Text, default="")

    # 评估结果（JSON 字符串）
    evaluation: Mapped[str] = mapped_column(Text, default="")
    score: Mapped[int] = mapped_column(Integer, default=0)


Index("ix_agent_graph_nodes_domain_conf", AgentGraphNode.domain_id, AgentGraphNode.confidence)
Index("ix_agent_skills_domain_status", AgentSkill.domain_id, AgentSkill.status)
Index("ix_agent_solutions_domain_status", AgentSolution.domain_id, AgentSolution.status)
