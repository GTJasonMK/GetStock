# AI Service
"""
AI分析服务 - 完整实现
"""

import logging
import re
import uuid
from typing import AsyncGenerator, Optional, List
from datetime import datetime
import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.settings import AIConfig
from app.models.ai import AIResponseResult, AIRecommendStock, PromptTemplate
from app.models.ai_session import AISession, AISessionMessage
from app.models.agent_knowledge import AgentRun
from app.schemas.ai import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    StockAnalysisRequest,
    StockAnalysisResponse,
    AgentResponse,
    StreamChunk,
)
from app.utils.helpers import normalize_stock_code
from app.utils.cache import cached, CacheTTL

logger = logging.getLogger(__name__)


async def select_ai_config(db: AsyncSession, model_id: Optional[int] = None) -> Optional[AIConfig]:
    """
    查询可用的 AIConfig。

    说明：
    - 当传入 model_id 时：仅返回该配置（且必须 enabled）；
    - 当不传 model_id 时：返回最近更新的启用配置（updated_at desc, id desc）。
    """
    if model_id:
        result = await db.execute(
            select(AIConfig).where(AIConfig.id == model_id, AIConfig.enabled == True)
        )
    else:
        result = await db.execute(
            select(AIConfig)
            .where(AIConfig.enabled == True)
            .order_by(AIConfig.updated_at.desc(), AIConfig.id.desc())
            .limit(1)
        )
    return result.scalar_one_or_none()


class AIService:
    """AI分析服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _normalize_agent_mode(mode: Optional[str]) -> str:
        """规范化 agent 执行模式（对齐 LearningSelfAgent 的 chat/do/think 语义）。"""
        m = (mode or "").strip().lower()
        if not m:
            return "agent"
        aliases = {
            "react": "agent",
            "default": "agent",
            "planner": "do",
        }
        return aliases.get(m, m)

    @staticmethod
    def _route_mode(question: str, stock_code: str = "") -> str:
        """
        简易模式路由（优先稳定/低成本）。

        - chat：闲聊/纯知识解释（不依赖实时数据）
        - do：明确任务/需要工具链（行情/K线/资金/公告等）
        - think：复杂开放任务（架构设计/多方案对比/系统优化等）
        """
        q = (question or "").strip()
        if not q:
            return "chat"

        # 强信号：出现股票代码/行情关键词，默认走 do（需要工具链信息）
        if stock_code:
            return "do"
        if re.search(r"\b(?:(sh|sz|hk|us)\s*)?\d{5,6}\b", q, flags=re.IGNORECASE):
            return "do"
        if any(k in q for k in ["行情", "k线", "K线", "分时", "资金", "龙虎榜", "北向", "公告", "研报", "筹码", "板块", "指数"]):
            return "do"

        # think：复杂/开放式
        if any(k in q for k in ["设计", "架构", "重构", "优化", "对比", "权衡", "方案", "路线图", "长期", "演进"]):
            return "think"

        # do：明确执行型指令
        if any(k in q for k in ["修复", "实现", "补齐", "完善", "改造", "生成", "编写", "重写", "迁移"]):
            return "do"

        return "chat"

    @staticmethod
    def _sanitize_session_id(session_id: Optional[str]) -> Optional[str]:
        """清洗 session_id（避免过长或包含异常字符导致存储/查询问题）。"""
        sid = (session_id or "").strip()
        if not sid:
            return None
        # 允许的字符：字母数字、下划线、短横线（便于 URL/前端存储）
        if not re.fullmatch(r"[a-zA-Z0-9_-]{8,64}", sid):
            return None
        return sid

    @staticmethod
    def _clamp_max_context_messages(value: int) -> int:
        """限制参与推理的历史消息条数，避免上下文无限增长。"""
        try:
            v = int(value)
        except Exception:
            v = 20
        # 下限 4：至少保留 2 轮 user/assistant；上限 60：避免长会话造成推理成本爆炸
        return max(4, min(60, v))

    @staticmethod
    def _build_session_title(title_hint: str, stock_code: str = "", stock_name: str = "") -> str:
        """生成会话标题（用于列表展示）。"""
        hint = (title_hint or "").strip().replace("\n", " ")
        hint = re.sub(r"\s+", " ", hint).strip()
        if stock_code and stock_name:
            prefix = f"{stock_name}({stock_code}) "
        elif stock_code:
            prefix = f"{stock_code} "
        else:
            prefix = ""
        title = (prefix + hint).strip()
        if not title:
            return "未命名会话"
        return title[:120]

    async def _get_or_create_session(
        self,
        session_id: Optional[str],
        *,
        mode: str,
        stock_code: str,
        stock_name: str,
        model_name: str,
        title_hint: str,
    ) -> AISession:
        """获取或创建会话（仅在需要时写库）。"""
        sid = self._sanitize_session_id(session_id) or uuid.uuid4().hex

        result = await self.db.execute(select(AISession).where(AISession.id == sid))
        session = result.scalar_one_or_none()

        if not session:
            session = AISession(
                id=sid,
                mode=mode or "agent",
                stock_code=stock_code or "",
                stock_name=stock_name or "",
                title=self._build_session_title(title_hint, stock_code=stock_code, stock_name=stock_name),
                model_name=model_name or "",
                message_count=0,
            )
            self.db.add(session)
            await self.db.commit()
            return session

        changed = False
        if mode and session.mode != mode:
            session.mode = mode
            changed = True
        if stock_code and session.stock_code != stock_code:
            session.stock_code = stock_code
            changed = True
        if stock_name and session.stock_name != stock_name:
            session.stock_name = stock_name
            changed = True
        if model_name and session.model_name != model_name:
            session.model_name = model_name
            changed = True
        if (not session.title) and title_hint:
            session.title = self._build_session_title(title_hint, stock_code=stock_code, stock_name=stock_name)
            changed = True

        if changed:
            await self.db.commit()

        return session

    async def _get_session_context_messages(self, session_id: str, limit: int) -> List[ChatMessage]:
        """获取会话用于推理的最近 N 条消息（按时间正序返回）。"""
        lim = self._clamp_max_context_messages(limit)
        result = await self.db.execute(
            select(AISessionMessage)
            .where(AISessionMessage.session_id == session_id)
            .where(AISessionMessage.role.in_(["user", "assistant", "system"]))
            .order_by(AISessionMessage.id.desc())
            .limit(lim)
        )
        rows = list(reversed(result.scalars().all()))
        return [ChatMessage(role=r.role, content=r.content) for r in rows]

    async def _append_session_message(
        self,
        session: AISession,
        *,
        role: str,
        content: str,
        name: str = "",
        extra: Optional[dict] = None,
    ) -> None:
        """追加会话消息并更新会话统计。"""
        payload = ""
        if extra is not None:
            try:
                payload = json.dumps(extra, ensure_ascii=False)
            except Exception:
                payload = ""

        msg = AISessionMessage(
            session_id=session.id,
            role=(role or "").lower() or "user",
            content=content or "",
            name=name or "",
            extra=payload,
        )
        self.db.add(msg)
        session.message_count = int(session.message_count or 0) + 1
        # 主动刷新更新时间，保证列表按最近活跃排序
        session.updated_at = datetime.now()
        await self.db.commit()

    async def _append_session_messages_bulk(
        self,
        session: AISession,
        messages: List[ChatMessage],
        *,
        allowed_roles: Optional[set[str]] = None,
    ) -> None:
        """批量写入会话消息（用于首次“引导/同步”历史，减少 commit 次数）。"""
        if not messages:
            return
        roles = allowed_roles or {"user", "assistant"}
        rows: list[AISessionMessage] = []
        for m in messages:
            role = (getattr(m, "role", "") or "").lower().strip()
            if role not in roles:
                continue
            content = getattr(m, "content", "") or ""
            if not content.strip():
                continue
            rows.append(
                AISessionMessage(
                    session_id=session.id,
                    role=role,
                    content=content,
                    name="",
                    extra="",
                )
            )
        if not rows:
            return
        for r in rows:
            self.db.add(r)
        session.message_count = int(session.message_count or 0) + len(rows)
        session.updated_at = datetime.now()
        await self.db.commit()

    async def _get_ai_config(self, model_id: Optional[int] = None) -> Optional[AIConfig]:
        """获取AI配置"""
        return await select_ai_config(self.db, model_id=model_id)

    async def _get_prompt_template(self, name: str) -> Optional[str]:
        """获取Prompt模板"""
        result = await self.db.execute(
            select(PromptTemplate).where(
                PromptTemplate.name == name,
                PromptTemplate.is_enabled == True
            )
        )
        template = result.scalar_one_or_none()
        return template.content if template else None

    @staticmethod
    def _should_enable_retrieval(question: str, stock_code: Optional[str] = None) -> bool:
        """轻量判断是否需要检索增强，避免每次对话都触发外部搜索"""
        if stock_code:
            return True
        q = (question or "").strip()
        if not q:
            return False
        # 启发式：包含“新闻/公告/最新”等词或包含 6 位代码时，认为需要检索
        trigger_keywords = [
            "最新", "消息", "新闻", "公告", "财报", "业绩", "预告", "快报",
            "研报", "评级", "目标价", "政策", "事件", "传闻", "利好", "利空",
            "减持", "增持", "回购", "中标", "订单", "处罚", "诉讼",
        ]
        if any(k in q for k in trigger_keywords):
            return True
        if re.search(r"\b(?:(sh|sz)\s*)?\d{6}\b", q, flags=re.IGNORECASE):
            return True
        return False

    async def _try_infer_stock_name(self, stock_code: str) -> str:
        """尝试从本地数据库推断股票名称（不触发外部行情请求）"""
        if not stock_code:
            return ""
        try:
            from app.services.stock_service import StockService

            svc = StockService(self.db)
            basic = await svc._get_basic_info(stock_code)
            return (basic or {}).get("name", "") or ""
        except Exception:
            return ""

    @cached(ttl_seconds=CacheTTL.NEWS, prefix="ai_retrieval_context")
    async def _build_retrieval_context(self, query: str) -> str:
        """构建检索上下文（带 TTL 缓存，降低外部 API 消耗）"""
        q = (query or "").strip()
        if not q:
            return ""

        from app.services.news_search_service import NewsSearchService

        service = NewsSearchService(self.db)
        try:
            items = await service.search(query=q, limit=8)
            if not items:
                return ""
            return service.format_as_context(query=q, items=items, max_items=5)
        finally:
            await service.close()

    @staticmethod
    def _inject_retrieval_context(messages: List[ChatMessage], context: str) -> List[ChatMessage]:
        """将检索上下文注入到消息列表中（尽量不影响用户原始提问）"""
        ctx = (context or "").strip()
        if not ctx:
            return messages

        injected = list(messages or [])
        # 保留已有 system message 的优先级：在连续 system 块之后插入检索上下文
        insert_at = 0
        for i, m in enumerate(injected):
            if (m.role or "").lower() == "system":
                insert_at = i + 1
            else:
                break

        injected.insert(insert_at, ChatMessage(role="system", content=f"{ctx}\n\n请基于以上检索信息回答；若信息不足请明确说明。"))
        return injected

    async def chat(self, request: ChatRequest) -> ChatResponse:
        """AI对话"""
        config = await self._get_ai_config(request.model_id)
        if not config:
            raise ValueError("没有可用的AI配置")

        from app.llm.client import LLMClient

        # 可能注入检索上下文（不改变历史 messages，避免污染前端展示）
        messages = request.messages
        try:
            if request.enable_retrieval and request.messages:
                question = request.messages[-1].content
                normalized_code = normalize_stock_code(request.stock_code or "")
                if self._should_enable_retrieval(question, normalized_code):
                    inferred_name = request.stock_name or await self._try_infer_stock_name(normalized_code)
                    query = " ".join([x for x in [inferred_name, normalized_code, question] if x]).strip() or question
                    ctx = await self._build_retrieval_context(query)
                    if ctx:
                        messages = self._inject_retrieval_context(request.messages, ctx)
        except Exception as e:
            logger.warning(f"构建检索上下文失败（将降级为纯对话）: {e}")

        client = LLMClient(config)
        try:
            response = await client.chat(messages)

            normalized_code = normalize_stock_code(request.stock_code or "")

            # 保存历史
            history = AIResponseResult(
                stock_code=normalized_code,
                stock_name=request.stock_name or "",
                question=request.messages[-1].content if request.messages else "",
                response=response.response,
                model_name=config.model_name,
                prompt_tokens=response.prompt_tokens,
                completion_tokens=response.completion_tokens,
                total_tokens=response.total_tokens,
                analysis_type="question",
            )
            self.db.add(history)
            await self.db.commit()

            return response
        finally:
            await client.close()

    async def chat_stream(self, request: ChatRequest) -> AsyncGenerator[StreamChunk, None]:
        """AI流式对话"""
        config = await self._get_ai_config(request.model_id)
        if not config:
            raise ValueError("没有可用的AI配置")

        from app.llm.client import LLMClient

        messages = request.messages
        try:
            if request.enable_retrieval and request.messages:
                question = request.messages[-1].content
                normalized_code = normalize_stock_code(request.stock_code or "")
                if self._should_enable_retrieval(question, normalized_code):
                    inferred_name = request.stock_name or await self._try_infer_stock_name(normalized_code)
                    query = " ".join([x for x in [inferred_name, normalized_code, question] if x]).strip() or question
                    ctx = await self._build_retrieval_context(query)
                    if ctx:
                        messages = self._inject_retrieval_context(request.messages, ctx)
        except Exception as e:
            logger.warning(f"构建检索上下文失败（将降级为纯对话）: {e}")

        client = LLMClient(config)

        full_response = ""
        try:
            async for chunk in client.chat_stream(messages):
                full_response += chunk.content
                yield chunk

            normalized_code = normalize_stock_code(request.stock_code or "")

            # 保存历史 - 必须在 try 块内，finally 之前
            history = AIResponseResult(
                stock_code=normalized_code,
                stock_name=request.stock_name or "",
                question=request.messages[-1].content if request.messages else "",
                response=full_response,
                model_name=config.model_name,
                analysis_type="question",
            )
            self.db.add(history)
            await self.db.commit()
        finally:
            await client.close()

    async def analyze_stock(self, request: StockAnalysisRequest) -> StockAnalysisResponse:
        """分析股票"""
        config = await self._get_ai_config(request.model_id)
        if not config:
            raise ValueError("没有可用的AI配置")

        request.stock_code = normalize_stock_code(request.stock_code)

        # 获取股票数据
        from app.services.stock_service import StockService
        stock_service = StockService(self.db)
        quotes = await stock_service.get_realtime_quotes([request.stock_code])

        # 构建Prompt
        stock_data = quotes[0] if quotes else None
        prompt = await self._build_analysis_prompt(request, stock_data)

        from app.llm.client import LLMClient
        from app.schemas.ai import ChatMessage

        client = LLMClient(config)
        try:
            response = await client.chat([ChatMessage(role="user", content=prompt)])

            # 保存历史
            history = AIResponseResult(
                stock_code=request.stock_code,
                stock_name=request.stock_name,
                question=prompt,
                response=response.response,
                model_name=config.model_name,
                prompt_tokens=response.prompt_tokens,
                completion_tokens=response.completion_tokens,
                total_tokens=response.total_tokens,
                analysis_type=request.analysis_type,
            )
            self.db.add(history)
            await self.db.commit()

            return StockAnalysisResponse(
                stock_code=request.stock_code,
                stock_name=request.stock_name,
                analysis=response.response,
                model_name=config.model_name,
                analysis_type=request.analysis_type,
                created_at=datetime.now(),
            )
        finally:
            await client.close()

    # ============ Simple Agent（简化版：数据分析→结论）===========

    @staticmethod
    def _build_simple_agent_system_prompt() -> str:
        """简化版 Agent 的 system prompt（不使用复杂的 Plan/ReAct/知识库编排）。"""
        return (
            "你是一个股票分析助手。你将收到用户问题与一份 JSON 数据上下文（已由系统抓取）。\n"
            "请只基于提供的数据进行分析，不要编造。\n\n"
            "输出要求（用中文）：\n"
            "1) 一句话结论：建议（买入/加仓/持有/减仓/观望/回避）+ 置信度（高/中/低）\n"
            "2) 关键依据：按 技术面/资金面/基本面/事件与风险 组织要点（每项 2-4 条）\n"
            "3) 关键价位：支撑/压力/止损/目标（若数据不足请写“无法给出/需更多数据”）\n"
            "4) 风险清单：3-6 条\n"
            "5) 数据缺失说明：如 missing 非空，需说明对结论的影响并降低置信度\n"
            "6) data_sources：最后用一行列出 data_sources（不要杜撰）\n"
        )

    @staticmethod
    def _build_simple_agent_user_prompt(question: str, context_json: str) -> str:
        q = (question or "").strip()
        ctx = (context_json or "").strip()
        return f"用户问题：{q}\n\n数据上下文(JSON)：\n{ctx}"

    async def simple_agent_chat(self, request: ChatRequest) -> ChatResponse:
        """简化版 Agent：拉取数据 → 交给 LLM 输出结论。"""
        config = await self._get_ai_config(request.model_id)
        if not config:
            raise ValueError("没有可用的AI配置")

        from app.llm.client import LLMClient
        from app.services.simple_agent_service import SimpleAgentService

        question = request.messages[-1].content if request.messages else ""
        builder = SimpleAgentService(self.db)
        ctx = await builder.build_context(
            question=question,
            stock_code=request.stock_code or "",
            stock_name=request.stock_name or "",
            enable_retrieval=bool(request.enable_retrieval),
        )

        messages = [
            ChatMessage(role="system", content=self._build_simple_agent_system_prompt()),
            ChatMessage(role="user", content=self._build_simple_agent_user_prompt(question, ctx.context_json)),
        ]

        client = LLMClient(config)
        try:
            response = await client.chat(messages)

            history = AIResponseResult(
                stock_code=normalize_stock_code(ctx.stock_code or request.stock_code or ""),
                stock_name=ctx.stock_name or request.stock_name or "",
                question=question,
                response=response.response,
                model_name=config.model_name,
                total_tokens=response.total_tokens,
                analysis_type="simple_agent",
            )
            self.db.add(history)
            await self.db.commit()

            return response
        finally:
            await client.close()

    async def simple_agent_chat_stream(self, request: ChatRequest) -> AsyncGenerator[StreamChunk, None]:
        """简化版 Agent（SSE）：拉取数据后流式输出 LLM 结论。"""
        config = await self._get_ai_config(request.model_id)
        if not config:
            raise ValueError("没有可用的AI配置")

        from app.llm.client import LLMClient
        from app.services.simple_agent_service import SimpleAgentService

        question = request.messages[-1].content if request.messages else ""
        builder = SimpleAgentService(self.db)
        ctx = await builder.build_context(
            question=question,
            stock_code=request.stock_code or "",
            stock_name=request.stock_name or "",
            enable_retrieval=bool(request.enable_retrieval),
        )

        messages = [
            ChatMessage(role="system", content=self._build_simple_agent_system_prompt()),
            ChatMessage(role="user", content=self._build_simple_agent_user_prompt(question, ctx.context_json)),
        ]

        client = LLMClient(config)
        full_response = ""
        try:
            async for chunk in client.chat_stream(messages):
                full_response += chunk.content
                yield chunk

            history = AIResponseResult(
                stock_code=normalize_stock_code(ctx.stock_code or request.stock_code or ""),
                stock_name=ctx.stock_name or request.stock_name or "",
                question=question,
                response=full_response,
                model_name=config.model_name,
                analysis_type="simple_agent",
            )
            self.db.add(history)
            await self.db.commit()
        finally:
            await client.close()

    async def _build_analysis_prompt(self, request: StockAnalysisRequest, stock_data) -> str:
        """构建分析Prompt - 支持模板"""
        # 模板优先级：
        # 1) request.prompt_template（外部指定模板名）
        # 2) 默认模板 stock_{analysis_type}
        template_candidates: List[str] = []
        if request.prompt_template:
            name = (request.prompt_template or "").strip()
            if name:
                template_candidates.append(name)
        template_candidates.append(f"stock_{request.analysis_type}")

        if stock_data:
            for template_name in template_candidates:
                template = await self._get_prompt_template(template_name)
                if not template:
                    continue
                try:
                    return template.format(
                        stock_code=request.stock_code,
                        stock_name=request.stock_name,
                        current_price=stock_data.current_price,
                        change_percent=stock_data.change_percent,
                        volume=stock_data.volume,
                        amount=stock_data.amount,
                        open_price=stock_data.open_price,
                        high_price=stock_data.high_price,
                        low_price=stock_data.low_price,
                        prev_close=stock_data.prev_close,
                    )
                except Exception as e:
                    # 模板格式化失败时回退到下一个候选模板/默认 Prompt，避免定时任务整体失败
                    logger.warning(f"Prompt模板格式化失败: template={template_name}, err={e}")
                    continue

        # 默认Prompt
        base_prompt = f"请分析股票 {request.stock_name}({request.stock_code}):\n\n"

        if stock_data:
            base_prompt += f"""当前价格: {stock_data.current_price}
涨跌幅: {stock_data.change_percent}%
今开: {stock_data.open_price}
最高: {stock_data.high_price}
最低: {stock_data.low_price}
昨收: {stock_data.prev_close}
成交量: {stock_data.volume}
成交额: {stock_data.amount}

"""

        if request.analysis_type == "summary":
            base_prompt += "请提供该股票的整体分析摘要，包括基本面、技术面和市场情绪。"
        elif request.analysis_type == "technical":
            base_prompt += "请提供该股票的技术分析，包括支撑位、压力位、趋势判断。"
        else:
            base_prompt += "请提供该股票的详细分析。"

        return base_prompt

    async def agent_chat(self, request: ChatRequest) -> AgentResponse:
        """Agent对话"""
        config = await self._get_ai_config(request.model_id)
        if not config:
            raise ValueError("没有可用的AI配置")

        from app.llm.agent import StockAgent
        from app.llm.client import LLMClient

        normalized_code = normalize_stock_code(request.stock_code or "")
        mode = self._normalize_agent_mode(getattr(request, "mode", None))
        if mode == "auto":
            # auto：按问题与是否有股票上下文做轻量路由
            last_q = request.messages[-1].content if request.messages else ""
            mode = self._route_mode(last_q, normalized_code)
        if mode not in {"chat", "do", "think", "agent"}:
            mode = "agent"

        title_hint = request.messages[-1].content if request.messages else ""
        session = await self._get_or_create_session(
            request.session_id,
            mode=mode,
            stock_code=normalized_code,
            stock_name=request.stock_name or "",
            model_name=config.model_name,
            title_hint=title_hint,
        )

        # 会话级多轮记忆：当客户端只传“本轮问题”时，从 DB 取回最近上下文拼接
        base_messages = request.messages
        if len(request.messages) <= 1:
            try:
                history_messages = await self._get_session_context_messages(
                    session.id,
                    request.max_context_messages,
                )
                base_messages = history_messages + request.messages
            except Exception as e:
                logger.warning(f"读取会话历史失败（将退化为仅本轮消息）: session_id={session.id}, err={e}")

        # 复用对话的“检索注入”逻辑，提升 Agent 的信息密度（尤其是新闻/公告类问题）
        messages = base_messages
        try:
            if request.enable_retrieval and messages:
                question = messages[-1].content
                if self._should_enable_retrieval(question, normalized_code):
                    inferred_name = request.stock_name or await self._try_infer_stock_name(normalized_code)
                    query = " ".join([x for x in [inferred_name, normalized_code, question] if x]).strip() or question
                    ctx = await self._build_retrieval_context(query)
                    if ctx:
                        messages = self._inject_retrieval_context(messages, ctx)
        except Exception as e:
            logger.warning(f"构建检索上下文失败（Agent 将降级为纯工具链）: {e}")

        # Knowledge retrieval（本地知识库分层检索，用于对齐 LearningSelfAgent 范式）
        knowledge_ctx = ""
        if mode in {"do", "think"}:
            try:
                from app.services.agent_knowledge_service import AgentKnowledgeService

                svc = AgentKnowledgeService(self.db)
                q = messages[-1].content if messages else ""
                query = " ".join([x for x in [request.stock_name or "", normalized_code, q] if x]).strip() or q
                bundle = await svc.retrieve(query=query, mode=mode)
                knowledge_ctx = bundle.context or ""
            except Exception as e:
                logger.warning(f"知识检索失败（可忽略，降级为无注入）: {e}")

        # 会话引导：若会话为空且客户端携带了多轮上下文，先同步到会话中（避免后续丢失记忆）
        try:
            if int(session.message_count or 0) == 0 and len(request.messages) > 1:
                seed = request.messages
                if (request.messages[-1].role or "").lower() == "user":
                    seed = request.messages[:-1]
                await self._append_session_messages_bulk(session, seed, allowed_roles={"user", "assistant"})
        except Exception as e:
            logger.warning(f"会话引导写入失败（可忽略）: session_id={session.id}, err={e}")

        # 先落库用户消息：即使后续 Agent 失败，也能保留会话轨迹
        try:
            if request.messages and (request.messages[-1].role or "").lower() == "user":
                await self._append_session_message(session, role="user", content=request.messages[-1].content)
        except Exception as e:
            logger.warning(f"写入会话用户消息失败（可忽略）: session_id={session.id}, err={e}")

        # chat 模式：不走工具链，仅普通对话（兼容 auto 路由）
        if mode == "chat":
            client = LLMClient(config)
            try:
                chat_resp = await client.chat(messages)
            finally:
                await client.close()

            response = AgentResponse(
                answer=chat_resp.response,
                thoughts=[],
                tool_calls=[],
                model_name=config.model_name,
                total_tokens=chat_resp.total_tokens,
            )
        else:
            agent = StockAgent(config, self.db)
            if mode == "do":
                response = await agent.run_do(
                    messages,
                    max_plan_steps=int(getattr(request, "max_plan_steps", 6) or 6),
                    knowledge_context=knowledge_ctx,
                )
            elif mode == "think":
                response = await agent.run_think(
                    messages,
                    max_plan_steps=int(getattr(request, "max_plan_steps", 6) or 6),
                    plan_candidates=int(getattr(request, "plan_candidates", 3) or 3),
                    knowledge_context=knowledge_ctx,
                )
            else:
                response = await agent.run(messages)

        # 落库 assistant 消息
        try:
            await self._append_session_message(session, role="assistant", content=response.answer)
        except Exception as e:
            logger.warning(f"写入会话助手消息失败（可忽略）: session_id={session.id}, err={e}")

        # 保存历史
        try:
            history = AIResponseResult(
                stock_code=normalized_code,
                stock_name=request.stock_name or "",
                question=request.messages[-1].content if request.messages else "",
                response=response.answer,
                model_name=config.model_name,
                total_tokens=response.total_tokens,
                analysis_type="agent",
            )
            self.db.add(history)
            await self.db.commit()
        except Exception as e:
            logger.warning(f"保存 Agent 历史失败（可忽略）: {e}")

        response.session_id = session.id

        # 落库 AgentRun（为后续评估/知识沉淀提供原料层）
        try:
            plan_json = ""
            if response.thoughts and (response.thoughts[0].thought or "").startswith("Plan("):
                plan_json = response.thoughts[0].observation or ""

            used_tools = []
            try:
                used_tools = [tc.tool_name for tc in (response.tool_calls or []) if tc and tc.tool_name]
            except Exception:
                used_tools = []

            evaluation_json = ""
            score = 0
            try:
                if bool(getattr(request, "enable_run_evaluation", True)):
                    from app.services.agent_evaluation_service import AgentEvaluationService

                    evaluator = AgentEvaluationService(config)
                    ev = await evaluator.evaluate(
                        mode=mode,
                        question=request.messages[-1].content if request.messages else "",
                        plan_json=plan_json,
                        used_tools=used_tools,
                        answer=response.answer,
                        knowledge_context=knowledge_ctx,
                        enable_llm=bool(getattr(request, "enable_llm_evaluation", False)),
                    )
                    evaluation_json = ev.evaluation_json or ""
                    score = int(ev.score or 0)
            except Exception as e:
                logger.warning(f"评估 AgentRun 失败（可忽略）: {e}")

            self.db.add(
                AgentRun(
                    session_id=session.id,
                    mode=mode,
                    stock_code=normalized_code,
                    stock_name=request.stock_name or "",
                    question=request.messages[-1].content if request.messages else "",
                    plan_json=plan_json,
                    used_tools=json.dumps(used_tools, ensure_ascii=False),
                    answer=response.answer,
                    model_name=config.model_name,
                    total_tokens=int(response.total_tokens or 0),
                    retrieval_context=knowledge_ctx,
                    evaluation=evaluation_json,
                    score=score,
                )
            )
            await self.db.commit()
        except Exception as e:
            logger.warning(f"保存 AgentRun 失败（可忽略）: {e}")

        return response

    async def agent_chat_stream(self, request: ChatRequest) -> AsyncGenerator[str, None]:
        """Agent流式对话"""
        config = await self._get_ai_config(request.model_id)
        if not config:
            raise ValueError("没有可用的AI配置")

        from app.llm.agent import StockAgent
        from app.llm.client import LLMClient

        normalized_code = normalize_stock_code(request.stock_code or "")
        mode = self._normalize_agent_mode(getattr(request, "mode", None))
        if mode == "auto":
            last_q = request.messages[-1].content if request.messages else ""
            mode = self._route_mode(last_q, normalized_code)
        if mode not in {"chat", "do", "think", "agent"}:
            mode = "agent"

        title_hint = request.messages[-1].content if request.messages else ""
        session = await self._get_or_create_session(
            request.session_id,
            mode=mode,
            stock_code=normalized_code,
            stock_name=request.stock_name or "",
            model_name=config.model_name,
            title_hint=title_hint,
        )

        # 会话级多轮记忆：当客户端只传“本轮问题”时，从 DB 取回最近上下文拼接
        base_messages = request.messages
        if len(request.messages) <= 1:
            try:
                history_messages = await self._get_session_context_messages(
                    session.id,
                    request.max_context_messages,
                )
                base_messages = history_messages + request.messages
            except Exception as e:
                logger.warning(f"读取会话历史失败（将退化为仅本轮消息）: session_id={session.id}, err={e}")

        messages = base_messages
        try:
            if request.enable_retrieval and messages:
                question = messages[-1].content
                if self._should_enable_retrieval(question, normalized_code):
                    inferred_name = request.stock_name or await self._try_infer_stock_name(normalized_code)
                    query = " ".join([x for x in [inferred_name, normalized_code, question] if x]).strip() or question
                    ctx = await self._build_retrieval_context(query)
                    if ctx:
                        messages = self._inject_retrieval_context(messages, ctx)
        except Exception as e:
            logger.warning(f"构建检索上下文失败（Agent 将降级为纯工具链）: {e}")

        # Knowledge retrieval（本地知识库分层检索，用于对齐 LearningSelfAgent 范式）
        knowledge_ctx = ""
        if mode in {"do", "think"}:
            try:
                from app.services.agent_knowledge_service import AgentKnowledgeService

                svc = AgentKnowledgeService(self.db)
                q = messages[-1].content if messages else ""
                query = " ".join([x for x in [request.stock_name or "", normalized_code, q] if x]).strip() or q
                bundle = await svc.retrieve(query=query, mode=mode)
                knowledge_ctx = bundle.context or ""
            except Exception as e:
                logger.warning(f"知识检索失败（可忽略，降级为无注入）: {e}")

        final_answer = ""
        plan_json = ""
        used_tools: list[str] = []
        # 先告知前端 session_id，便于本地持久化/恢复
        yield json.dumps({"type": "session", "session_id": session.id}, ensure_ascii=False)

        # 会话引导：若会话为空且客户端携带了多轮上下文，先同步到会话中（避免后续丢失记忆）
        try:
            if int(session.message_count or 0) == 0 and len(request.messages) > 1:
                seed = request.messages
                if (request.messages[-1].role or "").lower() == "user":
                    seed = request.messages[:-1]
                await self._append_session_messages_bulk(session, seed, allowed_roles={"user", "assistant"})
        except Exception as e:
            logger.warning(f"会话引导写入失败（可忽略）: session_id={session.id}, err={e}")

        # 先落库用户消息：即使后续 Agent 失败，也能保留会话轨迹
        try:
            if request.messages and (request.messages[-1].role or "").lower() == "user":
                await self._append_session_message(session, role="user", content=request.messages[-1].content)
        except Exception as e:
            logger.warning(f"写入会话用户消息失败（可忽略）: session_id={session.id}, err={e}")

        # chat 模式：不走工具链，直接流式输出 content，并在结束时补 final_answer
        if mode == "chat":
            llm = LLMClient(config)
            try:
                full = ""
                async for chunk in llm.chat_stream(messages):
                    if chunk.content:
                        full += chunk.content
                        yield json.dumps({"type": "content", "content": chunk.content, "done": chunk.done}, ensure_ascii=False)
                final_answer = full
                yield json.dumps({"type": "final_answer", "content": full}, ensure_ascii=False)
            finally:
                await llm.close()
        else:
            agent = StockAgent(config, self.db)
            async for chunk in agent.run_mode_stream(
                messages,
                mode=mode,
                max_plan_steps=int(getattr(request, "max_plan_steps", 6) or 6),
                plan_candidates=int(getattr(request, "plan_candidates", 3) or 3),
                knowledge_context=knowledge_ctx,
            ):
                # 尝试从事件中捕获最终答案，用于落库；解析失败不影响对前端输出
                try:
                    import json as _json

                    evt = _json.loads(chunk)
                    if isinstance(evt, dict) and evt.get("type") == "final_answer":
                        final_answer = str(evt.get("content", "") or "")
                    elif isinstance(evt, dict) and evt.get("type") == "plan":
                        try:
                            plan_json = json.dumps(evt.get("plan") or {}, ensure_ascii=False)
                        except Exception:
                            plan_json = ""
                    elif isinstance(evt, dict) and evt.get("type") == "tool_call":
                        tool = str(evt.get("tool", "") or "")
                        if tool:
                            used_tools.append(tool)
                except Exception:
                    pass
                yield chunk

        # 流式结束后写入（避免阻塞 SSE 输出）
        if final_answer:
            # 落库 assistant 消息
            try:
                await self._append_session_message(session, role="assistant", content=final_answer)
            except Exception as e:
                logger.warning(f"写入会话助手消息失败（可忽略）: session_id={session.id}, err={e}")

            # 保存“单次分析历史”（兼容既有历史页）
            try:
                history = AIResponseResult(
                    stock_code=normalized_code,
                    stock_name=request.stock_name or "",
                    question=request.messages[-1].content if request.messages else "",
                    response=final_answer,
                    model_name=config.model_name,
                    analysis_type="agent",
                )
                self.db.add(history)
                await self.db.commit()
            except Exception as e:
                logger.warning(f"保存 Agent 历史失败（可忽略）: {e}")

        # 落库 AgentRun（流式结束后写入，避免阻塞 SSE 输出）
        if final_answer:
            try:
                unique_tools = list(dict.fromkeys([t for t in used_tools if t]))

                evaluation_json = ""
                score = 0
                try:
                    if bool(getattr(request, "enable_run_evaluation", True)):
                        from app.services.agent_evaluation_service import AgentEvaluationService

                        evaluator = AgentEvaluationService(config)
                        ev = await evaluator.evaluate(
                            mode=mode,
                            question=request.messages[-1].content if request.messages else "",
                            plan_json=plan_json,
                            used_tools=unique_tools,
                            answer=final_answer,
                            knowledge_context=knowledge_ctx,
                            enable_llm=bool(getattr(request, "enable_llm_evaluation", False)),
                        )
                        evaluation_json = ev.evaluation_json or ""
                        score = int(ev.score or 0)
                except Exception as e:
                    logger.warning(f"评估 AgentRun 失败（可忽略）: {e}")

                self.db.add(
                    AgentRun(
                        session_id=session.id,
                        mode=mode,
                        stock_code=normalized_code,
                        stock_name=request.stock_name or "",
                        question=request.messages[-1].content if request.messages else "",
                        plan_json=plan_json,
                        used_tools=json.dumps(unique_tools, ensure_ascii=False),
                        answer=final_answer,
                        model_name=config.model_name,
                        retrieval_context=knowledge_ctx,
                        evaluation=evaluation_json,
                        score=score,
                    )
                )
                await self.db.commit()
            except Exception as e:
                logger.warning(f"保存 AgentRun 失败（可忽略）: {e}")

    # ============ 股票摘要分析 ============

    async def generate_stock_summary(
        self,
        stock_code: str,
        stock_name: str,
        model_id: Optional[int] = None
    ) -> str:
        """生成股票摘要"""
        stock_code = normalize_stock_code(stock_code)

        from app.services.stock_service import StockService

        stock_service = StockService(self.db)

        # 获取实时行情
        quotes = await stock_service.get_realtime_quotes([stock_code])
        quote = quotes[0] if quotes else None

        # 获取K线数据
        kline = await stock_service.get_kline(stock_code, "day", 20)

        # 获取资金流向
        money_flow = await stock_service.get_money_flow(stock_code, 5)

        # 构建摘要Prompt
        prompt = f"""请为以下股票生成投资摘要:

## 基本信息
- 股票代码: {stock_code}
- 股票名称: {stock_name}

## 实时行情
"""
        if quote:
            prompt += f"""- 当前价格: {quote.current_price}
- 涨跌幅: {quote.change_percent}%
- 成交量: {quote.volume}
- 成交额: {quote.amount}
"""

        prompt += "\n## 近期K线\n"
        if kline and kline.data:
            for k in kline.data[-5:]:
                prompt += f"- {k.date}: 开{k.open} 高{k.high} 低{k.low} 收{k.close}\n"

        prompt += "\n## 资金流向\n"
        if money_flow:
            for flow in money_flow[-5:]:
                prompt += f"- {flow.get('date')}: 主力净流入 {flow.get('main_net_inflow', 0):.2f}万\n"

        prompt += """
请从以下几个方面进行分析:
1. 当前走势评价
2. 技术面分析
3. 资金面分析
4. 风险提示
5. 投资建议

请用简洁专业的语言回答。"""

        # 调用AI
        config = await self._get_ai_config(model_id)
        if not config:
            raise ValueError("没有可用的AI配置")

        from app.llm.client import LLMClient
        from app.schemas.ai import ChatMessage

        llm_client = LLMClient(config)
        try:
            response = await llm_client.chat([ChatMessage(role="user", content=prompt)])

            # 保存历史
            history = AIResponseResult(
                stock_code=stock_code,
                stock_name=stock_name,
                question="股票摘要分析",
                response=response.response,
                model_name=config.model_name,
                prompt_tokens=response.prompt_tokens,
                completion_tokens=response.completion_tokens,
                total_tokens=response.total_tokens,
                analysis_type="summary",
            )
            self.db.add(history)
            await self.db.commit()

            return response.response
        finally:
            await llm_client.close()

    # ============ AI推荐股票 ============

    async def get_ai_recommendations(
        self,
        limit: int = 10,
        model_id: Optional[int] = None
    ) -> List[AIRecommendStock]:
        """获取AI推荐股票"""
        # 获取现有有效推荐
        result = await self.db.execute(
            select(AIRecommendStock)
            .where(AIRecommendStock.is_valid == True)
            .order_by(AIRecommendStock.score.desc())
            .limit(limit)
        )
        return result.scalars().all()

    async def generate_ai_recommendations(
        self,
        model_id: Optional[int] = None
    ) -> List[AIRecommendStock]:
        """生成AI推荐股票"""
        from app.services.search_service import SearchService

        search_service = SearchService(self.db)

        # 获取多个维度的股票
        hot_stocks = []

        # 涨停股
        result = await search_service.search_by_words("涨停")
        hot_stocks.extend(result.get("results", [])[:5])

        # 主力资金流入
        result = await search_service.search_by_words("主力资金流入")
        hot_stocks.extend(result.get("results", [])[:5])

        # 量比异动
        result = await search_service.search_by_words("量比大于2")
        hot_stocks.extend(result.get("results", [])[:5])

        # 去重
        seen_codes = set()
        unique_stocks = []
        for stock in hot_stocks:
            code = stock.get("stock_code", "")
            if code and code not in seen_codes:
                seen_codes.add(code)
                unique_stocks.append(stock)

        if not unique_stocks:
            return []

        # 构建AI分析Prompt
        stock_list = "\n".join([
            f"- {s.get('stock_code')}: {s.get('stock_name')} 涨幅{s.get('change_percent', 0):.2f}%"
            for s in unique_stocks[:15]
        ])

        prompt = f"""请从以下股票中选出最值得关注的5只股票,并给出推荐理由和评分:

{stock_list}

请按以下JSON格式返回:
[
  {{"stock_code": "代码", "stock_name": "名称", "score": 85, "reason": "推荐理由", "recommend_type": "buy/hold/sell", "target_price": 目标价, "stop_loss_price": 止损价}},
  ...
]

注意:
1. score范围0-100,越高越推荐
2. recommend_type: buy(买入), hold(持有), sell(卖出)
3. 只返回JSON数组,不要其他内容"""

        config = await self._get_ai_config(model_id)
        if not config:
            raise ValueError("没有可用的AI配置")

        from app.llm.client import LLMClient
        from app.schemas.ai import ChatMessage
        import json

        llm_client = LLMClient(config)
        try:
            response = await llm_client.chat([ChatMessage(role="user", content=prompt)])

            # 解析AI返回的JSON
            recommendations = []
            try:
                # 提取JSON部分
                content = response.response
                start = content.find("[")
                end = content.rfind("]") + 1
                if start >= 0 and end > start:
                    json_str = content[start:end]
                    data = json.loads(json_str)

                    # 将旧推荐标记为无效
                    await self.db.execute(
                        AIRecommendStock.__table__.update()
                        .values(is_valid=False)
                    )

                    # 保存新推荐
                    for item in data:
                        rec = AIRecommendStock(
                            stock_code=item.get("stock_code", ""),
                            stock_name=item.get("stock_name", ""),
                            score=item.get("score", 0),
                            reason=item.get("reason", ""),
                            recommend_type=item.get("recommend_type", "hold"),
                            target_price=item.get("target_price", 0),
                            stop_loss_price=item.get("stop_loss_price", 0),
                            is_valid=True,
                            model_name=config.model_name,
                        )
                        self.db.add(rec)
                        recommendations.append(rec)

                    await self.db.commit()
            except Exception as e:
                # 解析失败,记录日志并返回空列表
                import logging
                logging.getLogger(__name__).warning(f"解析AI推荐结果失败: {e}")

            return recommendations
        finally:
            await llm_client.close()

    # ============ 情感分析 ============

    async def analyze_sentiment(
        self,
        text: str,
        model_id: Optional[int] = None
    ) -> dict:
        """分析文本情感"""
        prompt = f"""请分析以下文本的情感倾向:

{text}

请按以下JSON格式返回:
{{
  "sentiment": "positive/negative/neutral",
  "score": 0.8,
  "keywords": ["关键词1", "关键词2"],
  "summary": "情感分析摘要"
}}

注意:
1. sentiment: positive(积极), negative(消极), neutral(中性)
2. score: 情感强度,范围0-1
3. 只返回JSON,不要其他内容"""

        config = await self._get_ai_config(model_id)
        if not config:
            raise ValueError("没有可用的AI配置")

        from app.llm.client import LLMClient
        from app.schemas.ai import ChatMessage
        import json

        client = LLMClient(config)
        try:
            response = await client.chat([ChatMessage(role="user", content=prompt)])

            # 解析结果
            try:
                content = response.response
                start = content.find("{")
                end = content.rfind("}") + 1
                if start >= 0 and end > start:
                    json_str = content[start:end]
                    return json.loads(json_str)
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"解析情感分析结果失败: {e}")

            return {
                "sentiment": "neutral",
                "score": 0.5,
                "keywords": [],
                "summary": "无法分析"
            }
        finally:
            await client.close()

    async def analyze_news_sentiment(
        self,
        stock_code: str,
        model_id: Optional[int] = None
    ) -> dict:
        """分析股票相关新闻的情感"""
        from app.services.news_service import NewsService

        news_service = NewsService(self.db)
        normalized_code = normalize_stock_code(stock_code or "")
        inferred_name = await self._try_infer_stock_name(normalized_code)
        keywords = " ".join([x for x in [inferred_name, normalized_code] if x]).strip() or stock_code
        news = await news_service.search_news(keywords, limit=10)

        if not news.items:
            return {
                "overall_sentiment": "neutral",
                "positive_count": 0,
                "negative_count": 0,
                "neutral_count": 0,
                "news_count": 0,
            }

        # 分析每条新闻
        sentiments = []
        for item in news.items:
            sentiment = await self.analyze_sentiment(
                f"{item.title}\n{item.content or ''}",
                model_id
            )
            sentiments.append(sentiment)

        # 统计
        positive = sum(1 for s in sentiments if s.get("sentiment") == "positive")
        negative = sum(1 for s in sentiments if s.get("sentiment") == "negative")
        neutral = len(sentiments) - positive - negative

        # 综合情感
        if positive > negative * 2:
            overall = "positive"
        elif negative > positive * 2:
            overall = "negative"
        else:
            overall = "neutral"

        return {
            "overall_sentiment": overall,
            "positive_count": positive,
            "negative_count": negative,
            "neutral_count": neutral,
            "news_count": len(sentiments),
        }

    # ============ 分享分析 ============

    async def share_analysis(
        self,
        stock_code: str,
        stock_name: str,
        content: Optional[str] = None
    ) -> str:
        """分享股票分析结果"""
        import hashlib
        from datetime import datetime

        # 如果没有提供内容，获取最新的分析结果
        if not content:
            result = await self.db.execute(
                select(AIResponseResult)
                .where(AIResponseResult.stock_code == stock_code)
                .order_by(AIResponseResult.created_at.desc())
                .limit(1)
            )
            item = result.scalar_one_or_none()
            if item:
                content = item.response
            else:
                content = f"{stock_name}({stock_code}) 暂无分析内容"

        # 生成分享ID
        share_data = f"{stock_code}_{stock_name}_{datetime.now().isoformat()}"
        share_id = hashlib.md5(share_data.encode()).hexdigest()[:12]

        # 实际应用中这里应该保存到数据库并返回可访问的URL
        # 这里简化处理，返回分享ID
        return f"share_{share_id}"

    # ============ 新闻AI总结 ============

    async def summary_news(
        self,
        question: str,
        model_id: Optional[int] = None
    ) -> str:
        """AI总结新闻资讯"""
        from app.services.news_service import NewsService

        news_service = NewsService(self.db)

        # 获取最新新闻
        news = await news_service.get_latest_news(None, 20)

        # 构建Prompt
        news_content = "\n".join([
            f"- [{item.title}] {item.content or ''}"
            for item in news.items[:15]
        ])

        prompt = f"""请根据以下最新财经资讯，回答用户的问题。

## 最新资讯
{news_content}

## 用户问题
{question}

请用专业、简洁的语言回答。如果问题与资讯无关，请基于你的专业知识回答。"""

        config = await self._get_ai_config(model_id)
        if not config:
            raise ValueError("没有可用的AI配置")

        from app.llm.client import LLMClient
        from app.schemas.ai import ChatMessage

        client = LLMClient(config)
        response = await client.chat([ChatMessage(role="user", content=prompt)])

        return response.response

    async def summary_news_stream(
        self,
        question: str,
        model_id: Optional[int] = None
    ) -> AsyncGenerator[str, None]:
        """AI总结新闻资讯 (流式)"""
        from app.services.news_service import NewsService

        news_service = NewsService(self.db)

        # 获取最新新闻
        news = await news_service.get_latest_news(None, 20)

        # 构建Prompt
        news_content = "\n".join([
            f"- [{item.title}] {item.content or ''}"
            for item in news.items[:15]
        ])

        prompt = f"""请根据以下最新财经资讯，回答用户的问题。

## 最新资讯
{news_content}

## 用户问题
{question}

请用专业、简洁的语言回答。如果问题与资讯无关，请基于你的专业知识回答。"""

        config = await self._get_ai_config(model_id)
        if not config:
            raise ValueError("没有可用的AI配置")

        from app.llm.client import LLMClient
        from app.schemas.ai import ChatMessage

        client = LLMClient(config)

        async for chunk in client.chat_stream([ChatMessage(role="user", content=prompt)]):
            yield chunk.content
