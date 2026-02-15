import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.database import async_session_maker
from app.main import app
from app.models.ai import AIResponseResult
from app.models.settings import AIConfig
from app.schemas.ai import ChatMessage, ChatRequest, ChatResponse


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


async def _clear_ai_tables():
    async with async_session_maker() as db:
        await db.execute(delete(AIResponseResult))
        await db.execute(delete(AIConfig))
        await db.commit()


@pytest.mark.asyncio
async def test_ai_history_query_and_clear_are_case_insensitive_and_normalized(client):
    await _clear_ai_tables()

    async with async_session_maker() as db:
        db.add(AIResponseResult(
            stock_code="SH600000",
            stock_name="浦发银行",
            question="q",
            response="a",
            model_name="test",
            analysis_type="question",
        ))
        await db.commit()

    history_resp = await client.get("/api/v1/ai/history", params={"stock_code": "sh600000"})
    assert history_resp.status_code == 200
    data = history_resp.json()["data"]
    assert data["total"] == 1
    assert data["items"][0]["stock_code"] == "SH600000"

    clear_resp = await client.delete("/api/v1/ai/history", params={"stock_code": "sh600000"})
    assert clear_resp.status_code == 200
    assert clear_resp.json()["code"] == 0

    async with async_session_maker() as db:
        count = (await db.execute(select(AIResponseResult))).scalars().all()
        assert count == []


@pytest.mark.asyncio
async def test_ai_service_chat_saves_normalized_stock_code(monkeypatch):
    await _clear_ai_tables()

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

        class FakeLLMClient:
            def __init__(self, config):
                self.config = config

            async def chat(self, messages):
                return ChatResponse(response="ok", model_name=self.config.model_name, total_tokens=1)

            async def close(self):
                return None

        import app.llm.client as llm_client_module
        monkeypatch.setattr(llm_client_module, "LLMClient", FakeLLMClient)

        from app.services.ai_service import AIService

        service = AIService(db)
        resp = await service.chat(ChatRequest(
            messages=[ChatMessage(role="user", content="hi")],
            stock_code="SH600000",
            stock_name="浦发银行",
        ))
        assert resp.response == "ok"

        histories = (await db.execute(select(AIResponseResult).order_by(AIResponseResult.id))).scalars().all()
        assert len(histories) == 1
        assert histories[0].stock_code == "sh600000"
