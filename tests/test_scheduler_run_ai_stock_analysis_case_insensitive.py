from datetime import datetime

import pytest
from sqlalchemy import delete

from app.database import async_session_maker
from app.models.settings import AIConfig
from app.models.stock import FollowedStock
from app.schemas.ai import StockAnalysisResponse
from app.tasks import scheduler as scheduler_module


@pytest.mark.asyncio
async def test_run_ai_stock_analysis_matches_followed_stock_case_insensitive(monkeypatch):
    async with async_session_maker() as db:
        await db.execute(delete(FollowedStock))
        await db.execute(delete(AIConfig))

        per_stock = AIConfig(name="per-stock", enabled=True)
        per_stock.updated_at = datetime(2020, 1, 1)
        default = AIConfig(name="default", enabled=True)
        default.updated_at = datetime(2026, 1, 1)

        db.add(per_stock)
        db.add(default)
        await db.flush()

        db.add(FollowedStock(
            stock_code="SH600000",
            stock_name="浦发银行",
            ai_config_id=per_stock.id,
        ))
        await db.commit()

    import app.services.ai_service as ai_service_module

    called = {}

    async def fake_analyze_stock(self, request):
        called["stock_code"] = request.stock_code
        called["stock_name"] = request.stock_name
        called["model_id"] = request.model_id
        return StockAnalysisResponse(
            stock_code=request.stock_code,
            stock_name=request.stock_name,
            analysis="ok",
            model_name="fake",
            analysis_type=request.analysis_type,
            created_at=datetime.now(),
        )

    monkeypatch.setattr(ai_service_module.AIService, "analyze_stock", fake_analyze_stock)

    await scheduler_module.run_ai_stock_analysis("sh600000")

    assert called["stock_code"] == "sh600000"
    assert called["stock_name"] == "浦发银行"
    assert called["model_id"] == per_stock.id

