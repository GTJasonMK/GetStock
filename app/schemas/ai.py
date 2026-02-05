# AI Schemas
"""
AI相关的Pydantic模型
"""

from datetime import datetime
from typing import Optional, List, Any

from pydantic import BaseModel


# ============ Chat Schemas ============

class ChatMessage(BaseModel):
    """聊天消息"""
    role: str  # user/assistant/system
    content: str


class ChatRequest(BaseModel):
    """聊天请求"""
    messages: List[ChatMessage]
    stock_code: Optional[str] = None
    stock_name: Optional[str] = None
    model_id: Optional[int] = None  # AI配置ID
    stream: bool = False
    # 是否启用“联网/资讯检索”增强（默认启用；内部会按问题类型做轻量判断，避免每次都触发外部搜索）
    enable_retrieval: bool = True
    # Agent 执行模式：chat/agent/do/think/auto（默认 agent）
    mode: Optional[str] = None
    # 会话ID：用于后端持久化多轮记忆；不传则自动创建
    session_id: Optional[str] = None
    # 参与推理的最大历史消息条数（仅影响上下文拼接，不影响落库全量）
    max_context_messages: int = 20
    # do/think 模式：规划步数上限（仅影响 plan，不影响落库）
    max_plan_steps: int = 6
    # think 模式：规划候选数量（多视角/多轮规划 → 评估挑选）
    plan_candidates: int = 3
    # 是否对本次 AgentRun 进行评估并落库（默认启用启发式评估；可选启用 LLM 评估）
    enable_run_evaluation: bool = True
    # 是否启用 LLM 评估（会产生额外模型调用成本；默认关闭）
    enable_llm_evaluation: bool = False


class ChatResponse(BaseModel):
    """聊天响应"""
    response: str
    model_name: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    session_id: Optional[str] = None


class StreamChunk(BaseModel):
    """流式响应块"""
    content: str
    done: bool = False
    model_name: str = ""
    tokens: int = 0


# ============ Analysis Schemas ============

class StockAnalysisRequest(BaseModel):
    """股票分析请求"""
    stock_code: str
    stock_name: str = ""
    analysis_type: str = "summary"  # summary/detail/technical
    model_id: Optional[int] = None
    # 指定 Prompt 模板名称（PromptTemplate.name），用于覆盖默认 stock_{analysis_type}
    prompt_template: Optional[str] = None


class StockAnalysisResponse(BaseModel):
    """股票分析响应"""
    stock_code: str
    stock_name: str
    analysis: str
    model_name: str
    analysis_type: str
    created_at: datetime


# ============ AI History Schemas ============

class AIHistoryItem(BaseModel):
    """AI历史记录"""
    id: int
    stock_code: str
    stock_name: str
    question: str
    response: str
    model_name: str
    analysis_type: str
    created_at: datetime


class AIHistoryResponse(BaseModel):
    """AI历史响应"""
    items: List[AIHistoryItem]
    total: int


# ============ Agent Schemas ============

class AgentToolCall(BaseModel):
    """Agent工具调用"""
    tool_name: str
    arguments: dict
    result: Optional[Any] = None


class AgentThought(BaseModel):
    """Agent思考过程"""
    thought: str
    action: Optional[str] = None
    action_input: Optional[dict] = None
    observation: Optional[str] = None


class AgentResponse(BaseModel):
    """Agent响应"""
    answer: str
    thoughts: List[AgentThought] = []
    tool_calls: List[AgentToolCall] = []
    model_name: str
    total_tokens: int = 0
    session_id: Optional[str] = None


# ============ Session Schemas ============

class AISessionInfo(BaseModel):
    """会话信息"""
    id: str
    mode: str
    title: str
    stock_code: str = ""
    stock_name: str = ""
    model_name: str = ""
    message_count: int = 0
    created_at: datetime
    updated_at: datetime


class AISessionMessageItem(BaseModel):
    """会话消息"""
    id: int
    role: str
    content: str
    created_at: datetime


class AISessionDetailResponse(BaseModel):
    """会话详情（含消息列表）"""
    session: AISessionInfo
    messages: List[AISessionMessageItem]


class AISessionListResponse(BaseModel):
    """会话列表响应"""
    items: List[AISessionInfo]
    total: int


# ============ Recommend Schemas ============

class AIRecommendItem(BaseModel):
    """AI推荐股票"""
    stock_code: str
    stock_name: str
    score: int
    reason: str
    recommend_type: str
    target_price: float = 0.0
    stop_loss_price: float = 0.0
    model_name: str
    created_at: datetime


class AIRecommendResponse(BaseModel):
    """AI推荐响应"""
    items: List[AIRecommendItem]
