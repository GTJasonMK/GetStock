import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.database import async_session_maker
from app.main import app
from app.models.ai import AIResponseResult
from app.models.ai_session import AISession, AISessionMessage
from app.models.settings import AIConfig
from app.schemas.ai import AgentResponse, ChatMessage, ChatRequest


async def _clear_tables():
    async with async_session_maker() as db:
        await db.execute(delete(AISessionMessage))
        await db.execute(delete(AISession))
        await db.execute(delete(AIResponseResult))
        await db.execute(delete(AIConfig))
        await db.commit()


@pytest.mark.asyncio
async def test_agent_session_persists_messages_and_supports_server_side_memory(monkeypatch):
    """
    目标：
    - 第一次调用不传 session_id：自动创建会话并返回 session_id
    - 第二次调用只传本轮问题 + session_id：后端能从 DB 拼接历史，实现多轮记忆
    """
    await _clear_tables()

    async with async_session_maker() as db:
        db.add(AIConfig(
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
        ))
        await db.commit()

        captured: list[list[ChatMessage]] = []

        class FakeStockAgent:
            def __init__(self, config, db_session):
                self.config = config
                self.db = db_session

            async def run(self, messages):
                captured.append(messages)
                return AgentResponse(
                    answer=f"ok-{len(captured)}",
                    thoughts=[],
                    tool_calls=[],
                    model_name="fake",
                    total_tokens=1,
                )

        import app.llm.agent as agent_module
        monkeypatch.setattr(agent_module, "StockAgent", FakeStockAgent)

        from app.services.ai_service import AIService

        service = AIService(db)

        # 1) 首轮：创建会话
        first = await service.agent_chat(ChatRequest(
            messages=[ChatMessage(role="user", content="第一问")],
            enable_retrieval=False,
        ))
        assert first.answer == "ok-1"
        assert first.session_id

        # 2) 次轮：只传本轮问题 + session_id，验证后端拼接历史
        second = await service.agent_chat(ChatRequest(
            session_id=first.session_id,
            messages=[ChatMessage(role="user", content="第二问")],
            enable_retrieval=False,
        ))
        assert second.answer == "ok-2"
        assert second.session_id == first.session_id

        # 第二次传给 agent 的 messages 应包含：user(第一问)、assistant(ok-1)、user(第二问)
        assert len(captured) == 2
        assert [(m.role, m.content) for m in captured[1]] == [
            ("user", "第一问"),
            ("assistant", "ok-1"),
            ("user", "第二问"),
        ]

        sessions = (await db.execute(select(AISession))).scalars().all()
        assert len(sessions) == 1
        assert sessions[0].id == first.session_id
        assert int(sessions[0].message_count or 0) == 4

        msgs = (await db.execute(
            select(AISessionMessage).where(AISessionMessage.session_id == first.session_id).order_by(AISessionMessage.id)
        )).scalars().all()
        assert [(m.role, m.content) for m in msgs] == [
            ("user", "第一问"),
            ("assistant", "ok-1"),
            ("user", "第二问"),
            ("assistant", "ok-2"),
        ]


@pytest.mark.asyncio
async def test_session_api_returns_messages_in_order(monkeypatch):
    await _clear_tables()

    # 先用 service 写入一段会话
    async with async_session_maker() as db:
        db.add(AIConfig(
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
        ))
        await db.commit()

        class FakeStockAgent:
            def __init__(self, config, db_session):
                self.config = config
                self.db = db_session

            async def run(self, messages):
                return AgentResponse(answer="ok", thoughts=[], tool_calls=[], model_name="fake", total_tokens=1)

        import app.llm.agent as agent_module
        monkeypatch.setattr(agent_module, "StockAgent", FakeStockAgent)

        from app.services.ai_service import AIService

        service = AIService(db)
        resp = await service.agent_chat(ChatRequest(
            messages=[ChatMessage(role="user", content="hello")],
            enable_retrieval=False,
        ))
        assert resp.session_id
        sid = resp.session_id

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        detail = await ac.get(f"/api/v1/ai/sessions/{sid}", params={"limit": 1000})
        assert detail.status_code == 200
        payload = detail.json()
        assert payload["code"] == 0
        data = payload["data"]
        assert data["session"]["id"] == sid
        assert [(m["role"], m["content"]) for m in data["messages"]] == [
            ("user", "hello"),
            ("assistant", "ok"),
        ]
