import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.database import async_session_maker
from app.main import app
from app.models.stock import FollowedStock


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_set_stock_ai_cron_rejects_invalid_expression(client):
    async with async_session_maker() as db:
        await db.execute(delete(FollowedStock).where(FollowedStock.stock_code == "sh600000"))
        db.add(FollowedStock(stock_code="sh600000", stock_name="Test"))
        await db.commit()

    resp = await client.put(
        "/api/v1/stock/follow/sh600000/cron",
        params={"cron_expression": "bad-cron"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_set_stock_ai_cron_accepts_5_field_expression(client):
    async with async_session_maker() as db:
        await db.execute(delete(FollowedStock).where(FollowedStock.stock_code == "sh600001"))
        db.add(FollowedStock(stock_code="sh600001", stock_name="Test"))
        await db.commit()

    resp = await client.put(
        "/api/v1/stock/follow/sh600001/cron",
        params={"cron_expression": "0 15 * * 1-5"},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["code"] == 0
