# AI Agent
"""
ReACT模式AI Agent - 完整工具集
"""

import json
import re
from typing import List, AsyncGenerator, Optional, Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.settings import AIConfig
from app.schemas.ai import ChatMessage, AgentResponse, AgentThought, AgentToolCall


# 工具定义
# 说明：在原 12 个工具基础上，补齐市场概览/龙虎榜/北向资金等高频信息，方便 Agent 端到端完成信息收集与回答。
TOOLS = [
    # 1. QueryStockPriceInfo - 实时股价数据
    {
        "name": "query_stock_price",
        "description": "批量获取实时股价数据，包括当前价格、涨跌幅、成交量、换手率等",
        "parameters": {
            "type": "object",
            "properties": {
                "stock_codes": {
                    "type": "string",
                    "description": "股票代码，多个用逗号隔开，格式必须为sh/sz/hk开头，例如：sz399001,sh600859"
                }
            },
            "required": ["stock_codes"]
        }
    },
    # 2. QueryStockKLine - K线数据
    {
        "name": "query_stock_kline",
        "description": "获取股票K线数据，输入股票代码和K线条数，返回股票K线数据",
        "parameters": {
            "type": "object",
            "properties": {
                "stock_code": {
                    "type": "string",
                    "description": "股票代码，格式为A股(sh/sz开头)、港股(hk开头)或美股(us开头)"
                },
                "days": {
                    "type": "integer",
                    "description": "日K数据条数",
                    "default": 30
                }
            },
            "required": ["stock_code"]
        }
    },
    # 3. QueryStockCodeInfo - 股票信息查询
    {
        "name": "query_stock_info",
        "description": "查询股票/指数信息(名称、代码、拼音、拼音首字母、交易所等)",
        "parameters": {
            "type": "object",
            "properties": {
                "search_word": {
                    "type": "string",
                    "description": "股票搜索关键词"
                }
            },
            "required": ["search_word"]
        }
    },
    # 4. GetFinancialReport - 财务报表
    {
        "name": "get_financial_report",
        "description": "查询股票财务报表数据，包括利润表、资产负债表等",
        "parameters": {
            "type": "object",
            "properties": {
                "stock_code": {
                    "type": "string",
                    "description": "股票代码，格式为A股(sh/sz开头)、港股(hk开头)或美股(us开头)，不支持批量查询"
                }
            },
            "required": ["stock_code"]
        }
    },
    # 5. ChoiceStockByIndicators - 自然语言选股
    {
        "name": "choice_stock_by_indicators",
        "description": "根据自然语言筛选股票，返回自然语言选股条件要求的股票所有相关数据。支持技术指标(MACD、RSI、KDJ、BOLL)、均线、市值、换手率、涨幅等条件",
        "parameters": {
            "type": "object",
            "properties": {
                "words": {
                    "type": "string",
                    "description": "选股自然语言，如：涨停股、主力资金流入、MACD金叉、市盈率低于20等"
                }
            },
            "required": ["words"]
        }
    },
    # 6. QueryMarketNews - 市场资讯
    {
        "name": "query_market_news",
        "description": "国内外市场资讯/电报/会议/事件，返回事件日期、市场资讯、全球新闻、外媒新闻等",
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "返回数量",
                    "default": 20
                }
            }
        }
    },
    # 7. QueryStockNewsTool - 股票新闻搜索
    {
        "name": "query_stock_news",
        "description": "按关键词搜索相关市场资讯/新闻",
        "parameters": {
            "type": "object",
            "properties": {
                "search_words": {
                    "type": "string",
                    "description": "搜索关键词，多个关键词使用空格分隔"
                }
            },
            "required": ["search_words"]
        }
    },
    # 8. QueryInteractiveAnswerData - 投资者互动问答
    {
        "name": "query_interactive_qa",
        "description": "获取投资者与上市公司互动问答的数据，反映当前投资者关注的热点问题",
        "parameters": {
            "type": "object",
            "properties": {
                "page": {
                    "type": "integer",
                    "description": "分页号",
                    "default": 1
                },
                "page_size": {
                    "type": "integer",
                    "description": "分页大小",
                    "default": 20
                },
                "keyword": {
                    "type": "string",
                    "description": "搜索关键词，多个关键词空格隔开（可输入股票名称或热门板块/行业/概念等）"
                }
            }
        }
    },
    # 9. GetIndustryResearchReport - 行业研究报告
    {
        "name": "get_industry_research_report",
        "description": "获取行业/板块研究报告",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "行业/板块名称"
                },
                "code": {
                    "type": "string",
                    "description": "行业/板块代码"
                }
            }
        }
    },
    # 10. QueryEconomicData - 宏观经济数据
    {
        "name": "query_economic_data",
        "description": "查询宏观经济数据(GDP、CPI、PPI、PMI)",
        "parameters": {
            "type": "object",
            "properties": {
                "flag": {
                    "type": "string",
                    "description": "数据类型: all(全部), GDP(国内生产总值), CPI(居民消费价格指数), PPI(工业品出厂价格指数), PMI(采购经理人指数)",
                    "default": "all"
                }
            }
        }
    },
    # 11. QueryBKDictInfo - 板块/行业字典
    {
        "name": "query_bk_dict",
        "description": "获取所有板块/行业名称或者代码(bkCode,bkName)",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    },
    # 12. 资金流向排名
    {
        "name": "get_money_flow_rank",
        "description": "获取资金流向排名，主力资金净流入/流出排行",
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "返回数量",
                    "default": 20
                },
                "order": {
                    "type": "string",
                    "description": "排序方向: desc(流入), asc(流出)",
                    "default": "desc"
                }
            }
        }
    },
    # 13. query_market_overview - 市场概览（对齐 daily_stock_analysis 的复盘口径）
    {
        "name": "query_market_overview",
        "description": "获取市场概览：指数、涨跌家数、成交额、涨跌停、板块涨跌榜、（可选）北向资金等",
        "parameters": {"type": "object", "properties": {}}
    },
    # 14. query_long_tiger - 龙虎榜
    {
        "name": "query_long_tiger",
        "description": "获取龙虎榜（可指定交易日期 YYYY-MM-DD）",
        "parameters": {
            "type": "object",
            "properties": {
                "trade_date": {"type": "string", "description": "交易日期 YYYY-MM-DD（可选）"}
            }
        }
    },
    # 15. query_north_flow - 北向资金
    {
        "name": "query_north_flow",
        "description": "获取北向资金（沪股通/深股通）历史数据",
        "parameters": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "近 N 个交易日", "default": 30}
            }
        }
    },
    # 16. query_industry_rank - 行业涨跌榜
    {
        "name": "query_industry_rank",
        "description": "获取行业排名（涨幅/换手率等）",
        "parameters": {
            "type": "object",
            "properties": {
                "sort_by": {"type": "string", "description": "change_percent/turnover", "default": "change_percent"},
                "order": {"type": "string", "description": "asc/desc", "default": "desc"},
                "limit": {"type": "integer", "description": "返回数量", "default": 20}
            }
        }
    },
    # 17. query_concept_rank - 概念板块涨跌榜
    {
        "name": "query_concept_rank",
        "description": "获取概念板块排名（涨幅/换手率等）",
        "parameters": {
            "type": "object",
            "properties": {
                "sort_by": {"type": "string", "description": "change_percent/turnover", "default": "change_percent"},
                "order": {"type": "string", "description": "asc/desc", "default": "desc"},
                "limit": {"type": "integer", "description": "返回数量", "default": 20}
            }
        }
    },
    # 18. query_industry_money_flow - 行业/概念资金流向榜
    {
        "name": "query_industry_money_flow",
        "description": "获取行业/概念资金流向排名",
        "parameters": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "description": "hangye(行业)/gainian(概念)", "default": "hangye"},
                "sort_by": {"type": "string", "description": "排序字段", "default": "main_inflow"}
            }
        }
    },
    # 19. query_stock_money_rank - 个股资金流入榜
    {
        "name": "query_stock_money_rank",
        "description": "获取股票资金流入排名",
        "parameters": {
            "type": "object",
            "properties": {
                "sort_by": {"type": "string", "description": "排序字段", "default": "main_inflow"},
                "limit": {"type": "integer", "description": "返回数量", "default": 20}
            }
        }
    },
    # 20. query_volume_ratio_rank - 量比排名
    {
        "name": "query_volume_ratio_rank",
        "description": "获取量比排名（用于发现量能异动）",
        "parameters": {
            "type": "object",
            "properties": {
                "min_ratio": {"type": "number", "description": "最小量比", "default": 2.0},
                "limit": {"type": "integer", "description": "返回数量", "default": 20}
            }
        }
    },
    # 21. query_limit_stats - 涨跌停统计
    {
        "name": "query_limit_stats",
        "description": "获取涨停/跌停统计与名单",
        "parameters": {"type": "object", "properties": {}}
    },
    # 22. get_stock_detail - 股票全量详情（估值/财务/股东/分红等）
    {
        "name": "get_stock_detail",
        "description": "获取股票完整详情（估值指标、财务、机构评级、股东、分红、资金流向等；实际字段以数据源可用性为准）",
        "parameters": {
            "type": "object",
            "properties": {
                "stock_code": {"type": "string", "description": "股票代码，格式为A股(sh/sz开头)、港股(hk开头)或美股(us开头)"}
            },
            "required": ["stock_code"]
        }
    },
    # 23. query_chip_distribution - 筹码分布（对齐 daily_stock_analysis）
    {
        "name": "query_chip_distribution",
        "description": "获取筹码分布（获利比例、平均成本、70/90 成本区间与集中度）。注：ETF/指数/部分股票可能无数据",
        "parameters": {
            "type": "object",
            "properties": {
                "stock_code": {"type": "string", "description": "股票代码，A股建议 sh/sz 前缀；也支持 6 位数字自动识别"}
            },
            "required": ["stock_code"]
        }
    },
    # 24. query_technical_analysis - 技术指标与信号（MA/MACD/RSI/支撑压力/评分）
    {
        "name": "query_technical_analysis",
        "description": "计算技术指标（MA/MACD/RSI/量比/支撑压力）并给出综合评分与买卖信号（用于生成决策仪表盘）",
        "parameters": {
            "type": "object",
            "properties": {
                "stock_code": {"type": "string", "description": "股票代码，A股建议 sh/sz 前缀；也支持 6 位数字自动识别"},
                "days": {"type": "integer", "description": "用于计算的日K条数（需>=60）", "default": 120}
            },
            "required": ["stock_code"]
        }
    },
    # 25. query_stock_notices - 公司公告
    {
        "name": "query_stock_notices",
        "description": "获取公司公告（用于风险排查：减持/回购/立案/处罚/业绩预告等）",
        "parameters": {
            "type": "object",
            "properties": {
                "stock_code": {"type": "string", "description": "股票代码"},
                "limit": {"type": "integer", "description": "返回数量", "default": 20}
            },
            "required": ["stock_code"]
        }
    },
    # 26. query_stock_research_reports - 研报/机构报告
    {
        "name": "query_stock_research_reports",
        "description": "获取股票研报（标题/机构/时间/摘要等），用于补充机构观点与预期差",
        "parameters": {
            "type": "object",
            "properties": {
                "stock_code": {"type": "string", "description": "股票代码"},
                "limit": {"type": "integer", "description": "返回数量", "default": 10}
            },
            "required": ["stock_code"]
        }
    },
    # 27. query_hot_topics - 热门话题
    {
        "name": "query_hot_topics",
        "description": "获取市场热门话题（用于判断短线情绪与主线）",
        "parameters": {"type": "object", "properties": {"size": {"type": "integer", "default": 20}}}
    },
    # 28. query_hot_events - 热门事件
    {
        "name": "query_hot_events",
        "description": "获取市场热门事件（用于捕捉近期催化）",
        "parameters": {"type": "object", "properties": {"size": {"type": "integer", "default": 20}}}
    },
    # 29. search_web - 联网搜索（多引擎）
    {
        "name": "search_web",
        "description": "联网检索资讯（多引擎/多Key/自动去重排序），返回结构化结果与可读上下文",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词/问题"},
                "limit": {"type": "integer", "description": "返回数量", "default": 8}
            },
            "required": ["query"]
        }
    },
]


class StockAgent:
    """股票分析Agent"""

    def __init__(self, config: AIConfig, db: AsyncSession):
        self.config = config
        self.db = db

    @staticmethod
    def _tool_name_set() -> set[str]:
        """可用工具名集合（用于规划/allow 约束过滤）。"""
        return {str(t.get("name", "") or "").strip() for t in TOOLS if t.get("name")}

    def _build_planner_prompt(
        self,
        *,
        mode: str,
        max_steps: int,
        candidate_hint: str = "",
        retrieval_context: str = "",
    ) -> str:
        """构建 Plan 阶段 Prompt（对齐 LearningSelfAgent 的 Plan-ReAct 范式）。"""
        tools_desc = json.dumps(
            [
                {
                    "name": t.get("name"),
                    "description": t.get("description"),
                    "parameters": t.get("parameters"),
                }
                for t in TOOLS
            ],
            ensure_ascii=False,
            indent=2,
        )

        hint = (candidate_hint or "").strip()
        hint_block = f"\n规划风格提示：{hint}\n" if hint else ""

        rc = (retrieval_context or "").strip()
        retrieval_block = f"\n已检索到的知识（供规划参考，可能不完整）：\n{rc}\n" if rc else ""

        return f"""你是一个专业的任务规划器（Planner）。你的职责是：根据用户问题，生成一个可执行的计划（Plan），供后续 ReAct 执行器逐步完成。

你可用的工具如下（仅允许从 tool.name 选择）：
{tools_desc}
{retrieval_block}
{hint_block}
输出要求（必须严格遵守）：
- 只输出一个 JSON 对象，不要输出任何额外文字、解释或 Markdown。
- JSON schema：
{{
  "mode": "{mode}",
  "steps": [
    {{
      "title": "步骤标题（短）",
      "goal": "本步骤目标（明确、可验证）",
      "allowed_tools": ["tool_name1", "tool_name2"]
    }}
  ]
}}

规划规则：
- steps 数量 <= {max_steps}（越少越好，但要覆盖完成任务所需信息）。
- allowed_tools 只能是上面工具列表中的 name；每步建议 0-4 个工具。
- 若用户问题不需要调用任何工具即可回答（闲聊/纯知识解释/不依赖实时数据），steps 可以为空列表。
- 计划要尽量体现：信息收集 → 关键判断 → 汇总输出 的顺序。
"""

    def _parse_plan(self, content: str, *, max_steps: int) -> Optional[dict]:
        """解析 Planner 输出的计划 JSON（容错：允许包裹文本/代码块）。"""
        text = (content or "").strip()
        if not text:
            return None

        # 1) 代码块优先
        fence = re.search(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.IGNORECASE | re.DOTALL)
        if fence:
            text = (fence.group(1) or "").strip()

        # 2) 直接解析
        raw_obj: Optional[dict] = None
        try:
            parsed = json.loads(text)
            raw_obj = parsed if isinstance(parsed, dict) else None
        except Exception:
            raw = self._extract_json_object(text)
            if raw:
                try:
                    parsed = json.loads(raw)
                    raw_obj = parsed if isinstance(parsed, dict) else None
                except Exception:
                    raw_obj = None

        if not raw_obj:
            return None

        steps = raw_obj.get("steps")
        if not isinstance(steps, list):
            steps = []

        tool_names = self._tool_name_set()
        cleaned_steps: list[dict] = []
        for s in steps:
            if not isinstance(s, dict):
                continue
            title = str(s.get("title", "") or "").strip() or "步骤"
            goal = str(s.get("goal", "") or "").strip()
            allowed = s.get("allowed_tools", [])
            if not isinstance(allowed, list):
                allowed = []
            allowed_clean = []
            for a in allowed:
                name = self._clean_tool_name(str(a or ""))
                if not name:
                    continue
                if name in tool_names:
                    allowed_clean.append(name)
            # 去重但保持顺序
            dedup: list[str] = []
            seen: set[str] = set()
            for n in allowed_clean:
                if n in seen:
                    continue
                seen.add(n)
                dedup.append(n)
            cleaned_steps.append(
                {
                    "title": title[:80],
                    "goal": goal[:300],
                    "allowed_tools": dedup[:8],
                }
            )

        # 控制步数上限
        max_n = max(1, int(max_steps or 1))
        cleaned_steps = cleaned_steps[:max_n]

        return {"mode": str(raw_obj.get("mode", "") or "").strip(), "steps": cleaned_steps}

    async def _create_plan(
        self,
        messages: List[ChatMessage],
        *,
        mode: str,
        max_steps: int,
        candidate_hint: str = "",
        retrieval_context: str = "",
    ) -> Optional[dict]:
        """生成计划（失败时返回 None，调用方应自动降级）。"""
        from app.llm.client import LLMClient

        # 规划只需要最近上下文，避免把大量 Observation 注入导致成本膨胀
        ctx = messages[-8:] if messages else []
        planner_messages = [
            ChatMessage(
                role="system",
                content=self._build_planner_prompt(
                    mode=mode,
                    max_steps=max_steps,
                    candidate_hint=candidate_hint,
                    retrieval_context=retrieval_context,
                ),
            )
        ] + ctx

        client = LLMClient(self.config)
        try:
            resp = await client.chat(planner_messages)
            return self._parse_plan(resp.response, max_steps=max_steps)
        finally:
            await client.close()

    async def _select_best_plan(self, messages: List[ChatMessage], plans: List[dict]) -> Optional[dict]:
        """评估挑选最优计划（think 模式的简化 evaluator）。"""
        from app.llm.client import LLMClient

        if not plans:
            return None
        if len(plans) == 1:
            return plans[0]

        prompt = f"""你是评估 Agent（Evaluator）。请从多个候选计划中选择一个最优计划，并可做轻量修正以提高可执行性。

评估标准：
- 覆盖完成任务所需信息（不过度冗余）
- 步骤顺序合理（先收集信息再输出）
- 每步 allowed_tools 合理且数量少（0-4 个为佳）
- 不调用不存在的工具

输出要求：
- 只输出一个 JSON 对象，不要输出任何额外文字。
- schema：
{{
  "selected_index": 0,
  "plan": {{ "mode": "think", "steps": [...] }}
}}
"""

        eval_messages = [
            ChatMessage(role="system", content=prompt),
            ChatMessage(role="user", content=json.dumps({"candidates": plans}, ensure_ascii=False)),
        ]

        client = LLMClient(self.config)
        try:
            resp = await client.chat(eval_messages)
            obj = self._parse_action_input(resp.response)  # 复用 JSON 容错解析
            idx = obj.get("selected_index")
            plan = obj.get("plan")
            try:
                idx_int = int(idx)
            except Exception:
                idx_int = 0
            if isinstance(plan, dict) and isinstance(plan.get("steps"), list):
                parsed = self._parse_plan(json.dumps(plan, ensure_ascii=False), max_steps=len(plan.get("steps") or []))
                return parsed or plans[min(max(idx_int, 0), len(plans) - 1)]
            return plans[min(max(idx_int, 0), len(plans) - 1)]
        finally:
            await client.close()

    @staticmethod
    def _parse_step_done(content: str) -> str:
        """解析步骤完成标记（用于 Plan-ReAct）。"""
        if not content:
            return ""
        m = re.search(
            r"^(?:Step\s*Done|StepDone|步骤完成|步骤\s*Done)\s*[:：]\s*(.+)$",
            content,
            flags=re.IGNORECASE | re.MULTILINE,
        )
        return (m.group(1) or "").strip() if m else ""

    async def run_do(
        self,
        messages: List[ChatMessage],
        *,
        max_plan_steps: int = 6,
        knowledge_context: str = "",
    ) -> AgentResponse:
        """do 模式：Plan（单模型规划） + ReAct（单模型执行）。

        说明：若规划失败则自动降级为直接 ReAct（run）。
        """
        plan = await self._create_plan(
            messages,
            mode="do",
            max_steps=max_plan_steps,
            retrieval_context=knowledge_context,
        )
        if not plan or not isinstance(plan.get("steps"), list):
            return await self.run(messages)
        return await self._run_with_plan(messages, plan, mode="do", knowledge_context=knowledge_context)

    async def run_think(
        self,
        messages: List[ChatMessage],
        *,
        max_plan_steps: int = 6,
        plan_candidates: int = 3,
        knowledge_context: str = "",
    ) -> AgentResponse:
        """think 模式（简化版）：多候选规划 + evaluator 挑选 + ReAct 执行。

        说明：
        - 当前实现为“同一模型多视角规划”，用于对齐范式；不引入额外模型依赖。
        - 若规划/评估失败则自动降级为 do/run。
        """
        n = max(1, min(5, int(plan_candidates or 1)))
        hints = [
            "偏向数据充分性：多维度收集后再结论",
            "偏向成本控制：最少工具调用完成任务",
            "偏向风险排查：优先公告/资金/异动",
            "偏向技术分析：K线/指标/支撑压力更深入",
            "偏向基本面：财务/估值/机构研报更深入",
        ]
        plans: list[dict] = []
        for i in range(n):
            p = await self._create_plan(
                messages,
                mode="think",
                max_steps=max_plan_steps,
                candidate_hint=hints[i % len(hints)],
                retrieval_context=knowledge_context,
            )
            if p and isinstance(p.get("steps"), list) and p.get("steps"):
                plans.append(p)

        if not plans:
            # 规划失败：降级为 do（仍可能生成 plan），再不行就 run
            return await self.run_do(messages, max_plan_steps=max_plan_steps)

        best = await self._select_best_plan(messages, plans) or plans[0]
        return await self._run_with_plan(messages, best, mode="think", knowledge_context=knowledge_context)

    async def _run_with_plan(
        self,
        messages: List[ChatMessage],
        plan: dict,
        *,
        mode: str,
        knowledge_context: str = "",
    ) -> AgentResponse:
        """按计划执行（每步带 allow 约束）。"""
        from app.llm.client import LLMClient

        client = LLMClient(self.config)
        thoughts: list[AgentThought] = []
        tool_calls: list[AgentToolCall] = []

        steps = plan.get("steps") if isinstance(plan, dict) else None
        if not isinstance(steps, list) or not steps:
            return await self.run(messages)

        # 记录 plan（便于调试/审计）
        try:
            thoughts.append(AgentThought(thought=f"Plan({mode})", observation=json.dumps(plan, ensure_ascii=False)))
        except Exception:
            thoughts.append(AgentThought(thought=f"Plan({mode})", observation="{}"))

        all_messages = [ChatMessage(role="system", content=self._build_system_prompt())]
        kc = (knowledge_context or "").strip()
        if kc:
            all_messages.append(ChatMessage(role="system", content=f"【知识检索】\n{kc}"))
        all_messages += list(messages or [])

        tool_names = self._tool_name_set()

        # 每步最多迭代次数：避免长对话在 do/think 下成本失控
        step_max_iterations = 4
        final_max_iterations = 4

        # 统计 union allow：用于最终汇总阶段（避免最后一步想补一个数据却被卡死）
        union_allowed: set[str] = set()
        for s in steps:
            if not isinstance(s, dict):
                continue
            allowed = s.get("allowed_tools", [])
            if not isinstance(allowed, list):
                continue
            for a in allowed:
                name = self._clean_tool_name(str(a or ""))
                if name in tool_names:
                    union_allowed.add(name)

        try:
            # 按步骤执行
            for idx, s in enumerate(steps):
                if not isinstance(s, dict):
                    continue
                title = str(s.get("title", "") or f"步骤{idx+1}").strip()
                goal = str(s.get("goal", "") or "").strip()
                allowed = s.get("allowed_tools", [])
                if not isinstance(allowed, list):
                    allowed = []
                allowed_step = []
                for a in allowed:
                    name = self._clean_tool_name(str(a or ""))
                    if name in tool_names:
                        allowed_step.append(name)
                # 去重
                allowed_step = list(dict.fromkeys(allowed_step))

                all_messages.append(
                    ChatMessage(
                        role="user",
                        content=(
                            f"现在执行计划步骤 {idx+1}/{len(steps)}。\n"
                            f"- 标题: {title}\n"
                            f"- 目标: {goal}\n"
                            f"- 允许工具: {', '.join(allowed_step) if allowed_step else '（不允许调用工具）'}\n\n"
                            "要求：\n"
                            "1) 若需要调用工具，Action 必须在允许工具列表中；否则请直接思考并输出 Step Done。\n"
                            "2) 完成本步骤后必须输出 `Step Done: ...`（一句话总结）。\n"
                            "3) 除非这是最后一步且你已确认完成所有步骤，否则不要输出 Final Answer。\n"
                        ),
                    )
                )

                for _ in range(step_max_iterations):
                    resp = await client.chat(all_messages)
                    content = resp.response

                    thought, action, action_input, final_answer = self._parse_response(content)
                    step_done = self._parse_step_done(content)

                    thoughts.append(
                        AgentThought(
                            thought=thought,
                            action=action if action else None,
                            action_input=action_input if action_input else None,
                        )
                    )

                    # 步骤完成：进入下一步
                    if step_done:
                        thoughts[-1].observation = step_done
                        all_messages.append(ChatMessage(role="assistant", content=content))
                        break

                    # 提前 Final：若不是最后一步，按 Step Done 处理（避免卡死）
                    if final_answer and idx < len(steps) - 1:
                        thoughts[-1].observation = "模型提前输出 Final Answer，已视为 Step Done 并继续执行后续步骤。"
                        all_messages.append(ChatMessage(role="assistant", content=content))
                        break

                    # 最后一步可直接 Final
                    if final_answer and idx == len(steps) - 1:
                        return AgentResponse(
                            answer=final_answer,
                            thoughts=thoughts,
                            tool_calls=tool_calls,
                            model_name=self.config.model_name,
                            total_tokens=resp.total_tokens,
                        )

                    # 工具调用
                    if action:
                        tool = self._clean_tool_name(action)
                        if allowed_step and tool not in allowed_step:
                            result = {"error": f"ToolNotAllowed: {tool} 不在本步骤允许工具列表中"}
                        else:
                            result = await self._execute_tool(tool, action_input)

                        tool_calls.append(AgentToolCall(tool_name=tool, arguments=action_input, result=result))
                        result_str = json.dumps(result, ensure_ascii=False)
                        thoughts[-1].observation = result_str

                        all_messages.append(ChatMessage(role="assistant", content=content))
                        all_messages.append(ChatMessage(role="user", content=f"Observation: {result_str}"))
                        continue

                    # 无 Action/Step Done：提示模型按格式继续
                    all_messages.append(ChatMessage(role="assistant", content=content))
                    all_messages.append(ChatMessage(role="user", content="请继续本步骤：要么调用允许的工具（Action+Action Input），要么输出 Step Done。"))
                else:
                    # 迭代耗尽：强行进入下一步
                    thoughts.append(AgentThought(thought=f"步骤{idx+1}超出迭代上限，强制进入下一步", observation=""))

            # 所有步骤执行完：要求输出最终答案
            all_messages.append(
                ChatMessage(
                    role="user",
                    content=(
                        "所有计划步骤已执行完毕。现在请输出 Final Answer。\n"
                        "- 若存在工具返回 error/关键数据缺失，请明确说明并降低置信度。\n"
                        "- 若属于买卖决策/操作策略类问题，请输出“决策仪表盘 JSON”代码块并列出 data_sources（实际调用的工具名）。\n"
                    ),
                )
            )

            for _ in range(final_max_iterations):
                resp = await client.chat(all_messages)
                content = resp.response
                thought, action, action_input, final_answer = self._parse_response(content)
                thoughts.append(AgentThought(thought=thought, action=action if action else None, action_input=action_input if action_input else None))

                if final_answer:
                    return AgentResponse(
                        answer=final_answer,
                        thoughts=thoughts,
                        tool_calls=tool_calls,
                        model_name=self.config.model_name,
                        total_tokens=resp.total_tokens,
                    )

                if action:
                    tool = self._clean_tool_name(action)
                    if union_allowed and tool not in union_allowed:
                        result = {"error": f"ToolNotAllowed: {tool} 不在计划允许工具集合中"}
                    else:
                        result = await self._execute_tool(tool, action_input)
                    tool_calls.append(AgentToolCall(tool_name=tool, arguments=action_input, result=result))
                    result_str = json.dumps(result, ensure_ascii=False)
                    thoughts[-1].observation = result_str
                    all_messages.append(ChatMessage(role="assistant", content=content))
                    all_messages.append(ChatMessage(role="user", content=f"Observation: {result_str}"))
                    continue

                # 没有 Final Answer：直接返回原始内容
                return AgentResponse(
                    answer=content,
                    thoughts=thoughts,
                    tool_calls=tool_calls,
                    model_name=self.config.model_name,
                    total_tokens=resp.total_tokens,
                )

            return AgentResponse(
                answer="抱歉，我需要更多信息才能给出最终结论。",
                thoughts=thoughts,
                tool_calls=tool_calls,
                model_name=self.config.model_name,
                total_tokens=0,
            )
        finally:
            await client.close()

    async def run_mode_stream(
        self,
        messages: List[ChatMessage],
        *,
        mode: str,
        max_plan_steps: int = 6,
        plan_candidates: int = 3,
        knowledge_context: str = "",
    ) -> AsyncGenerator[str, None]:
        """按 mode 流式输出事件（Plan 模式为事件流，不做 token 级流）。"""
        m = (mode or "").strip().lower()
        if m in {"", "agent"}:
            async for chunk in self.run_stream(messages):
                yield chunk
            return

        # do/think：先产出 plan，再按步骤执行（事件粒度输出）
        plan: Optional[dict] = None
        if m == "think":
            # 多候选规划 → 评估挑选
            n = max(1, min(5, int(plan_candidates or 1)))
            hints = [
                "偏向数据充分性：多维度收集后再结论",
                "偏向成本控制：最少工具调用完成任务",
                "偏向风险排查：优先公告/资金/异动",
                "偏向技术分析：K线/指标/支撑压力更深入",
                "偏向基本面：财务/估值/机构研报更深入",
            ]
            plans: list[dict] = []
            for i in range(n):
                p = await self._create_plan(
                    messages,
                    mode="think",
                    max_steps=max_plan_steps,
                    candidate_hint=hints[i % len(hints)],
                    retrieval_context=knowledge_context,
                )
                if p and isinstance(p.get("steps"), list) and p.get("steps"):
                    plans.append(p)
            plan = await self._select_best_plan(messages, plans) or (plans[0] if plans else None)
        elif m == "do":
            plan = await self._create_plan(
                messages,
                mode="do",
                max_steps=max_plan_steps,
                retrieval_context=knowledge_context,
            )
        else:
            # 未知模式：降级为 agent
            async for chunk in self.run_stream(messages):
                yield chunk
            return

        if not plan or not isinstance(plan.get("steps"), list):
            # 规划失败：降级为原始 ReAct
            async for chunk in self.run_stream(messages):
                yield chunk
            return

        yield json.dumps({"type": "plan", "plan": plan}, ensure_ascii=False)

        # 复用 _run_with_plan 的执行逻辑，但以事件流形式输出关键节点
        from app.llm.client import LLMClient

        client = LLMClient(self.config)
        steps = plan.get("steps") or []
        all_messages = [ChatMessage(role="system", content=self._build_system_prompt())]
        kc = (knowledge_context or "").strip()
        if kc:
            all_messages.append(ChatMessage(role="system", content=f"【知识检索】\n{kc}"))
        all_messages += list(messages or [])
        tool_names = self._tool_name_set()

        step_max_iterations = 4
        union_allowed: set[str] = set()
        for s in steps:
            if not isinstance(s, dict):
                continue
            allowed = s.get("allowed_tools", [])
            if not isinstance(allowed, list):
                continue
            for a in allowed:
                name = self._clean_tool_name(str(a or ""))
                if name in tool_names:
                    union_allowed.add(name)

        try:
            for idx, s in enumerate(steps):
                if not isinstance(s, dict):
                    continue
                title = str(s.get("title", "") or f"步骤{idx+1}").strip()
                goal = str(s.get("goal", "") or "").strip()
                allowed = s.get("allowed_tools", [])
                if not isinstance(allowed, list):
                    allowed = []
                allowed_step = []
                for a in allowed:
                    name = self._clean_tool_name(str(a or ""))
                    if name in tool_names:
                        allowed_step.append(name)
                allowed_step = list(dict.fromkeys(allowed_step))

                yield json.dumps(
                    {"type": "step_start", "step_index": idx + 1, "step_total": len(steps), "title": title, "goal": goal},
                    ensure_ascii=False,
                )

                all_messages.append(
                    ChatMessage(
                        role="user",
                        content=(
                            f"现在执行计划步骤 {idx+1}/{len(steps)}。\n"
                            f"- 标题: {title}\n"
                            f"- 目标: {goal}\n"
                            f"- 允许工具: {', '.join(allowed_step) if allowed_step else '（不允许调用工具）'}\n\n"
                            "要求：完成本步骤后输出 Step Done: ...；除非最后一步否则不要输出 Final Answer。"
                        ),
                    )
                )

                for _ in range(step_max_iterations):
                    resp = await client.chat(all_messages)
                    content = resp.response

                    thought, action, action_input, final_answer = self._parse_response(content)
                    step_done = self._parse_step_done(content)

                    if step_done:
                        yield json.dumps({"type": "step_done", "step_index": idx + 1, "content": step_done}, ensure_ascii=False)
                        all_messages.append(ChatMessage(role="assistant", content=content))
                        break

                    if final_answer and idx < len(steps) - 1:
                        yield json.dumps(
                            {"type": "step_done", "step_index": idx + 1, "content": "模型提前输出 Final Answer，已视为步骤完成"},
                            ensure_ascii=False,
                        )
                        all_messages.append(ChatMessage(role="assistant", content=content))
                        break

                    if final_answer and idx == len(steps) - 1:
                        yield json.dumps({"type": "final_answer", "content": final_answer}, ensure_ascii=False)
                        return

                    if action:
                        tool = self._clean_tool_name(action)
                        yield json.dumps({"type": "tool_call", "tool": tool, "arguments": action_input}, ensure_ascii=False)
                        if allowed_step and tool not in allowed_step:
                            result = {"error": f"ToolNotAllowed: {tool} 不在本步骤允许工具列表中"}
                        else:
                            result = await self._execute_tool(tool, action_input)
                        result_str = json.dumps(result, ensure_ascii=False)
                        yield json.dumps({"type": "observation", "content": result_str}, ensure_ascii=False)
                        all_messages.append(ChatMessage(role="assistant", content=content))
                        all_messages.append(ChatMessage(role="user", content=f"Observation: {result_str}"))
                        continue

                    all_messages.append(ChatMessage(role="assistant", content=content))
                    all_messages.append(ChatMessage(role="user", content="请按格式输出 Step Done 或 Action。"))

            all_messages.append(ChatMessage(role="user", content="所有步骤已完成。请输出 Final Answer。"))

            for _ in range(4):
                resp = await client.chat(all_messages)
                content = resp.response
                _, action, action_input, final_answer = self._parse_response(content)
                if final_answer:
                    yield json.dumps({"type": "final_answer", "content": final_answer}, ensure_ascii=False)
                    return
                if action:
                    tool = self._clean_tool_name(action)
                    yield json.dumps({"type": "tool_call", "tool": tool, "arguments": action_input}, ensure_ascii=False)
                    if union_allowed and tool not in union_allowed:
                        result = {"error": f"ToolNotAllowed: {tool} 不在计划允许工具集合中"}
                    else:
                        result = await self._execute_tool(tool, action_input)
                    result_str = json.dumps(result, ensure_ascii=False)
                    yield json.dumps({"type": "observation", "content": result_str}, ensure_ascii=False)
                    all_messages.append(ChatMessage(role="assistant", content=content))
                    all_messages.append(ChatMessage(role="user", content=f"Observation: {result_str}"))
                    continue
                yield json.dumps({"type": "final_answer", "content": content}, ensure_ascii=False)
                return

            yield json.dumps({"type": "final_answer", "content": "抱歉，我需要更多信息才能给出最终结论。"}, ensure_ascii=False)
        finally:
            await client.close()

    def _build_system_prompt(self) -> str:
        """构建系统Prompt"""
        tools_desc = json.dumps(TOOLS, ensure_ascii=False, indent=2)
        return f"""你是一个专业的股票分析助手，可以帮助用户查询和分析股票数据。

你可以使用以下工具：
{tools_desc}

当用户提问时，请按照以下ReACT模式回答（必须严格遵守格式，便于程序解析）：

1. Thought: 思考用户的问题，分析需要做什么
2. Action: 选择合适的工具
3. Action Input: 工具的输入参数（JSON对象；尽量写成单行，不要用 ``` 代码块）
4. Observation: 工具返回的结果
5. 重复1-4直到获取足够信息
6. Final Answer: 给出最终回答

注意：
- Thought 只写简短计划/下一步（不要展开推理细节）。
- Action 必须是工具列表中的 name 原样。
- 如果工具返回 error 字段，请在 Final Answer 中说明失败原因，并给出可行的替代方案或下一步建议。
- 不要编造工具返回的数据；需要数据时必须先调用工具。
- 如果用户的问题属于“买卖决策/是否值得/给操作策略/仓位/止损/目标价”，请在 Final Answer 中尽量输出**结构化**结论（参考 daily_stock_analysis 的决策仪表盘思路）：
  1) 先给一句话结论（🟢/🟡/🔴/⚠️ + 操作建议）
  2) 再给一个 JSON 代码块（字段尽量齐全但保持精炼），示例字段：
     - sentiment_score: 0-100 整数
     - trend_prediction: 强烈看多/看多/震荡/看空/强烈看空
     - operation_advice: 买入/加仓/持有/减仓/卖出/观望
     - confidence_level: 高/中/低
     - key_levels: support/resistance/stop_loss/take_profit（尽量给出数值或明确条件）
     - checklist: 3-6 条 ✅/⚠️/❌ 检查项
     - risk_alerts / positive_catalysts: 列表（各 1-5 条）
     - data_sources: 本次实际调用过的工具名列表（不要杜撰）
  3) 若关键数据缺失（例如筹码/公告/研报无数据），必须在结论中显式标注“不足/不可用”，并降低 confidence_level。

请用中文回答。
"""

    async def _execute_tool(self, tool_name: str, arguments: dict) -> Any:
        """执行工具 - 完整工具集"""
        from app.services.stock_service import StockService
        from app.services.market_service import MarketService
        from app.services.news_service import NewsService
        from app.services.search_service import SearchService
        from app.datasources.eastmoney import EastMoneyClient
        from app.utils.helpers import normalize_stock_code

        stock_service = StockService(self.db)
        market_service = MarketService(self.db)
        news_service = NewsService(self.db)
        search_service = SearchService(self.db)

        try:
            # 1. query_stock_price - 实时股价
            if tool_name == "query_stock_price":
                codes = [normalize_stock_code(c) for c in str(arguments.get("stock_codes", "") or "").split(",") if c and c.strip()]
                quotes = await stock_service.get_realtime_quotes(codes)
                return {"stocks": [q.model_dump() for q in quotes]}

            # 2. query_stock_kline - K线数据
            elif tool_name == "query_stock_kline":
                code = normalize_stock_code(str(arguments.get("stock_code", "") or ""))
                kline = await stock_service.get_kline(
                    code,
                    "day",
                    int(arguments.get("days", 30) or 30),
                )
                # 返回最近10条数据的摘要
                data = kline.data[-10:] if kline.data else []
                return {
                    "stock_code": kline.stock_code,
                    "stock_name": kline.stock_name,
                    "klines": [d.model_dump() for d in data]
                }

            # 3. query_stock_info - 股票信息查询
            elif tool_name == "query_stock_info":
                results = await stock_service.search_stocks(
                    arguments["search_word"], limit=10
                )
                return {"results": [r.model_dump() for r in results]}

            # 4. get_financial_report - 财务报表
            elif tool_name == "get_financial_report":
                async with EastMoneyClient() as client:
                    return await client.get_financial_report(normalize_stock_code(str(arguments.get("stock_code", "") or "")))

            # 5. choice_stock_by_indicators - 自然语言选股
            elif tool_name == "choice_stock_by_indicators":
                result = await search_service.search_by_words(arguments["words"])
                # 限制返回数量避免token过多
                stocks = result.get("results", [])[:20]
                return {
                    "conditions": result.get("conditions", []),
                    "stocks": stocks,
                    "total": result.get("total", 0)
                }

            # 6. query_market_news - 市场资讯
            elif tool_name == "query_market_news":
                news = await news_service.get_latest_news(
                    limit=arguments.get("limit", 20)
                )
                return {
                    "news": [
                        {"title": n.title, "content": n.content[:200] if n.content else "", "publish_time": str(n.publish_time)}
                        for n in news.items[:20]
                    ]
                }

            # 7. query_stock_news - 股票新闻搜索
            elif tool_name == "query_stock_news":
                news = await news_service.search_news(
                    arguments["search_words"],
                    limit=20
                )
                return {
                    "news": [
                        {"title": n.title, "content": n.content[:200] if n.content else "", "publish_time": str(n.publish_time)}
                        for n in news.items[:20]
                    ]
                }

            # 8. query_interactive_qa - 投资者互动问答
            elif tool_name == "query_interactive_qa":
                async with EastMoneyClient() as client:
                    qa_list = await client.get_interactive_qa(
                        keyword=arguments.get("keyword", ""),
                        page=arguments.get("page", 1),
                        page_size=arguments.get("page_size", 20)
                    )
                return {"qa_list": qa_list}

            # 9. get_industry_research_report - 行业研究报告
            elif tool_name == "get_industry_research_report":
                async with EastMoneyClient() as client:
                    reports = await client.get_industry_research_reports(
                        name=arguments.get("name", ""),
                        code=arguments.get("code", "")
                    )
                return {"reports": reports[:10]}

            # 10. query_economic_data - 宏观经济数据
            elif tool_name == "query_economic_data":
                data = await market_service.get_economic_data(
                    indicator=arguments.get("flag", "all"),
                    count=20
                )
                return data.model_dump() if data else {}

            # 11. query_bk_dict - 板块/行业字典
            elif tool_name == "query_bk_dict":
                async with EastMoneyClient() as client:
                    industries = await client.get_industry_rank("change_percent", "desc", 50)
                    concepts = await client.get_concept_rank("change_percent", "desc", 50)
                return {
                    "industries": [{"code": i.bk_code, "name": i.bk_name} for i in industries.items],
                    "concepts": [{"code": c.bk_code, "name": c.bk_name} for c in concepts.items]
                }

            # 12. get_money_flow_rank - 资金流向排名
            elif tool_name == "get_money_flow_rank":
                flow = await market_service.get_money_flow(
                    order=arguments.get("order", "desc"),
                    limit=arguments.get("limit", 20)
                )
                return {"stocks": [i.model_dump() for i in flow.items]}

            # 13. query_market_overview - 市场概览
            elif tool_name == "query_market_overview":
                overview = await market_service.get_market_overview()
                return overview.model_dump() if overview else {}

            # 14. query_long_tiger - 龙虎榜
            elif tool_name == "query_long_tiger":
                data = await market_service.get_long_tiger(arguments.get("trade_date"))
                if not data:
                    return {"items": [], "trade_date": arguments.get("trade_date", "")}
                payload = data.model_dump()
                # 控制返回条数，避免 token 爆炸
                items = payload.get("items") or []
                payload["items"] = items[:20]
                return payload

            # 15. query_north_flow - 北向资金
            elif tool_name == "query_north_flow":
                days = int(arguments.get("days", 30) or 30)
                data = await market_service.get_north_flow(days)
                if not isinstance(data, dict):
                    return {"current": None, "history": []}
                history = data.get("history") or []
                if isinstance(history, list):
                    data["history"] = history[: min(len(history), 30)]
                return data

            # 16. query_industry_rank - 行业排名
            elif tool_name == "query_industry_rank":
                resp = await market_service.get_industry_rank(
                    sort_by=arguments.get("sort_by", "change_percent"),
                    order=arguments.get("order", "desc"),
                    limit=int(arguments.get("limit", 20) or 20),
                )
                payload = resp.model_dump() if resp else {"items": [], "update_time": ""}
                payload["items"] = (payload.get("items") or [])[:20]
                return payload

            # 17. query_concept_rank - 概念板块排名
            elif tool_name == "query_concept_rank":
                resp = await market_service.get_concept_rank(
                    sort_by=arguments.get("sort_by", "change_percent"),
                    order=arguments.get("order", "desc"),
                    limit=int(arguments.get("limit", 20) or 20),
                )
                payload = resp.model_dump() if resp else {"items": [], "update_time": ""}
                payload["items"] = (payload.get("items") or [])[:20]
                return payload

            # 18. query_industry_money_flow - 行业/概念资金流向
            elif tool_name == "query_industry_money_flow":
                category = str(arguments.get("category", "hangye") or "hangye")
                sort_by = str(arguments.get("sort_by", "main_inflow") or "main_inflow")
                data = await market_service.get_industry_money_flow(category=category, sort_by=sort_by)
                if isinstance(data, dict) and isinstance(data.get("items"), list):
                    data["items"] = data["items"][:30]
                return data

            # 19. query_stock_money_rank - 股票资金流入排名
            elif tool_name == "query_stock_money_rank":
                sort_by = str(arguments.get("sort_by", "main_inflow") or "main_inflow")
                limit = int(arguments.get("limit", 20) or 20)
                data = await market_service.get_stock_money_rank(sort_by=sort_by, limit=limit)
                if isinstance(data, dict) and isinstance(data.get("items"), list):
                    data["items"] = data["items"][:limit]
                return data

            # 20. query_volume_ratio_rank - 量比排名
            elif tool_name == "query_volume_ratio_rank":
                min_ratio = float(arguments.get("min_ratio", 2.0) or 2.0)
                limit = int(arguments.get("limit", 20) or 20)
                data = await market_service.get_volume_ratio_rank(min_ratio=min_ratio, limit=limit)
                if isinstance(data, dict) and isinstance(data.get("items"), list):
                    data["items"] = data["items"][:limit]
                return data

            # 21. query_limit_stats - 涨跌停统计
            elif tool_name == "query_limit_stats":
                data = await market_service.get_limit_stats()
                if isinstance(data, dict):
                    # 名单只保留前 50，避免 token 爆炸
                    for k in ("limit_up_stocks", "limit_down_stocks"):
                        if isinstance(data.get(k), list):
                            data[k] = data[k][:50]
                return data

            # 22. get_stock_detail - 股票全量详情
            elif tool_name == "get_stock_detail":
                code = normalize_stock_code(str(arguments.get("stock_code", "") or ""))
                detail = await stock_service.get_stock_detail(code)
                if not isinstance(detail, dict):
                    return {}
                # 控制返回体积：只返回常用字段
                return {
                    "quote": detail.get("quote"),
                    "basic": detail.get("basic"),
                    "fundamental": detail.get("fundamental"),
                    "rating": detail.get("rating"),
                    "shareholders": (detail.get("shareholders") or [])[:30] if isinstance(detail.get("shareholders"), list) else detail.get("shareholders"),
                    "dividend": (detail.get("dividend") or [])[:30] if isinstance(detail.get("dividend"), list) else detail.get("dividend"),
                    "concepts": detail.get("concepts"),
                }

            # 23. query_chip_distribution - 筹码分布
            elif tool_name == "query_chip_distribution":
                code = normalize_stock_code(str(arguments.get("stock_code", "") or ""))
                resp = await stock_service.get_chip_distribution(code)
                return resp.model_dump()

            # 24. query_technical_analysis - 技术分析
            elif tool_name == "query_technical_analysis":
                code = normalize_stock_code(str(arguments.get("stock_code", "") or ""))
                days = int(arguments.get("days", 120) or 120)

                kline = await stock_service.get_kline(code, "day", days)
                klines = [d.model_dump() for d in (kline.data or [])]

                from app.services.technical_service import TechnicalService

                svc = TechnicalService()
                try:
                    result = await svc.analyze(code=code, klines=klines, stock_name=kline.stock_name)
                except Exception as e:
                    return {"error": f"技术分析失败: {e}", "stock_code": code, "kline_count": len(klines)}

                return {
                    "stock_code": result.code,
                    "stock_name": result.name,
                    "current_price": result.current_price,
                    "change_percent": result.change_percent,
                    "score": result.score,
                    "buy_signal": result.buy_signal.value,
                    "trend": {
                        "status": result.trend.status.value,
                        "ma_alignment": result.trend.ma_alignment,
                        "ma5": result.trend.ma_5,
                        "ma10": result.trend.ma_10,
                        "ma20": result.trend.ma_20,
                        "ma60": result.trend.ma_60,
                        "bias_ma5": result.trend.bias_5,
                        "bias_ma10": result.trend.bias_10,
                        "price_position": result.trend.price_position,
                    },
                    "macd": {
                        "dif": result.macd.dif,
                        "dea": result.macd.dea,
                        "macd": result.macd.macd,
                        "signal": result.macd.signal.value,
                    },
                    "rsi": {
                        "rsi_6": result.rsi.rsi_6,
                        "rsi_12": result.rsi.rsi_12,
                        "rsi_24": result.rsi.rsi_24,
                        "signal": result.rsi.signal.value,
                    },
                    "volume": {
                        "volume_ratio": result.volume.volume_ratio,
                        "volume_trend": result.volume.volume_trend,
                        "is_volume_breakout": result.volume.is_volume_breakout,
                        "avg_volume_5": result.volume.avg_volume_5,
                        "avg_volume_10": result.volume.avg_volume_10,
                    },
                    "support_resistance": {
                        "support_1": result.support_resistance.support_1,
                        "support_2": result.support_resistance.support_2,
                        "resistance_1": result.support_resistance.resistance_1,
                        "resistance_2": result.support_resistance.resistance_2,
                        "distance_to_support": result.support_resistance.distance_to_support,
                        "distance_to_resistance": result.support_resistance.distance_to_resistance,
                    },
                    "summary": result.summary,
                    "analysis_time": result.analysis_time.isoformat(),
                }

            # 25. query_stock_notices - 公司公告
            elif tool_name == "query_stock_notices":
                code = normalize_stock_code(str(arguments.get("stock_code", "") or ""))
                limit = int(arguments.get("limit", 20) or 20)
                data = await news_service.get_stock_notices(code, limit=limit)
                if isinstance(data, dict) and isinstance(data.get("items"), list):
                    data["items"] = data["items"][:limit]
                return data

            # 26. query_stock_research_reports - 研报
            elif tool_name == "query_stock_research_reports":
                code = normalize_stock_code(str(arguments.get("stock_code", "") or ""))
                limit = int(arguments.get("limit", 10) or 10)
                rows = await market_service.get_stock_research_reports(code, limit=limit)
                return {"stock_code": code, "items": (rows or [])[:limit], "total": len(rows or [])}

            # 27. query_hot_topics - 热门话题
            elif tool_name == "query_hot_topics":
                size = int(arguments.get("size", 20) or 20)
                return await news_service.get_hot_topics(size=size)

            # 28. query_hot_events - 热门事件
            elif tool_name == "query_hot_events":
                size = int(arguments.get("size", 20) or 20)
                return await news_service.get_hot_events(size=size)

            # 29. search_web - 联网搜索
            elif tool_name == "search_web":
                query = str(arguments.get("query", "") or "").strip()
                limit = int(arguments.get("limit", 8) or 8)
                if not query:
                    return {"items": [], "context": "query 不能为空"}

                from app.services.news_search_service import NewsSearchService

                service = NewsSearchService(self.db)
                try:
                    items = await service.search(query=query, limit=limit)
                    context = service.format_as_context(query=query, items=items, max_items=min(5, limit))
                    return {
                        "query": query,
                        "context": context,
                        "items": [
                            {
                                "title": i.title,
                                "source": i.source,
                                "publish_time": i.publish_time.isoformat() if i.publish_time else "",
                                "url": i.url,
                                "content": (i.content or "")[:240],
                            }
                            for i in (items or [])[:limit]
                        ],
                    }
                finally:
                    await service.close()

            return {"error": f"Unknown tool: {tool_name}"}

        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    def _clean_tool_name(name: str) -> str:
        """清理工具名，避免模型输出带引号/反引号导致匹配失败"""
        return re.sub(r"[`\"'\u201c\u201d]", "", (name or "").strip())

    @staticmethod
    def _extract_json_object(text: str) -> Optional[str]:
        """从文本中提取第一个 JSON 对象字符串（{...}），用于解析 Action Input"""
        if not text:
            return None

        start = text.find("{")
        if start < 0:
            return None

        depth = 0
        in_string = False
        escape = False

        for i in range(start, len(text)):
            ch = text[i]
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
                continue

            if ch == '"':
                in_string = True
                continue

            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start : i + 1]

        return None

    def _parse_action_input(self, raw: str) -> dict:
        """解析 Action Input（兼容多行/代码块/夹杂文本）"""
        text = (raw or "").strip()
        if not text:
            return {}

        # 1) 优先提取代码块内内容
        fence = re.search(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.IGNORECASE | re.DOTALL)
        if fence:
            text = (fence.group(1) or "").strip()

        # 2) 直接解析（适配单行 JSON）
        try:
            data = json.loads(text)
            return data if isinstance(data, dict) else {}
        except Exception:
            pass

        # 3) 尝试提取 JSON 对象片段
        obj = self._extract_json_object(text)
        if not obj:
            return {}
        try:
            data = json.loads(obj)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _parse_response(self, content: str) -> tuple:
        """解析Agent响应，返回(thought, action, action_input, final_answer)"""
        thought = ""
        action = ""
        action_input_text = ""
        final_answer = ""

        lines = (content or "").strip().splitlines()
        current_section: Optional[str] = None

        def match_section(line: str) -> Optional[str]:
            # 兼容英文/中文分隔符
            patterns = {
                "thought": r"^\s*(thought|思考)\s*[:：]\s*",
                "action": r"^\s*(action|行动)\s*[:：]\s*",
                "action_input": r"^\s*(action\s*input|行动\s*输入)\s*[:：]\s*",
                "final_answer": r"^\s*(final\s*answer|最终回答|最终答案)\s*[:：]\s*",
            }
            for key, pat in patterns.items():
                if re.match(pat, line, flags=re.IGNORECASE):
                    return key
            return None

        def strip_header(line: str) -> str:
            # 去掉 "xxx:" 前缀，保留后面的内容
            return re.sub(r"^\s*[^:：]{1,30}\s*[:：]\s*", "", line).strip()

        for line in lines:
            section = match_section(line)
            if section:
                current_section = section
                inline = strip_header(line)
                if section == "thought":
                    thought = inline
                elif section == "action":
                    action = inline
                elif section == "action_input":
                    action_input_text = inline
                elif section == "final_answer":
                    final_answer = inline
                continue

            if current_section == "thought":
                thought = (thought + "\n" + line).strip() if thought else line.strip()
            elif current_section == "action_input":
                action_input_text = (action_input_text + "\n" + line).strip() if action_input_text else line.strip()
            elif current_section == "final_answer":
                final_answer = (final_answer + "\n" + line).strip() if final_answer else line.strip()

        action = self._clean_tool_name(action)
        action_input = self._parse_action_input(action_input_text)
        return thought.strip(), action.strip(), action_input, final_answer.strip()

    async def run(self, messages: List[ChatMessage]) -> AgentResponse:
        """运行Agent"""
        from app.llm.client import LLMClient

        client = LLMClient(self.config)
        thoughts = []
        tool_calls = []

        try:
            # 添加系统Prompt
            all_messages = [
                ChatMessage(role="system", content=self._build_system_prompt())
            ] + messages

            # 提升迭代上限：对齐“先充分收集信息再结论”的工作方式（仍需控制工具输出体积避免成本失控）
            max_iterations = 7
            for _ in range(max_iterations):
                response = await client.chat(all_messages)
                content = response.response

                thought, action, action_input, final_answer = self._parse_response(content)

                thoughts.append(AgentThought(
                    thought=thought,
                    action=action if action else None,
                    action_input=action_input if action_input else None,
                ))

                if final_answer:
                    return AgentResponse(
                        answer=final_answer,
                        thoughts=thoughts,
                        tool_calls=tool_calls,
                        model_name=self.config.model_name,
                        total_tokens=response.total_tokens,
                    )

                if action:
                    # 执行工具
                    result = await self._execute_tool(action, action_input)
                    result_str = json.dumps(result, ensure_ascii=False)

                    tool_calls.append(AgentToolCall(
                        tool_name=action,
                        arguments=action_input,
                        result=result,
                    ))

                    # 更新最后一个thought的observation
                    thoughts[-1].observation = result_str

                    # 添加observation到消息
                    all_messages.append(ChatMessage(role="assistant", content=content))
                    all_messages.append(ChatMessage(role="user", content=f"Observation: {result_str}"))
                else:
                    # 没有action也没有final answer，可能是格式问题
                    return AgentResponse(
                        answer=content,
                        thoughts=thoughts,
                        tool_calls=tool_calls,
                        model_name=self.config.model_name,
                        total_tokens=response.total_tokens,
                    )

            # 超过最大迭代次数
            return AgentResponse(
                answer="抱歉，我需要更多信息才能回答这个问题。",
                thoughts=thoughts,
                tool_calls=tool_calls,
                model_name=self.config.model_name,
                total_tokens=0,
            )
        finally:
            await client.close()

    async def run_stream(self, messages: List[ChatMessage]) -> AsyncGenerator[str, None]:
        """流式运行Agent"""
        from app.llm.client import LLMClient

        client = LLMClient(self.config)

        try:
            all_messages = [
                ChatMessage(role="system", content=self._build_system_prompt())
            ] + messages

            max_iterations = 7
            for iteration in range(max_iterations):
                full_content = ""

                async for chunk in client.chat_stream(all_messages):
                    full_content += chunk.content
                    yield json.dumps({
                        "type": "content",
                        "content": chunk.content,
                        "done": chunk.done,
                    })

                thought, action, action_input, final_answer = self._parse_response(full_content)

                if final_answer:
                    yield json.dumps({
                        "type": "final_answer",
                        "content": final_answer,
                    })
                    break

                if action:
                    yield json.dumps({
                        "type": "tool_call",
                        "tool": action,
                        "arguments": action_input,
                    })

                    result = await self._execute_tool(action, action_input)
                    result_str = json.dumps(result, ensure_ascii=False)

                    yield json.dumps({
                        "type": "observation",
                        "content": result_str,
                    })

                    all_messages.append(ChatMessage(role="assistant", content=full_content))
                    all_messages.append(ChatMessage(role="user", content=f"Observation: {result_str}"))
                else:
                    break
        finally:
            await client.close()
