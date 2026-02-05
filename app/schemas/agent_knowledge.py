# Agent Knowledge Schemas
"""
Agent 知识库相关 Pydantic 模型（用于 API 与检索结果返回）。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


class AgentDomainItem(BaseModel):
    id: str
    name: str = ""
    description: str = ""
    keywords: list[str] = []
    parent_id: str = ""
    sort_order: int = 0
    is_enabled: bool = True
    is_deprecated: bool = False
    created_at: datetime
    updated_at: datetime


class AgentSkillItem(BaseModel):
    id: int
    name: str
    domain_id: str
    description: str = ""
    triggers: list[str] = []
    prerequisites: list[str] = []
    steps: list[str] = []
    failure_modes: list[str] = []
    validation: list[str] = []
    version: str = "1.0.0"
    status: str = "approved"
    is_enabled: bool = True
    created_at: datetime
    updated_at: datetime


class AgentSolutionItem(BaseModel):
    id: int
    name: str
    domain_id: str = ""
    description: str = ""
    skill_ids: list[int] = []
    tool_names: list[str] = []
    steps: Any = None
    status: str = "approved"
    is_enabled: bool = True
    created_at: datetime
    updated_at: datetime


class AgentToolDocItem(BaseModel):
    tool_name: str
    description: str = ""
    parameters_schema: Any = None
    usage: str = ""
    tips: str = ""
    status: str = "approved"
    is_enabled: bool = True
    created_at: datetime
    updated_at: datetime


class AgentGraphNodeItem(BaseModel):
    id: int
    title: str
    content: str
    keywords: list[str] = []
    domain_id: str = ""
    confidence: float = 0.6
    source: str = ""
    is_active: bool = True
    created_at: datetime
    updated_at: datetime


class AgentGraphNodeCreateRequest(BaseModel):
    title: str
    content: str
    keywords: list[str] = []
    domain_id: str = ""
    confidence: float = 0.6
    source: str = "user"
    is_active: bool = True


class AgentGraphNodeUpdateRequest(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    keywords: Optional[list[str]] = None
    domain_id: Optional[str] = None
    confidence: Optional[float] = None
    source: Optional[str] = None
    is_active: Optional[bool] = None


class AgentSkillCreateRequest(BaseModel):
    name: str
    domain_id: str
    description: str = ""
    triggers: list[str] = []
    prerequisites: list[str] = []
    steps: list[str] = []
    failure_modes: list[str] = []
    validation: list[str] = []
    version: str = "1.0.0"
    status: str = "draft"
    is_enabled: bool = True


class AgentSkillUpdateRequest(BaseModel):
    name: Optional[str] = None
    domain_id: Optional[str] = None
    description: Optional[str] = None
    triggers: Optional[list[str]] = None
    prerequisites: Optional[list[str]] = None
    steps: Optional[list[str]] = None
    failure_modes: Optional[list[str]] = None
    validation: Optional[list[str]] = None
    version: Optional[str] = None
    status: Optional[str] = None
    is_enabled: Optional[bool] = None


class AgentSolutionCreateRequest(BaseModel):
    name: str
    domain_id: str = ""
    description: str = ""
    skill_ids: list[int] = []
    tool_names: list[str] = []
    steps: Any = None
    status: str = "draft"
    is_enabled: bool = True


class AgentSolutionUpdateRequest(BaseModel):
    name: Optional[str] = None
    domain_id: Optional[str] = None
    description: Optional[str] = None
    skill_ids: Optional[list[int]] = None
    tool_names: Optional[list[str]] = None
    steps: Any = None
    status: Optional[str] = None
    is_enabled: Optional[bool] = None


class AgentRetrieveRequest(BaseModel):
    query: str
    mode: Optional[str] = "do"


class AgentRetrieveResponse(BaseModel):
    query: str
    mode: str
    keywords: list[str]
    context: str
    graph_nodes: list[AgentGraphNodeItem] = []
    domains: list[AgentDomainItem] = []
    skills: list[AgentSkillItem] = []
    solutions: list[AgentSolutionItem] = []
    tool_docs: list[AgentToolDocItem] = []


class AgentRunItem(BaseModel):
    id: int
    created_at: datetime
    session_id: str
    mode: str
    stock_code: str = ""
    stock_name: str = ""
    question: str
    plan_json: Any = None
    used_tools: list[str] = []
    answer: str
    model_name: str = ""
    total_tokens: int = 0
    retrieval_context: str = ""
    evaluation: Any = None
    score: int = 0
