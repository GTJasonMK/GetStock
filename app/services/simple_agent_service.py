# Simple Agent Service
"""
简化版“数据分析→结论”流水线（按用户最新需求收敛）。

设计原则：
- 不依赖复杂的 Plan/ReAct/知识库编排；
- 固定并发拉取核心数据（容错，不因单点失败中断）；
- 将数据压缩为“可读/可控/可审计”的 JSON 上下文，交给 LLM 输出结论；
- 明确列出缺失项与数据来源（避免看似“分析了很多”但其实没有数据）。
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.market_service import MarketService
from app.services.news_search_service import NewsSearchService
from app.services.stock_service import StockService
from app.services.technical_service import TechnicalService
from app.utils.helpers import normalize_stock_code


def _json_dumps(obj: Any) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False)
    except Exception:
        return "{}"


def _truncate(text: str, max_len: int) -> str:
    s = (text or "").strip()
    if len(s) <= max_len:
        return s
    return s[: max(0, max_len - 1)] + "…"


def _coerce_float(val: Any) -> Optional[float]:
    try:
        if val is None:
            return None
        if isinstance(val, bool):
            return None
        return float(val)
    except Exception:
        return None


def _extract_stock_code_from_text(text: str) -> str:
    """从文本中尽量抽取股票代码（只做轻量规则，不引入复杂 NER）。"""
    t = (text or "").strip()
    if not t:
        return ""

    m = re.search(r"\b(?:(sh|sz|hk|us)\s*)?(\d{5,6})\b", t, flags=re.IGNORECASE)
    if not m:
        return ""

    prefix = (m.group(1) or "").lower()
    code = m.group(2) or ""
    if prefix:
        return normalize_stock_code(prefix + code)

    # 未带前缀时仅处理 A 股 6 位码（默认按 60/68 -> sh，其余 -> sz）
    if len(code) == 6:
        if code.startswith(("60", "68")):
            return normalize_stock_code("sh" + code)
        return normalize_stock_code("sz" + code)

    return ""


@dataclass
class SimpleAgentContext:
    stock_code: str
    stock_name: str
    context_json: str
    data_sources: list[str]
    missing: list[str]


class SimpleAgentService:
    """简化版 Agent：负责收集数据并生成可注入上下文。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def build_context(
        self,
        *,
        question: str,
        stock_code: str = "",
        stock_name: str = "",
        enable_retrieval: bool = False,
    ) -> SimpleAgentContext:
        q = (question or "").strip()
        code = normalize_stock_code(stock_code) if stock_code else _extract_stock_code_from_text(q)

        stock_service = StockService(self.db)
        market_service = MarketService(self.db)
        technical_service = TechnicalService()

        data_sources: list[str] = []
        missing: list[str] = []

        # 没有股票上下文时：仅做市场概览 +（可选）资讯检索，保持简单
        if not code:
            market_overview = None
            try:
                market_overview = await market_service.get_market_overview()
                data_sources.append("market_overview")
            except Exception:
                missing.append("market_overview")

            retrieval_context = ""
            if enable_retrieval and q:
                try:
                    svc = NewsSearchService(self.db)
                    items = await svc.search(query=q, limit=6)
                    retrieval_context = svc.format_as_context(query=q, items=items, max_items=4) if items else ""
                    if retrieval_context:
                        data_sources.append("news_search")
                except Exception:
                    missing.append("news_search")
                finally:
                    try:
                        await svc.close()  # type: ignore[has-type]
                    except Exception:
                        pass

            payload = {
                "question": _truncate(q, 500),
                "stock_code": "",
                "stock_name": "",
                "market_overview": market_overview.model_dump() if market_overview else None,
                "retrieval_context": retrieval_context,
                "data_sources": data_sources,
                "missing": missing,
            }
            return SimpleAgentContext(
                stock_code="",
                stock_name="",
                context_json=_json_dumps(payload),
                data_sources=data_sources,
                missing=missing,
            )

        # 有股票上下文：并发拉取核心信息
        inferred_name = stock_name or ""
        if not inferred_name:
            try:
                basic = await stock_service._get_basic_info(code)
                inferred_name = (basic or {}).get("name", "") if isinstance(basic, dict) else ""
            except Exception:
                inferred_name = ""

        async def _safe_call(name: str, coro):
            try:
                value = await coro
                return name, value, None
            except Exception as e:
                return name, None, str(e)

        tasks = [
            _safe_call("stock_detail", stock_service.get_stock_detail(code)),
            _safe_call("kline_long", stock_service.get_kline(code, "day", 120)),
            _safe_call("chip_distribution", stock_service.get_chip_distribution(code)),
            _safe_call("notices", market_service.get_stock_notices(code, 10)),
            _safe_call("research_reports", market_service.get_stock_research_reports(code, 10)),
            _safe_call("market_overview", market_service.get_market_overview()),
        ]

        retrieval_task = None
        if enable_retrieval and q:
            retrieval_task = _safe_call("news_search", self._build_retrieval_context(query=" ".join([inferred_name, code, q]).strip() or q))
            tasks.append(retrieval_task)

        results = await asyncio.gather(*tasks)
        out: dict[str, Any] = {}
        errors: dict[str, str] = {}
        for name, value, err in results:
            out[name] = value
            if err:
                errors[name] = err

        # 记录可用性
        for key in ["stock_detail", "kline_long", "chip_distribution", "notices", "research_reports", "market_overview", "news_search"]:
            if key not in out:
                continue
            if out.get(key) is None:
                missing.append(key)
            else:
                # kline/chip 有 available 字段时进一步判断
                if key == "kline_long":
                    try:
                        if not bool(getattr(out[key], "available", True)):
                            missing.append("kline_long")
                        else:
                            data_sources.append("kline")
                    except Exception:
                        data_sources.append("kline")
                elif key == "chip_distribution":
                    try:
                        if not bool(getattr(out[key], "available", True)):
                            missing.append("chip_distribution")
                        else:
                            data_sources.append("chip_distribution")
                    except Exception:
                        data_sources.append("chip_distribution")
                else:
                    data_sources.append(key)

        # 技术分析：依赖 long kline（至少 60 条）
        technical: Optional[dict] = None
        try:
            kline = out.get("kline_long")
            if kline and getattr(kline, "available", True) and getattr(kline, "data", None):
                klines = []
                for d in list(getattr(kline, "data") or []):
                    klines.append(
                        {
                            "date": getattr(d, "date", ""),
                            "open": _coerce_float(getattr(d, "open", None)) or 0.0,
                            "close": _coerce_float(getattr(d, "close", None)) or 0.0,
                            "high": _coerce_float(getattr(d, "high", None)) or 0.0,
                            "low": _coerce_float(getattr(d, "low", None)) or 0.0,
                            "volume": int(getattr(d, "volume", 0) or 0),
                        }
                    )
                if len(klines) >= 60:
                    r = await technical_service.analyze(code=code, klines=klines, stock_name=inferred_name)
                    sr = r.support_resistance
                    technical = {
                        "score": int(r.score),
                        "buy_signal": str(r.buy_signal.value),
                        "trend": str(r.trend.status.value),
                        "macd_signal": str(r.macd.signal.value),
                        "rsi_signal": str(r.rsi.signal.value),
                        "support_resistance": {
                            "support_1": float(sr.support_1),
                            "support_2": float(sr.support_2),
                            "resistance_1": float(sr.resistance_1),
                            "resistance_2": float(sr.resistance_2),
                        },
                        "summary": r.summary,
                    }
                    data_sources.append("technical_analysis")
                else:
                    missing.append("technical_analysis")
            else:
                missing.append("technical_analysis")
        except Exception:
            missing.append("technical_analysis")

        # 压缩输出：避免把大数组直接塞进 prompt
        detail = out.get("stock_detail") if isinstance(out.get("stock_detail"), dict) else {}
        quote = (detail or {}).get("quote") if isinstance(detail, dict) else None
        fundamental = (detail or {}).get("fundamental") if isinstance(detail, dict) else {}
        money_flow = (detail or {}).get("money_flow") if isinstance(detail, dict) else []

        kline_short = None
        try:
            k = out.get("kline_long")
            if k and getattr(k, "data", None):
                data = list(getattr(k, "data") or [])
                kline_short = [d.model_dump() for d in data[-30:]]
        except Exception:
            kline_short = None

        chip = None
        try:
            c = out.get("chip_distribution")
            if c and getattr(c, "available", True) and getattr(c, "data", None):
                chip = c.data.model_dump()  # type: ignore[union-attr]
        except Exception:
            chip = None

        notices = out.get("notices") if isinstance(out.get("notices"), list) else []
        reports = out.get("research_reports") if isinstance(out.get("research_reports"), list) else []
        news_ctx = out.get("news_search") if isinstance(out.get("news_search"), str) else ""
        market_overview = out.get("market_overview")

        payload = {
            "question": _truncate(q, 500),
            "stock_code": code,
            "stock_name": inferred_name,
            "quote": quote,
            "fundamental": fundamental,
            "money_flow": money_flow[:10] if isinstance(money_flow, list) else money_flow,
            "kline_last30": kline_short,
            "technical": technical,
            "chip_distribution": chip,
            "notices": notices[:10],
            "research_reports": reports[:10],
            "market_overview": market_overview.model_dump() if market_overview else None,
            "retrieval_context": _truncate(news_ctx, 1600),
            "errors": {k: _truncate(v, 200) for k, v in errors.items()},
            "data_sources": list(dict.fromkeys(data_sources)),
            "missing": list(dict.fromkeys(missing)),
        }

        return SimpleAgentContext(
            stock_code=code,
            stock_name=inferred_name,
            context_json=_json_dumps(payload),
            data_sources=list(dict.fromkeys(data_sources)),
            missing=list(dict.fromkeys(missing)),
        )

    async def _build_retrieval_context(self, query: str) -> str:
        q = (query or "").strip()
        if not q:
            return ""
        svc = NewsSearchService(self.db)
        try:
            items = await svc.search(query=q, limit=8)
            if not items:
                return ""
            return svc.format_as_context(query=q, items=items, max_items=5)
        finally:
            await svc.close()

