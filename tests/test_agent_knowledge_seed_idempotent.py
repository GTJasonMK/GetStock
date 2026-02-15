import pytest
from sqlalchemy import delete, select

from app.database import async_session_maker
from app.models.agent_knowledge import AgentDomain, AgentSkill, AgentSolution, AgentToolDoc
from app.services.agent_knowledge_service import AgentKnowledgeService


@pytest.mark.asyncio
async def test_ensure_seeded_backfills_when_domains_already_exist():
    async with async_session_maker() as db:
        # 清空相关表，避免受其他用例影响
        await db.execute(delete(AgentToolDoc))
        await db.execute(delete(AgentSolution))
        await db.execute(delete(AgentSkill))
        await db.execute(delete(AgentDomain))
        await db.commit()

        # 模拟“只存在部分 Domain，其它表为空”的历史状态
        db.add(
            AgentDomain(
                id="finance.stock",
                name="股票分析",
                description="仅用于测试的占位 domain",
                keywords="[]",
                parent_id="finance",
                sort_order=10,
                is_system=True,
                is_enabled=True,
                is_deprecated=False,
            )
        )
        await db.commit()

        svc = AgentKnowledgeService(db)
        await svc.ensure_seeded()

        domain_ids = {str(x) for x in (await db.execute(select(AgentDomain.id))).scalars().all()}
        assert "finance.market" in domain_ids
        assert "dev.recon" in domain_ids

        tool_doc = (
            await db.execute(select(AgentToolDoc).where(AgentToolDoc.tool_name == "query_stock_price"))
        ).scalar_one_or_none()
        assert tool_doc is not None

        sol = (
            await db.execute(select(AgentSolution).where(AgentSolution.name == "个股分析-Plan-ReAct 模板"))
        ).scalar_one_or_none()
        assert sol is not None

        # 幂等：重复调用不应重复插入（以 tool_docs 数量为例）
        before = len((await db.execute(select(AgentToolDoc.tool_name))).scalars().all())
        await svc.ensure_seeded()
        after = len((await db.execute(select(AgentToolDoc.tool_name))).scalars().all())
        assert after == before

