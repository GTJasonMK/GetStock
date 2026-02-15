import pytest
from sqlalchemy import delete, select

from app.database import async_session_maker
from app.models.ai import AIResponseResult
from app.models.settings import AIConfig
from app.schemas.ai import ChatMessage, ChatRequest, ChatResponse


@pytest.mark.asyncio
async def test_simple_agent_chat_saves_history(monkeypatch):
    async with async_session_maker() as db:
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

        class FakeLLMClient:
            def __init__(self, config):
                self.config = config

            async def chat(self, messages):
                return ChatResponse(response="ok", model_name=self.config.model_name, total_tokens=1)

            async def close(self):
                return None

        import app.llm.client as llm_client_module

        monkeypatch.setattr(llm_client_module, "LLMClient", FakeLLMClient)

        from app.services.simple_agent_service import SimpleAgentContext

        async def fake_build_context(self, *, question, stock_code="", stock_name="", enable_retrieval=False):
            return SimpleAgentContext(
                stock_code="sh600000",
                stock_name="浦发银行",
                context_json='{"ok":true}',
                data_sources=["stock_detail"],
                missing=[],
            )

        import app.services.simple_agent_service as simple_service_module

        monkeypatch.setattr(simple_service_module.SimpleAgentService, "build_context", fake_build_context)

        from app.services.ai_service import AIService

        svc = AIService(db)
        resp = await svc.simple_agent_chat(
            ChatRequest(messages=[ChatMessage(role="user", content="请分析 sh600000")], enable_retrieval=False)
        )
        assert resp.response == "ok"

        rows = (await db.execute(select(AIResponseResult).order_by(AIResponseResult.id))).scalars().all()
        assert len(rows) == 1
        assert rows[0].analysis_type == "simple_agent"
        assert rows[0].stock_code == "sh600000"
        assert rows[0].stock_name == "浦发银行"

