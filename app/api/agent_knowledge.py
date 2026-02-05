# Agent Knowledge API
"""
Agent 知识库 API：
- 分层检索（图谱→领域→技能→方案→工具文档）
- 列表查询（用于调试/维护）
"""

from __future__ import annotations

import json
from typing import Optional, Any

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.agent_knowledge import AgentDomain, AgentSkill, AgentSolution, AgentToolDoc, AgentGraphNode, AgentRun
from app.schemas.common import Response
from app.schemas.agent_knowledge import (
    AgentRetrieveRequest,
    AgentRetrieveResponse,
    AgentDomainItem,
    AgentSkillItem,
    AgentSolutionItem,
    AgentToolDocItem,
    AgentGraphNodeItem,
    AgentRunItem,
    AgentGraphNodeCreateRequest,
    AgentGraphNodeUpdateRequest,
    AgentSkillCreateRequest,
    AgentSkillUpdateRequest,
    AgentSolutionCreateRequest,
    AgentSolutionUpdateRequest,
)
from app.services.agent_knowledge_service import AgentKnowledgeService, _json_loads_list


router = APIRouter()


def _try_json_loads(text: str) -> Any:
    raw = (text or "").strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


def _json_dumps_or_empty(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False)
    except Exception:
        return ""


@router.post("/retrieve", response_model=Response[AgentRetrieveResponse])
async def retrieve(
    request: AgentRetrieveRequest,
    db: AsyncSession = Depends(get_db),
):
    svc = AgentKnowledgeService(db)
    bundle = await svc.retrieve(request.query, mode=str(request.mode or "do"))

    return Response(
        data=AgentRetrieveResponse(
            query=request.query,
            mode=str(request.mode or "do"),
            keywords=bundle.keywords,
            context=bundle.context,
            graph_nodes=[
                AgentGraphNodeItem(
                    id=n.id,
                    title=n.title,
                    content=n.content,
                    keywords=[str(x) for x in _json_loads_list(n.keywords)],
                    domain_id=n.domain_id or "",
                    confidence=float(n.confidence or 0.0),
                    source=n.source or "",
                    is_active=bool(n.is_active),
                    created_at=n.created_at,
                    updated_at=n.updated_at,
                )
                for n in bundle.graph_nodes
            ],
            domains=[
                AgentDomainItem(
                    id=d.id,
                    name=d.name or "",
                    description=d.description or "",
                    keywords=[str(x) for x in _json_loads_list(d.keywords)],
                    parent_id=d.parent_id or "",
                    sort_order=int(d.sort_order or 0),
                    is_enabled=bool(d.is_enabled),
                    is_deprecated=bool(d.is_deprecated),
                    created_at=d.created_at,
                    updated_at=d.updated_at,
                )
                for d in bundle.domains
            ],
            skills=[
                AgentSkillItem(
                    id=s.id,
                    name=s.name,
                    domain_id=s.domain_id,
                    description=s.description or "",
                    triggers=[str(x) for x in _json_loads_list(s.triggers)],
                    prerequisites=[str(x) for x in _json_loads_list(s.prerequisites)],
                    steps=[str(x) for x in _json_loads_list(s.steps)],
                    failure_modes=[str(x) for x in _json_loads_list(s.failure_modes)],
                    validation=[str(x) for x in _json_loads_list(s.validation)],
                    version=s.version or "1.0.0",
                    status=s.status or "approved",
                    is_enabled=bool(s.is_enabled),
                    created_at=s.created_at,
                    updated_at=s.updated_at,
                )
                for s in bundle.skills
            ],
            solutions=[
                AgentSolutionItem(
                    id=sol.id,
                    name=sol.name,
                    domain_id=sol.domain_id or "",
                    description=sol.description or "",
                    skill_ids=[int(x) for x in _json_loads_list(sol.skill_ids) if str(x).isdigit()],
                    tool_names=[str(x) for x in _json_loads_list(sol.tool_names)],
                    steps=_try_json_loads(sol.steps) if isinstance(sol.steps, str) else sol.steps,
                    status=sol.status or "approved",
                    is_enabled=bool(sol.is_enabled),
                    created_at=sol.created_at,
                    updated_at=sol.updated_at,
                )
                for sol in bundle.solutions
            ],
            tool_docs=[
                AgentToolDocItem(
                    tool_name=t.tool_name,
                    description=t.description or "",
                    parameters_schema=_try_json_loads(t.parameters_schema) if isinstance(t.parameters_schema, str) else t.parameters_schema,
                    usage=t.usage or "",
                    tips=t.tips or "",
                    status=t.status or "approved",
                    is_enabled=bool(t.is_enabled),
                    created_at=t.created_at,
                    updated_at=t.updated_at,
                )
                for t in bundle.tool_docs
            ],
        )
    )


@router.get("/domains", response_model=Response[list[AgentDomainItem]])
async def list_domains(
    enabled: Optional[bool] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    svc = AgentKnowledgeService(db)
    await svc.ensure_seeded()

    stmt = select(AgentDomain).order_by(AgentDomain.sort_order.asc(), AgentDomain.id.asc())
    if enabled is True:
        stmt = stmt.where(AgentDomain.is_enabled == True, AgentDomain.is_deprecated == False)
    result = await db.execute(stmt)
    rows = result.scalars().all()

    return Response(
        data=[
            AgentDomainItem(
                id=d.id,
                name=d.name or "",
                description=d.description or "",
                keywords=[str(x) for x in _json_loads_list(d.keywords)],
                parent_id=d.parent_id or "",
                sort_order=int(d.sort_order or 0),
                is_enabled=bool(d.is_enabled),
                is_deprecated=bool(d.is_deprecated),
                created_at=d.created_at,
                updated_at=d.updated_at,
            )
            for d in rows
        ]
    )


@router.get("/skills", response_model=Response[list[AgentSkillItem]])
async def list_skills(
    domain_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    svc = AgentKnowledgeService(db)
    await svc.ensure_seeded()

    stmt = select(AgentSkill).order_by(AgentSkill.updated_at.desc(), AgentSkill.id.desc())
    if domain_id:
        stmt = stmt.where(AgentSkill.domain_id == domain_id)
    if status:
        stmt = stmt.where(AgentSkill.status == status)
    result = await db.execute(stmt)
    rows = result.scalars().all()

    return Response(
        data=[
            AgentSkillItem(
                id=s.id,
                name=s.name,
                domain_id=s.domain_id,
                description=s.description or "",
                triggers=[str(x) for x in _json_loads_list(s.triggers)],
                prerequisites=[str(x) for x in _json_loads_list(s.prerequisites)],
                steps=[str(x) for x in _json_loads_list(s.steps)],
                failure_modes=[str(x) for x in _json_loads_list(s.failure_modes)],
                validation=[str(x) for x in _json_loads_list(s.validation)],
                version=s.version or "1.0.0",
                status=s.status or "approved",
                is_enabled=bool(s.is_enabled),
                created_at=s.created_at,
                updated_at=s.updated_at,
            )
            for s in rows
        ]
    )


@router.post("/skills", response_model=Response[AgentSkillItem])
async def create_skill(
    request: AgentSkillCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    svc = AgentKnowledgeService(db)
    await svc.ensure_seeded()

    skill = AgentSkill(
        name=request.name,
        domain_id=request.domain_id,
        description=request.description or "",
        triggers=_json_dumps_or_empty(request.triggers),
        prerequisites=_json_dumps_or_empty(request.prerequisites),
        steps=_json_dumps_or_empty(request.steps),
        failure_modes=_json_dumps_or_empty(request.failure_modes),
        validation=_json_dumps_or_empty(request.validation),
        version=request.version or "1.0.0",
        status=(request.status or "draft").strip() or "draft",
        source="user",
        is_enabled=bool(request.is_enabled),
    )
    db.add(skill)
    await db.commit()
    await db.refresh(skill)

    return Response(
        data=AgentSkillItem(
            id=skill.id,
            name=skill.name,
            domain_id=skill.domain_id,
            description=skill.description or "",
            triggers=[str(x) for x in _json_loads_list(skill.triggers)],
            prerequisites=[str(x) for x in _json_loads_list(skill.prerequisites)],
            steps=[str(x) for x in _json_loads_list(skill.steps)],
            failure_modes=[str(x) for x in _json_loads_list(skill.failure_modes)],
            validation=[str(x) for x in _json_loads_list(skill.validation)],
            version=skill.version or "1.0.0",
            status=skill.status or "draft",
            is_enabled=bool(skill.is_enabled),
            created_at=skill.created_at,
            updated_at=skill.updated_at,
        )
    )


@router.put("/skills/{skill_id}", response_model=Response[AgentSkillItem])
async def update_skill(
    skill_id: int,
    request: AgentSkillUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    row = (await db.execute(select(AgentSkill).where(AgentSkill.id == skill_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="skill not found")

    if request.name is not None:
        row.name = request.name
    if request.domain_id is not None:
        row.domain_id = request.domain_id
    if request.description is not None:
        row.description = request.description
    if request.triggers is not None:
        row.triggers = _json_dumps_or_empty(request.triggers)
    if request.prerequisites is not None:
        row.prerequisites = _json_dumps_or_empty(request.prerequisites)
    if request.steps is not None:
        row.steps = _json_dumps_or_empty(request.steps)
    if request.failure_modes is not None:
        row.failure_modes = _json_dumps_or_empty(request.failure_modes)
    if request.validation is not None:
        row.validation = _json_dumps_or_empty(request.validation)
    if request.version is not None:
        row.version = request.version
    if request.status is not None:
        row.status = (request.status or "").strip()
    if request.is_enabled is not None:
        row.is_enabled = bool(request.is_enabled)

    await db.commit()
    await db.refresh(row)

    return Response(
        data=AgentSkillItem(
            id=row.id,
            name=row.name,
            domain_id=row.domain_id,
            description=row.description or "",
            triggers=[str(x) for x in _json_loads_list(row.triggers)],
            prerequisites=[str(x) for x in _json_loads_list(row.prerequisites)],
            steps=[str(x) for x in _json_loads_list(row.steps)],
            failure_modes=[str(x) for x in _json_loads_list(row.failure_modes)],
            validation=[str(x) for x in _json_loads_list(row.validation)],
            version=row.version or "1.0.0",
            status=row.status or "draft",
            is_enabled=bool(row.is_enabled),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
    )


@router.delete("/skills/{skill_id}", response_model=Response[dict])
async def delete_skill(
    skill_id: int,
    db: AsyncSession = Depends(get_db),
):
    row = (await db.execute(select(AgentSkill).where(AgentSkill.id == skill_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="skill not found")

    # 软删除：禁用即可，不影响历史复盘
    row.is_enabled = False
    row.status = "deprecated"
    await db.commit()
    return Response(data={"ok": True})


@router.get("/solutions", response_model=Response[list[AgentSolutionItem]])
async def list_solutions(
    domain_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    svc = AgentKnowledgeService(db)
    await svc.ensure_seeded()

    stmt = select(AgentSolution).order_by(AgentSolution.updated_at.desc(), AgentSolution.id.desc())
    if domain_id:
        stmt = stmt.where(AgentSolution.domain_id == domain_id)
    if status:
        stmt = stmt.where(AgentSolution.status == status)
    result = await db.execute(stmt)
    rows = result.scalars().all()

    return Response(
        data=[
            AgentSolutionItem(
                id=sol.id,
                name=sol.name,
                domain_id=sol.domain_id or "",
                description=sol.description or "",
                skill_ids=[int(x) for x in _json_loads_list(sol.skill_ids) if str(x).isdigit()],
                tool_names=[str(x) for x in _json_loads_list(sol.tool_names)],
                steps=_try_json_loads(sol.steps) if isinstance(sol.steps, str) else sol.steps,
                status=sol.status or "approved",
                is_enabled=bool(sol.is_enabled),
                created_at=sol.created_at,
                updated_at=sol.updated_at,
            )
            for sol in rows
        ]
    )


@router.post("/solutions", response_model=Response[AgentSolutionItem])
async def create_solution(
    request: AgentSolutionCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    svc = AgentKnowledgeService(db)
    await svc.ensure_seeded()

    sol = AgentSolution(
        name=request.name,
        domain_id=request.domain_id or "",
        description=request.description or "",
        skill_ids=_json_dumps_or_empty(request.skill_ids),
        tool_names=_json_dumps_or_empty(request.tool_names),
        steps=_json_dumps_or_empty(request.steps),
        status=(request.status or "draft").strip() or "draft",
        source="user",
        is_enabled=bool(request.is_enabled),
    )
    db.add(sol)
    await db.commit()
    await db.refresh(sol)

    return Response(
        data=AgentSolutionItem(
            id=sol.id,
            name=sol.name,
            domain_id=sol.domain_id or "",
            description=sol.description or "",
            skill_ids=[int(x) for x in _json_loads_list(sol.skill_ids) if str(x).isdigit()],
            tool_names=[str(x) for x in _json_loads_list(sol.tool_names)],
            steps=_try_json_loads(sol.steps) if isinstance(sol.steps, str) else sol.steps,
            status=sol.status or "draft",
            is_enabled=bool(sol.is_enabled),
            created_at=sol.created_at,
            updated_at=sol.updated_at,
        )
    )


@router.put("/solutions/{solution_id}", response_model=Response[AgentSolutionItem])
async def update_solution(
    solution_id: int,
    request: AgentSolutionUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    row = (await db.execute(select(AgentSolution).where(AgentSolution.id == solution_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="solution not found")

    if request.name is not None:
        row.name = request.name
    if request.domain_id is not None:
        row.domain_id = request.domain_id
    if request.description is not None:
        row.description = request.description
    if request.skill_ids is not None:
        row.skill_ids = _json_dumps_or_empty(request.skill_ids)
    if request.tool_names is not None:
        row.tool_names = _json_dumps_or_empty(request.tool_names)
    if request.steps is not None:
        row.steps = _json_dumps_or_empty(request.steps)
    if request.status is not None:
        row.status = (request.status or "").strip()
    if request.is_enabled is not None:
        row.is_enabled = bool(request.is_enabled)

    await db.commit()
    await db.refresh(row)

    return Response(
        data=AgentSolutionItem(
            id=row.id,
            name=row.name,
            domain_id=row.domain_id or "",
            description=row.description or "",
            skill_ids=[int(x) for x in _json_loads_list(row.skill_ids) if str(x).isdigit()],
            tool_names=[str(x) for x in _json_loads_list(row.tool_names)],
            steps=_try_json_loads(row.steps) if isinstance(row.steps, str) else row.steps,
            status=row.status or "draft",
            is_enabled=bool(row.is_enabled),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
    )


@router.delete("/solutions/{solution_id}", response_model=Response[dict])
async def delete_solution(
    solution_id: int,
    db: AsyncSession = Depends(get_db),
):
    row = (await db.execute(select(AgentSolution).where(AgentSolution.id == solution_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="solution not found")
    row.is_enabled = False
    row.status = "deprecated"
    await db.commit()
    return Response(data={"ok": True})


@router.get("/tools", response_model=Response[list[AgentToolDocItem]])
async def list_tools(
    enabled: Optional[bool] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    svc = AgentKnowledgeService(db)
    await svc.ensure_seeded()

    stmt = select(AgentToolDoc).order_by(AgentToolDoc.tool_name.asc())
    if enabled is True:
        stmt = stmt.where(AgentToolDoc.is_enabled == True, AgentToolDoc.status == "approved")
    result = await db.execute(stmt)
    rows = result.scalars().all()

    return Response(
        data=[
            AgentToolDocItem(
                tool_name=t.tool_name,
                description=t.description or "",
                parameters_schema=_try_json_loads(t.parameters_schema) if isinstance(t.parameters_schema, str) else t.parameters_schema,
                usage=t.usage or "",
                tips=t.tips or "",
                status=t.status or "approved",
                is_enabled=bool(t.is_enabled),
                created_at=t.created_at,
                updated_at=t.updated_at,
            )
            for t in rows
        ]
    )


@router.get("/graph", response_model=Response[list[AgentGraphNodeItem]])
async def list_graph_nodes(
    active: Optional[bool] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    svc = AgentKnowledgeService(db)
    await svc.ensure_seeded()

    stmt = select(AgentGraphNode).order_by(AgentGraphNode.updated_at.desc(), AgentGraphNode.id.desc())
    if active is True:
        stmt = stmt.where(AgentGraphNode.is_active == True)
    result = await db.execute(stmt)
    rows = result.scalars().all()

    return Response(
        data=[
            AgentGraphNodeItem(
                id=n.id,
                title=n.title,
                content=n.content,
                keywords=[str(x) for x in _json_loads_list(n.keywords)],
                domain_id=n.domain_id or "",
                confidence=float(n.confidence or 0.0),
                source=n.source or "",
                is_active=bool(n.is_active),
                created_at=n.created_at,
                updated_at=n.updated_at,
            )
            for n in rows
        ]
    )


@router.post("/graph", response_model=Response[AgentGraphNodeItem])
async def create_graph_node(
    request: AgentGraphNodeCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    svc = AgentKnowledgeService(db)
    await svc.ensure_seeded()

    node = AgentGraphNode(
        title=request.title,
        content=request.content,
        keywords=_json_dumps_or_empty(request.keywords),
        domain_id=request.domain_id or "",
        confidence=float(request.confidence or 0.6),
        source=request.source or "user",
        is_active=bool(request.is_active),
    )
    db.add(node)
    await db.commit()
    await db.refresh(node)

    return Response(
        data=AgentGraphNodeItem(
            id=node.id,
            title=node.title,
            content=node.content,
            keywords=[str(x) for x in _json_loads_list(node.keywords)],
            domain_id=node.domain_id or "",
            confidence=float(node.confidence or 0.0),
            source=node.source or "",
            is_active=bool(node.is_active),
            created_at=node.created_at,
            updated_at=node.updated_at,
        )
    )


@router.put("/graph/{node_id}", response_model=Response[AgentGraphNodeItem])
async def update_graph_node(
    node_id: int,
    request: AgentGraphNodeUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    row = (await db.execute(select(AgentGraphNode).where(AgentGraphNode.id == node_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="graph node not found")

    if request.title is not None:
        row.title = request.title
    if request.content is not None:
        row.content = request.content
    if request.keywords is not None:
        row.keywords = _json_dumps_or_empty(request.keywords)
    if request.domain_id is not None:
        row.domain_id = request.domain_id
    if request.confidence is not None:
        row.confidence = float(request.confidence)
    if request.source is not None:
        row.source = request.source
    if request.is_active is not None:
        row.is_active = bool(request.is_active)

    await db.commit()
    await db.refresh(row)

    return Response(
        data=AgentGraphNodeItem(
            id=row.id,
            title=row.title,
            content=row.content,
            keywords=[str(x) for x in _json_loads_list(row.keywords)],
            domain_id=row.domain_id or "",
            confidence=float(row.confidence or 0.0),
            source=row.source or "",
            is_active=bool(row.is_active),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
    )


@router.delete("/graph/{node_id}", response_model=Response[dict])
async def delete_graph_node(
    node_id: int,
    db: AsyncSession = Depends(get_db),
):
    row = (await db.execute(select(AgentGraphNode).where(AgentGraphNode.id == node_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="graph node not found")
    row.is_active = False
    await db.commit()
    return Response(data={"ok": True})


@router.get("/runs", response_model=Response[list[AgentRunItem]])
async def list_runs(
    session_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(AgentRun).order_by(AgentRun.created_at.desc()).limit(limit)
    if session_id:
        stmt = stmt.where(AgentRun.session_id == session_id)
    result = await db.execute(stmt)
    rows = result.scalars().all()

    return Response(
        data=[
            AgentRunItem(
                id=r.id,
                created_at=r.created_at,
                session_id=r.session_id,
                mode=r.mode,
                stock_code=r.stock_code or "",
                stock_name=r.stock_name or "",
                question=r.question,
                plan_json=_try_json_loads(r.plan_json) if isinstance(r.plan_json, str) else None,
                used_tools=[str(x) for x in _json_loads_list(r.used_tools)],
                answer=r.answer,
                model_name=r.model_name or "",
                total_tokens=int(r.total_tokens or 0),
                retrieval_context=r.retrieval_context or "",
                evaluation=_try_json_loads(r.evaluation) if isinstance(r.evaluation, str) else None,
                score=int(r.score or 0),
            )
            for r in rows
        ]
    )
