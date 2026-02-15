import pytest
from sqlalchemy import delete

from app.database import async_session_maker
from app.models.ai import AIResponseResult
from app.models.ai_session import AISession, AISessionMessage
from app.models.agent_knowledge import AgentRun
from app.models.settings import AIConfig
from app.schemas.ai import AgentResponse, ChatMessage, ChatRequest


@pytest.mark.asyncio
async def test_ai_service_do_mode_passes_knowledge_context_into_planner(monkeypatch):
    async with async_session_maker() as db:
        # 清理可能影响断言的表
        await db.execute(delete(AISessionMessage))
        await db.execute(delete(AISession))
        await db.execute(delete(AgentRun))
        await db.execute(delete(AIResponseResult))
        await db.execute(delete(AIConfig))
        await db.commit()

        db.add(
            AIConfig(
                name="test",
                enabled=True,
                base_url="https://api.openai.com/v1",
                api_key="test-key",
                model_name="gpt-4",
                max_tokens=16,
                temperature=0.0,
                timeout=3,
                http_proxy="",
                http_proxy_enabled=False,
            )
        )
        await db.commit()

        captured: dict[str, str] = {"knowledge": ""}

        async def fake_run_do(self, messages, *, max_plan_steps=6, knowledge_context=""):
            captured["knowledge"] = str(knowledge_context or "")
            return AgentResponse(answer="ok", thoughts=[], tool_calls=[], model_name="fake", total_tokens=1)

        import app.llm.agent as agent_module
        monkeypatch.setattr(agent_module.StockAgent, "run_do", fake_run_do)

        from app.services.ai_service import AIService

        service = AIService(db)
        resp = await service.agent_chat(
            ChatRequest(
                mode="do",
                enable_retrieval=False,
                messages=[ChatMessage(role="user", content="请分析 sh600000 资金流向，并给风险提示")],
            )
        )

        assert resp.answer == "ok"
        # 知识检索上下文应已注入（至少包含技能块）
        assert "【技能(方法论)】" in captured["knowledge"]

