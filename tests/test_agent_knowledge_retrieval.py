import pytest
from sqlalchemy import delete

from app.database import async_session_maker
from app.models.agent_knowledge import AgentDomain, AgentSkill, AgentToolDoc
from app.services.agent_knowledge_service import AgentKnowledgeService


@pytest.mark.asyncio
async def test_agent_knowledge_service_seeds_minimum_defaults_and_retrieves_context():
    async with async_session_maker() as db:
        # 清空，确保走 seed 逻辑（避免依赖执行顺序）
        await db.execute(delete(AgentToolDoc))
        await db.execute(delete(AgentSkill))
        await db.execute(delete(AgentDomain))
        await db.commit()

        svc = AgentKnowledgeService(db)
        bundle = await svc.retrieve("请分析 sh600000 的资金流向和风险点", mode="do")

        assert bundle.context
        # 至少应能命中股票分析领域与核心方法论技能
        assert any(d.id == "finance.stock" for d in bundle.domains)
        assert any("多维度分析" in (s.name or "") for s in bundle.skills)
        # seed 会把运行时工具写入 tool_docs（不保证全部命中，但应至少存在一些）
        assert bundle.tool_docs is not None

