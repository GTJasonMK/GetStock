# Agent Evaluation Service
"""
Agent 执行评估服务（对齐 LearningSelfAgent/docs/agent 的“评估→沉淀”闭环）。

设计目标：
- 默认不依赖外部 LLM：使用启发式规则给出基础评分与问题清单，保证离线可用、测试可跑。
- 可选启用 LLM 评估：在需要更高质量评审时，用同一模型生成结构化评估 JSON。
- 评估结果用于：
  1) 写入 AgentRun.evaluation/score 便于复盘
  2) 作为后续“知识沉淀”的候选输入（knowledge_candidates）
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Optional

from app.models.settings import AIConfig
from app.schemas.ai import ChatMessage


def _json_dumps(obj: Any) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False)
    except Exception:
        return ""


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _clamp_score(score: int) -> int:
    return max(0, min(100, int(score)))


def _truncate(text: str, max_len: int) -> str:
    s = (text or "").strip()
    if len(s) <= max_len:
        return s
    return s[: max(0, max_len - 1)] + "…"


def _extract_json_object(text: str) -> Optional[dict]:
    raw = (text or "").strip()
    if not raw:
        return None
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except Exception:
        pass

    # 尝试截取 JSON 对象（避免模型输出前后夹杂解释文本）
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end <= start:
        return None
    snippet = raw[start : end + 1]
    try:
        data = json.loads(snippet)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


@dataclass
class AgentEvaluationResult:
    score: int
    evaluation_json: str
    evaluator: str = "heuristic"  # heuristic/llm
    raw: str = ""


class AgentEvaluationService:
    """AgentRun 评估器（启发式 + 可选 LLM）。"""

    def __init__(self, config: Optional[AIConfig] = None):
        self.config = config

    def evaluate_heuristic(
        self,
        *,
        mode: str,
        question: str,
        plan_json: str,
        used_tools: list[str],
        answer: str,
        knowledge_context: str,
    ) -> AgentEvaluationResult:
        """启发式评估：保证离线可用，且不引入外部调用。"""
        m = (mode or "").strip().lower() or "agent"
        q = (question or "").strip()
        a = (answer or "").strip()
        tools = [t for t in (used_tools or []) if str(t).strip()]

        checklist = {
            "has_question": bool(q),
            "has_plan": bool((plan_json or "").strip()),
            "used_tools": len(tools) > 0,
            "has_answer": bool(a),
            "has_knowledge_context": bool((knowledge_context or "").strip()),
            "mode": m,
        }

        issues: list[str] = []
        suggestions: list[str] = []

        if m in {"do", "think"} and not tools:
            issues.append("do/think 模式未记录到工具调用（可能规划未触发或工具链失败）。")
            suggestions.append("检查 planner 输出与工具权限；必要时在 plan 中显式加入 get_* 工具步骤。")

        if m in {"do", "think"} and not checklist["has_plan"]:
            issues.append("do/think 模式缺少 plan_json（无法复盘规划质量）。")
            suggestions.append("确保 plan 阶段事件或 thoughts[0] 计划块被正确落库。")

        if len(a) < 40:
            issues.append("回答过短，可能缺少数据依据或风险提示。")
            suggestions.append("补齐数据来源、关键指标与风险提示；对缺失数据明确降级说明。")

        if m in {"do", "think"} and not checklist["has_knowledge_context"]:
            # 知识检索失败不一定是问题，但作为提示项
            issues.append("本次未注入 knowledge_context（可能影响稳定性与可复用性）。")
            suggestions.append("补充知识库 seed/维护；或在检索 query 中加入股票名/代码等强信号。")

        # 评分：以“可复盘/可执行/有依据”为核心
        score = 50
        if checklist["has_plan"]:
            score += 10
        else:
            score -= 5

        if m in {"do", "think"}:
            score += 10 if tools else -10
            score += 5 if checklist["has_knowledge_context"] else 0

        if len(a) >= 220:
            score += 12
        elif len(a) >= 120:
            score += 8
        elif len(a) >= 60:
            score += 2
        else:
            score -= 10

        score = _clamp_score(score)

        evaluation = {
            "version": "1.0",
            "evaluator": "heuristic",
            "score": score,
            "checklist": checklist,
            "issues": issues,
            "suggestions": suggestions,
            # 为后续“知识沉淀”预留结构（此处仅输出空候选，避免误写入）
            "knowledge_candidates": [],
        }

        return AgentEvaluationResult(score=score, evaluation_json=_json_dumps(evaluation), evaluator="heuristic")

    async def evaluate(
        self,
        *,
        mode: str,
        question: str,
        plan_json: str,
        used_tools: list[str],
        answer: str,
        knowledge_context: str,
        enable_llm: bool = False,
    ) -> AgentEvaluationResult:
        """评估入口：默认启发式，可选用 LLM 生成更详细的结构化评审。"""
        base = self.evaluate_heuristic(
            mode=mode,
            question=question,
            plan_json=plan_json,
            used_tools=used_tools,
            answer=answer,
            knowledge_context=knowledge_context,
        )

        if not enable_llm or not self.config:
            return base

        # LLM 评估：失败则回退到启发式，保证主流程稳定。
        try:
            llm_result = await self._evaluate_with_llm(
                mode=mode,
                question=question,
                plan_json=plan_json,
                used_tools=used_tools,
                answer=answer,
                knowledge_context=knowledge_context,
            )
            return llm_result or base
        except Exception:
            return base

    async def _evaluate_with_llm(
        self,
        *,
        mode: str,
        question: str,
        plan_json: str,
        used_tools: list[str],
        answer: str,
        knowledge_context: str,
    ) -> Optional[AgentEvaluationResult]:
        if not self.config:
            return None

        from app.llm.client import LLMClient

        system = (
            "你是一个严格的 Agent 执行评估器。"
            "你必须只输出一个 JSON 对象，不要输出任何额外文本。"
            "JSON schema:\n"
            "{\n"
            '  \"score\": 0-100 的整数,\n'
            '  \"issues\": [string],\n'
            '  \"suggestions\": [string],\n'
            '  \"knowledge_candidates\": [\n'
            "    {\n"
            '      \"type\": \"graph_node\"|\"skill\"|\"solution\",\n'
            '      \"title\": string,\n'
            '      \"content\": string,\n'
            '      \"tags\": [string],\n'
            '      \"confidence\": 0-1\n'
            "    }\n"
            "  ]\n"
            "}\n"
        )

        payload = _json_dumps(
            {
                "mode": (mode or "").strip().lower(),
                "question": _truncate(question, 800),
                "plan_json": _truncate(plan_json, 1200),
                "used_tools": [str(t) for t in (used_tools or [])][:30],
                "answer": _truncate(answer, 1800),
                "knowledge_context": _truncate(knowledge_context, 1200),
            }
        )

        messages = [
            ChatMessage(role="system", content=system),
            ChatMessage(role="user", content=payload),
        ]

        client = LLMClient(self.config)
        try:
            resp = await client.chat(messages)
            raw = (resp.response or "").strip()
        finally:
            await client.close()

        data = _extract_json_object(raw)
        if not data:
            return None

        score = _clamp_score(_safe_int(data.get("score", 0), 0))
        issues = data.get("issues") if isinstance(data.get("issues"), list) else []
        suggestions = data.get("suggestions") if isinstance(data.get("suggestions"), list) else []
        candidates = data.get("knowledge_candidates") if isinstance(data.get("knowledge_candidates"), list) else []

        evaluation = {
            "version": "1.0",
            "evaluator": "llm",
            "score": score,
            "issues": [str(x) for x in issues if str(x).strip()][:20],
            "suggestions": [str(x) for x in suggestions if str(x).strip()][:20],
            "knowledge_candidates": candidates[:20],
        }

        return AgentEvaluationResult(
            score=score,
            evaluation_json=_json_dumps(evaluation),
            evaluator="llm",
            raw=raw,
        )

