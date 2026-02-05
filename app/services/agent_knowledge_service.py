# Agent 知识库服务
"""
实现对齐 LearningSelfAgent/docs/agent 的“分层检索”能力：

图谱 → 领域 → 技能 → 方案 → 工具文档

目标：
- 低成本（优先本地 DB 规则匹配，不强依赖 LLM）
- 可落地（可注入 Planner/Executor prompt，提升可用性）
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Iterable, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_knowledge import (
    AgentDomain,
    AgentGraphNode,
    AgentSkill,
    AgentSolution,
    AgentToolDoc,
)


def _json_dumps(obj: Any) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False)
    except Exception:
        return ""


def _json_loads_list(text: str) -> list[Any]:
    raw = (text or "").strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except Exception:
        # 兼容“空格/逗号分隔”
        parts = re.split(r"[\s,;，；]+", raw)
        return [p for p in (x.strip() for x in parts) if p]


def _clamp(n: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, int(n)))


_STOPWORDS = {
    "如何",
    "怎么",
    "为什么",
    "什么",
    "一下",
    "目前",
    "当前",
    "这个",
    "那个",
    "可以",
    "是否",
    "还是",
    "我们",
    "你们",
    "项目",
    "模块",
    "实现",
    "功能",
    "数据",
    "接口",
    "页面",
}


def extract_keywords(text: str, *, max_keywords: int = 20) -> list[str]:
    """从输入中抽取关键词（规则优先，避免额外 LLM 成本）。"""
    t = (text or "").strip()
    if not t:
        return []

    zh = re.findall(r"[\u4e00-\u9fff]{2,8}", t)
    en = re.findall(r"[a-zA-Z0-9_]{3,}", t)
    raw = [*zh, *en]

    # 去停用词 + 去重（保持顺序）
    out: list[str] = []
    seen: set[str] = set()
    for w in raw:
        w = w.strip()
        if not w or w in _STOPWORDS:
            continue
        lw = w.lower()
        if lw in seen:
            continue
        seen.add(lw)
        out.append(w)
        if len(out) >= max_keywords:
            break
    return out


def _score_text(haystack: str, keywords: Iterable[str]) -> int:
    h = (haystack or "").lower()
    score = 0
    for k in keywords:
        if not k:
            continue
        kk = str(k).lower()
        if not kk:
            continue
        if kk in h:
            # 简单计分：出现则 +2，出现次数额外 +1
            score += 2
            score += h.count(kk)
    return score


def _truncate(text: str, max_len: int) -> str:
    s = (text or "").strip()
    if len(s) <= max_len:
        return s
    return s[: max(0, max_len - 1)] + "…"


@dataclass
class RetrievalBundle:
    keywords: list[str]
    graph_nodes: list[AgentGraphNode]
    domains: list[AgentDomain]
    skills: list[AgentSkill]
    solutions: list[AgentSolution]
    tool_docs: list[AgentToolDoc]
    context: str


class AgentKnowledgeService:
    """Agent 知识库：检索 + 格式化注入。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def ensure_seeded(self) -> None:
        """写入最小默认知识（幂等），保证开箱可用。"""
        defaults = [
            AgentDomain(
                id="finance.stock",
                name="股票分析",
                description="个股分析、策略、风险提示、技术/基本面/资金/情绪综合判断。",
                keywords=_json_dumps(["股票", "个股", "K线", "分时", "估值", "财务", "筹码", "公告", "研报", "资金"]),
                parent_id="finance",
                sort_order=10,
            ),
            AgentDomain(
                id="finance.market",
                name="市场与板块",
                description="指数、北向资金、龙虎榜、行业/概念、市场统计与情绪。",
                keywords=_json_dumps(["市场", "指数", "北向", "龙虎榜", "行业", "概念", "板块", "涨停", "跌停", "成交额"]),
                parent_id="finance",
                sort_order=20,
            ),
            AgentDomain(
                id="finance.news",
                name="资讯与事件",
                description="新闻、电报、公告、事件驱动与舆情检索。",
                keywords=_json_dumps(["新闻", "电报", "公告", "事件", "研报", "政策", "传闻", "热点"]),
                parent_id="finance",
                sort_order=30,
            ),
            AgentDomain(
                id="data.datasource",
                name="数据源与抓取",
                description="数据源选择、失败兜底、解析异常、接口口径与缓存策略。",
                keywords=_json_dumps(["数据源", "抓取", "解析", "failover", "兜底", "口径", "缓存", "限流", "反爬"]),
                parent_id="data",
                sort_order=40,
            ),
            AgentDomain(
                id="dev.recon",
                name="项目开发与修复",
                description="项目架构、模块耦合、测试、性能优化与可维护性改进。",
                keywords=_json_dumps(["重构", "优化", "测试", "性能", "耦合", "可维护", "接口契约", "缓存", "持久化"]),
                parent_id="dev",
                sort_order=50,
            ),
            AgentDomain(
                id="misc",
                name="未分类",
                description="无法明确归类的内容。",
                keywords=_json_dumps(["其它", "杂项"]),
                parent_id="",
                sort_order=999,
            ),
        ]

        changed = False

        # Domains：按 id 补齐缺失项（不覆盖用户自定义修改）
        default_ids = [d.id for d in defaults]
        existing_ids_result = await self.db.execute(select(AgentDomain.id).where(AgentDomain.id.in_(default_ids)))
        existing_ids = {str(x) for x in existing_ids_result.scalars().all()}
        for d in defaults:
            if d.id in existing_ids:
                continue
            self.db.add(d)
            changed = True

        # Seed ToolDocs from current runtime tools
        try:
            from app.llm.agent import TOOLS as RUNTIME_TOOLS

            runtime_names = [str(t.get("name", "") or "").strip() for t in RUNTIME_TOOLS]
            runtime_names = [n for n in runtime_names if n]
            existing_tools_result = await self.db.execute(
                select(AgentToolDoc.tool_name).where(AgentToolDoc.tool_name.in_(runtime_names[:200]))
            )
            existing_tools = {str(x) for x in existing_tools_result.scalars().all()}

            for t in RUNTIME_TOOLS:
                name = str(t.get("name", "") or "").strip()
                if not name:
                    continue
                if name in existing_tools:
                    continue
                self.db.add(
                    AgentToolDoc(
                        tool_name=name,
                        description=str(t.get("description", "") or ""),
                        parameters_schema=_json_dumps(t.get("parameters") or {}),
                        usage="",
                        tips="",
                        source="runtime",
                    )
                )
                changed = True
        except Exception:
            # 种子写入失败不阻塞系统
            pass

        # Seed one core skill (stock multi-dimensional analysis)
        core_skill = None
        try:
            core_skill_result = await self.db.execute(
                select(AgentSkill)
                .where(AgentSkill.name == "个股多维度分析方法论", AgentSkill.domain_id == "finance.stock")
                .limit(1)
            )
            core_skill = core_skill_result.scalar_one_or_none()
        except Exception:
            core_skill = None

        if not core_skill:
            core_skill = AgentSkill(
                name="个股多维度分析方法论",
                domain_id="finance.stock",
                description="获取行情/K线/技术指标/筹码/资金/公告研报/热点，综合输出操作建议与风险提示。",
                triggers=_json_dumps(["分析", "建议", "买入", "卖出", "止损", "目标价", "仓位", "复盘"]),
                steps=_json_dumps(
                    [
                        "获取实时行情（价格/涨跌幅/成交额）",
                        "获取K线与技术指标（MA/MACD/RSI/支撑压力）",
                        "获取资金面（北向/主力/板块资金）",
                        "获取筹码分布（获利比例/成本区间/集中度）",
                        "获取公告/研报/热点（风险与催化）",
                        "汇总输出：结论+决策仪表盘JSON+数据源列表+风险提示",
                    ]
                ),
                validation=_json_dumps(["列出 data_sources（实际调用过的工具）", "对缺失数据降置信度并说明原因"]),
                source="system",
                status="approved",
            )
            self.db.add(core_skill)
            changed = True

        # Seed minimal solutions：用于把 ToolDoc 引入检索上下文（更贴近 LearningSelfAgent 的“方案层”）
        try:
            await self.db.flush()
            core_skill_id = int(getattr(core_skill, "id", 0) or 0)
        except Exception:
            core_skill_id = 0

        solution_candidates = [
            AgentSolution(
                name="个股分析-Plan-ReAct 模板",
                domain_id="finance.stock",
                description="面向个股的标准执行顺序：行情→K线/技术→筹码/资金→公告/研报→结论+风险提示。",
                skill_ids=_json_dumps([core_skill_id] if core_skill_id else []),
                tool_names=_json_dumps(
                    [
                        "query_stock_price",
                        "query_stock_kline",
                        "query_technical_analysis",
                        "query_chip_distribution",
                        "query_stock_money_rank",
                        "query_north_flow",
                        "query_stock_notices",
                        "query_stock_research_reports",
                        "query_hot_topics",
                    ]
                ),
                steps=_json_dumps(
                    [
                        {"step": "获取行情", "tool": "query_stock_price"},
                        {"step": "获取K线", "tool": "query_stock_kline"},
                        {"step": "技术指标", "tool": "query_technical_analysis"},
                        {"step": "筹码分布", "tool": "query_chip_distribution"},
                        {"step": "资金流向", "tool": "query_stock_money_rank"},
                        {"step": "公告/研报/热点", "tool": "query_stock_notices"},
                        {"step": "输出结论与风险", "tool": ""},
                    ]
                ),
                source="system",
                status="approved",
            ),
            AgentSolution(
                name="市场概览-复盘模板",
                domain_id="finance.market",
                description="面向全市场复盘：市场概览→涨跌停/成交→北向资金→龙虎榜→行业/概念强弱。",
                skill_ids=_json_dumps([]),
                tool_names=_json_dumps(
                    [
                        "query_market_overview",
                        "query_limit_stats",
                        "query_north_flow",
                        "query_long_tiger",
                        "query_industry_rank",
                        "query_concept_rank",
                    ]
                ),
                steps=_json_dumps(
                    [
                        {"step": "市场统计", "tool": "query_market_overview"},
                        {"step": "涨跌停统计", "tool": "query_limit_stats"},
                        {"step": "北向资金", "tool": "query_north_flow"},
                        {"step": "龙虎榜", "tool": "query_long_tiger"},
                        {"step": "行业/概念强弱", "tool": "query_industry_rank"},
                        {"step": "输出结论与重点方向", "tool": ""},
                    ]
                ),
                source="system",
                status="approved",
            ),
        ]

        existing_solution_names_result = await self.db.execute(
            select(AgentSolution.name).where(AgentSolution.name.in_([s.name for s in solution_candidates]))
        )
        existing_solution_names = {str(x) for x in existing_solution_names_result.scalars().all()}
        for sol in solution_candidates:
            if sol.name in existing_solution_names:
                continue
            self.db.add(sol)
            changed = True

        if changed:
            await self.db.commit()

    async def retrieve(self, query: str, *, mode: str = "do") -> RetrievalBundle:
        """分层检索并生成可注入的上下文文本。"""
        await self.ensure_seeded()

        q = (query or "").strip()
        keywords = extract_keywords(q)

        # 1) Graph nodes（候选）
        graph_candidates: list[AgentGraphNode] = []
        if keywords:
            # 先粗筛：title/content/keywords 命中任一关键词
            stmt = select(AgentGraphNode).where(AgentGraphNode.is_active == True)
            result = await self.db.execute(stmt)
            all_nodes = result.scalars().all()
            for n in all_nodes:
                hay = " ".join([n.title or "", n.content or "", n.keywords or ""])
                s = _score_text(hay, keywords)
                if s > 0:
                    graph_candidates.append(n)

            # 排序：关键词匹配 + 置信度
            graph_candidates.sort(
                key=lambda n: (_score_text(" ".join([n.title or "", n.content or "", n.keywords or ""]), keywords), float(n.confidence or 0.0), n.id),
                reverse=True,
            )
        graph_nodes = graph_candidates[:6]

        # 2) Domains
        dom_result = await self.db.execute(
            select(AgentDomain).where(AgentDomain.is_enabled == True, AgentDomain.is_deprecated == False).order_by(AgentDomain.sort_order.asc())
        )
        all_domains = dom_result.scalars().all()

        domain_scored: list[tuple[int, AgentDomain]] = []
        for d in all_domains:
            dkw = _json_loads_list(d.keywords)
            hay = " ".join([d.id, d.name or "", d.description or "", " ".join([str(x) for x in dkw])])
            s = _score_text(hay, keywords)
            domain_scored.append((s, d))
        domain_scored.sort(key=lambda x: (x[0], -int(x[1].sort_order or 0)), reverse=True)

        domains = [d for s, d in domain_scored if s > 0][:3]
        if not domains:
            # 默认兜底：股票/项目两类
            fallback_ids = ["finance.stock", "finance.market", "dev.recon"]
            domains = [d for d in all_domains if d.id in fallback_ids][:2]

        domain_ids = [d.id for d in domains]

        # 3) Skills
        skill_stmt = (
            select(AgentSkill)
            .where(AgentSkill.is_enabled == True, AgentSkill.status == "approved")
            .where(AgentSkill.domain_id.in_(domain_ids))
            .order_by(AgentSkill.updated_at.desc())
        )
        skill_result = await self.db.execute(skill_stmt)
        all_skills = skill_result.scalars().all()

        skill_scored: list[tuple[int, AgentSkill]] = []
        for s in all_skills:
            trg = _json_loads_list(s.triggers)
            hay = " ".join([s.name or "", s.description or "", " ".join([str(x) for x in trg])])
            score = _score_text(hay, keywords)
            skill_scored.append((score, s))
        skill_scored.sort(key=lambda x: (x[0], x[1].id), reverse=True)

        skill_limit = 6 if (mode or "").lower() == "think" else 3
        skills = [s for score, s in skill_scored if score > 0][:skill_limit]
        if not skills:
            skills = all_skills[: min(skill_limit, len(all_skills))]

        # 4) Solutions
        sol_stmt = (
            select(AgentSolution)
            .where(AgentSolution.is_enabled == True, AgentSolution.status == "approved")
            .order_by(AgentSolution.updated_at.desc())
        )
        sol_result = await self.db.execute(sol_stmt)
        all_solutions = sol_result.scalars().all()

        skill_ids = {int(s.id) for s in skills if getattr(s, "id", None) is not None}

        sol_scored: list[tuple[int, AgentSolution]] = []
        for sol in all_solutions:
            if sol.domain_id and sol.domain_id not in domain_ids:
                # 领域不匹配时降低优先级，但不直接排除（可能跨域复用）
                domain_penalty = -2
            else:
                domain_penalty = 0

            sol_skill_ids = set()
            try:
                sol_skill_ids = {int(x) for x in _json_loads_list(sol.skill_ids) if str(x).isdigit()}
            except Exception:
                sol_skill_ids = set()

            overlap = len(skill_ids.intersection(sol_skill_ids))
            hay = " ".join([sol.name or "", sol.description or "", sol.steps or ""])
            score = _score_text(hay, keywords) + overlap * 3 + domain_penalty
            sol_scored.append((score, sol))

        sol_scored.sort(key=lambda x: (x[0], x[1].id), reverse=True)
        solutions = [s for score, s in sol_scored if score > 0][:3]

        # 5) Tool docs
        tool_names: list[str] = []
        for sol in solutions:
            tool_names.extend([str(x) for x in _json_loads_list(sol.tool_names)])
        # 去重
        tool_names = list(dict.fromkeys([t for t in tool_names if t]))

        tool_docs: list[AgentToolDoc] = []
        if tool_names:
            td_result = await self.db.execute(
                select(AgentToolDoc)
                .where(AgentToolDoc.is_enabled == True)
                .where(AgentToolDoc.tool_name.in_(tool_names[:20]))
            )
            tool_docs = td_result.scalars().all()

        context = self.format_as_context(
            keywords=keywords,
            graph_nodes=graph_nodes,
            domains=domains,
            skills=skills,
            solutions=solutions,
            tool_docs=tool_docs,
        )

        return RetrievalBundle(
            keywords=keywords,
            graph_nodes=graph_nodes,
            domains=domains,
            skills=skills,
            solutions=solutions,
            tool_docs=tool_docs,
            context=context,
        )

    def format_as_context(
        self,
        *,
        keywords: list[str],
        graph_nodes: list[AgentGraphNode],
        domains: list[AgentDomain],
        skills: list[AgentSkill],
        solutions: list[AgentSolution],
        tool_docs: list[AgentToolDoc],
        max_chars: int = 1800,
    ) -> str:
        """格式化为可注入 Planner/Executor 的上下文文本。"""
        blocks: list[str] = []

        if keywords:
            blocks.append("【关键词】" + "、".join(keywords[:12]))

        if graph_nodes:
            lines = []
            for n in graph_nodes[:6]:
                lines.append(f"- ({float(n.confidence or 0.0):.2f}) {n.title}: {_truncate(n.content, 160)}")
            blocks.append("【图谱(事实/约束)】\n" + "\n".join(lines))

        if domains:
            lines = []
            for d in domains[:3]:
                lines.append(f"- {d.id}（{d.name}）：{_truncate(d.description, 120)}")
            blocks.append("【领域候选】\n" + "\n".join(lines))

        if skills:
            lines = []
            for s in skills[:6]:
                steps = _json_loads_list(s.steps)
                step_txt = " / ".join([str(x) for x in steps[:4]]) if steps else _truncate(s.description, 120)
                lines.append(f"- {s.name}：{_truncate(step_txt, 180)}")
            blocks.append("【技能(方法论)】\n" + "\n".join(lines))

        if solutions:
            lines = []
            for sol in solutions[:3]:
                lines.append(f"- {sol.name}：{_truncate(sol.description or sol.steps, 160)}")
            blocks.append("【参考方案】\n" + "\n".join(lines))

        if tool_docs:
            lines = []
            for t in tool_docs[:6]:
                lines.append(f"- {t.tool_name}：{_truncate(t.description, 160)}")
            blocks.append("【工具提示】\n" + "\n".join(lines))

        text = "\n\n".join([b for b in blocks if b.strip()]).strip()
        return _truncate(text, _clamp(max_chars, 400, 4000))
