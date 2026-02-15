import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.database import async_session_maker
from app.main import app
from app.models.stock import FollowedStock


@pytest.mark.asyncio
async def test_stock_follow_returns_normalized_stock_code():
    async with async_session_maker() as db:
        await db.execute(delete(FollowedStock))
        db.add(FollowedStock(stock_code="SH600000", stock_name="浦发银行"))
        await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/stock/follow")
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["code"] == 0
        assert payload["data"][0]["stock_code"] == "sh600000"
