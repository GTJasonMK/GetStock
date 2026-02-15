import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.database import async_session_maker
from app.main import app
from app.models.stock import FollowedStock, Group, GroupStock


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


async def _clear_group_and_followed_tables():
    async with async_session_maker() as db:
        await db.execute(delete(GroupStock))
        await db.execute(delete(Group))
        await db.execute(delete(FollowedStock))
        await db.commit()


@pytest.mark.asyncio
async def test_settings_import_is_idempotent_and_normalizes_stock_codes(client):
    await _clear_group_and_followed_tables()

    payload = {
        "followed_stocks": ["SH600000", "sh600000"],
        "groups": [
            {
                "name": "G1",
                "description": "desc",
                "stocks": ["SH600000", "sh600000"],
            }
        ],
    }

    resp1 = await client.post("/api/v1/settings/import", json=payload)
    assert resp1.status_code == 200
    assert resp1.json()["code"] == 0

    # 重复导入不应触发 groups.name 唯一约束，也不应重复写入同股不同大小写
    resp2 = await client.post("/api/v1/settings/import", json=payload)
    assert resp2.status_code == 200
    assert resp2.json()["code"] == 0

    async with async_session_maker() as db:
        groups = (await db.execute(select(Group))).scalars().all()
        assert len(groups) == 1
        assert groups[0].name == "G1"

        group_stocks = (await db.execute(select(GroupStock))).scalars().all()
        assert len(group_stocks) == 1
        assert group_stocks[0].stock_code == "sh600000"

        followed = (await db.execute(select(FollowedStock))).scalars().all()
        assert len(followed) == 1
        assert followed[0].stock_code == "sh600000"


@pytest.mark.asyncio
async def test_group_add_remove_stock_normalizes_and_is_case_insensitive(client):
    await _clear_group_and_followed_tables()

    create_resp = await client.post("/api/v1/group", json={"name": "G1", "description": "", "sort_order": 0})
    assert create_resp.status_code == 200
    group_id = create_resp.json()["data"]["id"]

    add_resp = await client.post(f"/api/v1/group/{group_id}/stock", params={"stock_code": "SH600000"})
    assert add_resp.status_code == 200
    assert add_resp.json()["code"] == 0

    # 同一股票不同大小写视为重复
    add_dup_resp = await client.post(f"/api/v1/group/{group_id}/stock", params={"stock_code": "sh600000"})
    assert add_dup_resp.status_code == 400

    # 删除时允许不同大小写/前缀输入
    remove_resp = await client.delete(f"/api/v1/group/{group_id}/stock/SH600000")
    assert remove_resp.status_code == 200
    assert remove_resp.json()["code"] == 0

    async with async_session_maker() as db:
        group_stocks = (await db.execute(select(GroupStock))).scalars().all()
        assert group_stocks == []
