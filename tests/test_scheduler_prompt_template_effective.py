import pytest
from sqlalchemy import delete

from app.database import async_session_maker
from app.models.ai import PromptTemplate
from app.models.settings import AIConfig
from app.models.stock import FollowedStock
from app.schemas.ai import ChatResponse
from app.schemas.stock import StockQuote
from app.services.stock_service import StockService
from app.tasks import scheduler as scheduler_module


@pytest.mark.asyncio
async def test_run_ai_stock_analysis_uses_prompt_template_name(monkeypatch):
    captured_prompt = {"value": None}

    async with async_session_maker() as db:
        await db.execute(delete(PromptTemplate))
        await db.execute(delete(AIConfig))
        await db.execute(delete(FollowedStock))

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
        db.add(FollowedStock(stock_code="sh600000", stock_name="浦发银行"))
        db.add(PromptTemplate(
            name="my_template",
            template_type="custom",
            content="MYTEMPLATE {stock_code}-{stock_name}-{current_price}",
            description="test",
            is_system=False,
            is_enabled=True,
            sort_order=0,
        ))
        await db.commit()

    async def fake_get_realtime_quotes(self, codes):
        assert codes == ["sh600000"]
        return [
            StockQuote(
                stock_code="sh600000",
                stock_name="浦发银行",
                current_price=11.0,
                change_percent=1.0,
                change_amount=0.1,
                open_price=10.8,
                high_price=11.2,
                low_price=10.7,
                prev_close=10.9,
                volume=123456,
                amount=987654.0,
                update_time="",
            )
        ]

    monkeypatch.setattr(StockService, "get_realtime_quotes", fake_get_realtime_quotes)

    class FakeLLMClient:
        def __init__(self, config):
            self.config = config

        async def chat(self, messages):
            captured_prompt["value"] = messages[0].content if messages else None
            return ChatResponse(response="ok", model_name=self.config.model_name, total_tokens=1)

        async def close(self):
            return None

    import app.llm.client as llm_client_module
    monkeypatch.setattr(llm_client_module, "LLMClient", FakeLLMClient)

    await scheduler_module.run_ai_stock_analysis("sh600000", prompt_template="my_template")

    assert captured_prompt["value"] == "MYTEMPLATE sh600000-浦发银行-11.0"

