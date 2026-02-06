# Stock Service
"""
股票数据服务 - 完整实现
"""

import asyncio
import logging
from typing import List, Optional, Dict, Any

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.market import StockBasic, StockInfoHK, StockInfoUS
from app.schemas.stock import (
    StockSearchResult,
    StockQuote,
    KLineResponse,
    KLineData,
    MinuteDataResponse,
    MinuteData,
    ChipDistribution,
    ChipDistributionResponse,
)
from app.utils.cache import cached, CacheTTL
from app.utils.helpers import normalize_stock_code, parse_stock_code


logger = logging.getLogger(__name__)


class StockService:
    """股票数据服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def _get_datasource_manager(self):
        """获取数据源管理器（按 DB 配置初始化）。"""
        from app.datasources.manager import get_datasource_manager

        manager = get_datasource_manager()
        await manager.initialize(self.db)
        return manager

    async def get_stock_info(self, stock_code: str) -> Dict[str, Any]:
        """
        获取股票详细信息 (对应Go的Greet方法)
        """
        stock_code = normalize_stock_code(stock_code)
        # 获取实时行情
        quotes = await self.get_realtime_quotes([stock_code])
        quote = quotes[0] if quotes else None

        # 获取基本信息
        basic_info = await self._get_basic_info(stock_code)

        # 获取资金流向
        money_flow = await self.get_money_flow(stock_code, 1)

        return {
            "quote": quote.model_dump() if quote else None,
            "basic": basic_info,
            "money_flow": money_flow,
        }

    async def get_stock_detail(self, stock_code: str) -> Dict[str, Any]:
        """获取股票完整详情（并发优化，包含财务、估值、股东、分红数据）"""
        stock_code = normalize_stock_code(stock_code)
        # 并发执行所有数据获取操作
        results = await asyncio.gather(
            self.get_realtime_quotes([stock_code]),
            self._get_basic_info(stock_code),
            self.get_kline(stock_code, "day", 30),
            self.get_money_flow(stock_code, 5),
            self.get_stock_concepts(stock_code),
            self.get_stock_fundamental(stock_code),
            self.get_financial_report(stock_code),
            self.get_rating_summary(stock_code),
            self.get_shareholder_count(stock_code),
            self.get_dividend_history(stock_code),
            return_exceptions=True  # 避免单个失败导致全部失败
        )

        (quotes, basic_info, kline, money_flow, concepts,
         fundamental, financial, rating, shareholders, dividend) = results

        # 处理可能的异常结果
        quote = None
        if not isinstance(quotes, Exception) and quotes:
            quote = quotes[0]

        if isinstance(basic_info, Exception):
            basic_info = None

        if isinstance(kline, Exception):
            kline = None

        if isinstance(money_flow, Exception):
            money_flow = []

        if isinstance(concepts, Exception):
            concepts = []

        if isinstance(fundamental, Exception):
            fundamental = {}

        if isinstance(financial, Exception):
            financial = {}

        if isinstance(rating, Exception):
            rating = {}

        if isinstance(shareholders, Exception):
            shareholders = []

        if isinstance(dividend, Exception):
            dividend = []

        return {
            "quote": quote.model_dump() if quote else None,
            "basic": basic_info,
            "kline": kline.model_dump() if kline else None,
            "money_flow": money_flow,
            "concepts": concepts,
            "fundamental": fundamental,  # PE/PB/ROE等估值指标
            "financial": financial,      # 财务报表数据
            "rating": rating,            # 机构评级汇总
            "shareholders": shareholders, # 股东人数变化
            "dividend": dividend,         # 分红送转历史
        }

    async def _get_basic_info(self, stock_code: str) -> Optional[Dict]:
        """获取股票基本信息"""
        stock_code = normalize_stock_code(stock_code)
        # 从数据库查询
        code = stock_code.replace("sh", "").replace("sz", "").replace("hk", "").replace("us", "")

        result = await self.db.execute(
            select(StockBasic).where(
                or_(
                    StockBasic.symbol == stock_code,
                    StockBasic.ts_code.contains(code),
                )
            )
        )
        stock = result.scalar_one_or_none()

        if stock:
            return {
                "ts_code": stock.ts_code,
                "symbol": stock.symbol,
                "name": stock.name,
                "industry": stock.industry,
                "list_date": stock.list_date,
                "exchange": stock.exchange,
            }

        return None

    async def search_stocks(
        self,
        keyword: str,
        market: Optional[str] = None,
        limit: int = 20
    ) -> List[StockSearchResult]:
        """搜索股票"""
        results = []

        # A股搜索
        if not market or market == "A":
            query = select(StockBasic).where(
                or_(
                    StockBasic.symbol.contains(keyword),
                    StockBasic.name.contains(keyword),
                    StockBasic.ts_code.contains(keyword),
                )
            ).limit(limit)

            result = await self.db.execute(query)
            for stock in result.scalars().all():
                results.append(StockSearchResult(
                    stock_code=stock.symbol,
                    stock_name=stock.name,
                    exchange=stock.exchange,
                    industry=stock.industry,
                ))

        # 港股搜索
        if not market or market == "HK":
            query = select(StockInfoHK).where(
                or_(
                    StockInfoHK.ts_code.contains(keyword),
                    StockInfoHK.name.contains(keyword),
                )
            ).limit(limit)

            result = await self.db.execute(query)
            for stock in result.scalars().all():
                results.append(StockSearchResult(
                    stock_code=f"hk{stock.ts_code.split('.')[0]}",
                    stock_name=stock.name,
                    exchange="HKEX",
                    industry="",
                ))

        # 美股搜索
        if not market or market == "US":
            query = select(StockInfoUS).where(
                or_(
                    StockInfoUS.ts_code.contains(keyword),
                    StockInfoUS.name.contains(keyword),
                )
            ).limit(limit)

            result = await self.db.execute(query)
            for stock in result.scalars().all():
                results.append(StockSearchResult(
                    stock_code=f"us{stock.ts_code}",
                    stock_name=stock.name,
                    exchange=stock.exchange,
                    industry="",
                ))

        return results[:limit]

    @cached(ttl_seconds=CacheTTL.REALTIME_QUOTE, prefix="realtime_quotes")
    async def get_realtime_quotes(self, codes: List[str]) -> List[StockQuote]:
        """获取实时行情"""
        # 统一股票代码格式，避免大小写/前缀差异导致数据源拼接错误
        codes = [normalize_stock_code(c) for c in codes or []]
        codes = [c for c in codes if c]

        manager = await self._get_datasource_manager()

        try:
            return await manager.get_realtime_quotes(codes)
        except Exception:
            # 与旧实现保持一致：取不到数据时返回空列表，避免接口直接 500
            return []

    @cached(ttl_seconds=CacheTTL.KLINE, prefix="kline")
    async def get_kline(
        self,
        stock_code: str,
        period: str = "day",
        count: int = 100,
        adjust: str = "qfq"
    ) -> KLineResponse:
        """获取K线数据"""
        stock_code = normalize_stock_code(stock_code)
        period = (period or "day").strip().lower()
        adjust = (adjust or "qfq").strip().lower()
        manager = await self._get_datasource_manager()

        try:
            return await manager.get_kline(stock_code, period=period, count=count, adjust=adjust)
        except Exception as e:
            # 与旧实现保持一致：接口不直接 500，但需要给出“不可用原因”，避免前端图表静默空白
            reason = str(e) if e else "K线数据源暂不可用"
            if getattr(manager, "all_disabled", False):
                reason = "数据源配置存在但均为禁用：请在「设置 → 数据源」启用至少一个（推荐启用 eastmoney 用于K线）"
            return KLineResponse(stock_code=stock_code, stock_name="", period=period, available=False, reason=reason[:500], data=[])

    @cached(ttl_seconds=CacheTTL.MINUTE_DATA, prefix="minute_data")
    async def get_minute_data(self, stock_code: str) -> MinuteDataResponse:
        """获取分钟数据"""
        stock_code = normalize_stock_code(stock_code)

        manager = await self._get_datasource_manager()

        try:
            return await manager.get_minute_data(stock_code)
        except Exception as e:
            # 与旧实现保持一致：接口不直接 500，但要给出明确的“不可用原因”，避免前端静默空白
            reason = str(e) if e else "分时数据源暂不可用"
            if getattr(manager, "all_disabled", False):
                reason = "数据源配置存在但均为禁用：请在「设置 → 数据源」启用至少一个（推荐启用 eastmoney 用于分时）"
            return MinuteDataResponse(stock_code=stock_code, stock_name="", available=False, reason=reason[:500], data=[])

    @cached(ttl_seconds=CacheTTL.MONEY_FLOW, prefix="stock_money_flow")
    async def get_money_flow(self, stock_code: str, days: int = 10) -> List[Dict]:
        """获取股票资金流向"""
        stock_code = normalize_stock_code(stock_code)
        manager = await self._get_datasource_manager()
        return await manager.get_stock_money_flow(stock_code, days)

    @cached(ttl_seconds=CacheTTL.MONEY_FLOW, prefix="money_trend")
    async def get_money_trend(self, stock_code: str, days: int = 10) -> List[Dict]:
        """获取股票资金流向趋势"""
        stock_code = normalize_stock_code(stock_code)
        manager = await self._get_datasource_manager()
        return await manager.get_money_trend(stock_code, days)

    @cached(ttl_seconds=CacheTTL.CONCEPTS, prefix="stock_concepts")
    async def get_stock_concepts(self, stock_code: str) -> List[Dict]:
        """获取股票所属概念/板块"""
        stock_code = normalize_stock_code(stock_code)
        manager = await self._get_datasource_manager()
        return await manager.get_stock_concepts(stock_code)

    @cached(ttl_seconds=CacheTTL.HOT_STOCKS, prefix="hot_stocks")
    async def get_hot_stocks(self, market: str = "A", limit: int = 20) -> List[Dict]:
        """获取热门股票"""
        manager = await self._get_datasource_manager()
        return await manager.get_hot_stocks(market, limit)

    # ============ 基本面数据 ============

    @cached(ttl_seconds=CacheTTL.MONEY_FLOW, prefix="fundamental")
    async def get_stock_fundamental(self, stock_code: str) -> Dict[str, Any]:
        """获取个股基本面数据 (PE/PB/ROE/市值等)"""
        stock_code = normalize_stock_code(stock_code)
        manager = await self._get_datasource_manager()
        return await manager.get_stock_fundamental(stock_code)

    @cached(ttl_seconds=CacheTTL.KLINE, prefix="financial_report")
    async def get_financial_report(self, stock_code: str) -> Dict[str, Any]:
        """获取财务报表数据 (利润表/资产负债表)"""
        stock_code = normalize_stock_code(stock_code)
        manager = await self._get_datasource_manager()
        return await manager.get_financial_report(stock_code)

    # ============ 股票排行榜 ============

    @cached(ttl_seconds=CacheTTL.HOT_STOCKS, prefix="stock_rank")
    async def get_stock_rank(
        self,
        sort_by: str = "change_percent",
        order: str = "desc",
        limit: int = 50,
        market: str = "all",
    ) -> List[Dict]:
        """获取增强版股票排行榜 (含估值指标)"""
        manager = await self._get_datasource_manager()
        data = await manager.get_stock_rank(sort_by=sort_by, order=order, limit=limit, market=market)

        # 兼容前端：MarketPanel 使用 item.pe / item.pb
        for item in data or []:
            if isinstance(item, dict) and "pe" not in item:
                item["pe"] = item.get("pe_dynamic") or item.get("pe_ttm") or item.get("pe_static")
        return data or []

    # ============ 行业研报 ============

    @cached(ttl_seconds=CacheTTL.NEWS, prefix="industry_reports")
    async def get_industry_research_reports(
        self, name: str = "", code: str = "", limit: int = 20
    ) -> List[Dict]:
        """获取行业研究报告"""
        manager = await self._get_datasource_manager()
        return await manager.get_industry_research_reports(name, code, limit)

    # ============ 持仓收益分析 ============

    async def get_portfolio_analysis(self) -> Dict[str, Any]:
        """
        分析自选股持仓收益
        基于已记录的成本价和持仓量计算收益率、浮盈浮亏
        """
        from app.models.stock import FollowedStock

        # 获取所有有持仓数据的自选股
        result = await self.db.execute(
            select(FollowedStock).where(
                FollowedStock.cost_price.isnot(None),
                FollowedStock.cost_price > 0,
                FollowedStock.volume.isnot(None),
                FollowedStock.volume > 0,
            )
        )
        positions = result.scalars().all()

        if not positions:
            return {
                "total_cost": 0,
                "total_market_value": 0,
                "total_profit": 0,
                "total_profit_percent": 0,
                "position_count": 0,
                "missing_quote_count": 0,
                "positions": [],
            }

        # 获取实时行情
        codes = [normalize_stock_code(p.stock_code) for p in positions]
        codes = [c for c in codes if c]
        quotes = await self.get_realtime_quotes(codes)
        quote_map = {q.stock_code: q for q in quotes}

        position_details = []
        total_cost = 0
        total_market_value = 0
        missing_quote_count = 0

        for pos in positions:
            normalized_code = normalize_stock_code(pos.stock_code)
            quote = quote_map.get(normalized_code)
            cost = pos.cost_price * pos.volume
            total_cost += cost

            if quote:
                current_price = quote.current_price
                market_value = current_price * pos.volume
                profit = market_value - cost
                profit_percent = (profit / cost * 100) if cost > 0 else 0
                total_market_value += market_value
                change_percent = quote.change_percent
            else:
                # 行情缺失时不要把现价当作 0（会把盈亏误判为 -100%），用 None 明确表示“未知”
                missing_quote_count += 1
                current_price = None
                market_value = None
                profit = None
                profit_percent = None
                change_percent = None

            position_details.append({
                "stock_code": normalized_code or pos.stock_code,
                "stock_name": pos.stock_name or (quote.stock_name if quote else ""),
                "cost_price": pos.cost_price,
                "current_price": current_price,
                "volume": pos.volume,
                "cost": round(cost, 2),
                "market_value": round(market_value, 2) if market_value is not None else None,
                "profit": round(profit, 2) if profit is not None else None,
                "profit_percent": round(profit_percent, 2) if profit_percent is not None else None,
                "change_percent": change_percent,
            })

        # 按收益率排序
        position_details.sort(
            key=lambda x: (
                x.get("profit_percent") is not None,
                x.get("profit_percent") if x.get("profit_percent") is not None else float("-inf"),
            ),
            reverse=True,
        )

        # 汇总：若存在缺失行情，则总市值/总盈亏无法完整计算，返回 None 避免误导
        if missing_quote_count > 0:
            total_market_value_out = None
            total_profit_out = None
            total_profit_percent_out = None
        else:
            total_profit = total_market_value - total_cost
            total_profit_percent = (total_profit / total_cost * 100) if total_cost > 0 else 0
            total_market_value_out = round(total_market_value, 2)
            total_profit_out = round(total_profit, 2)
            total_profit_percent_out = round(total_profit_percent, 2)

        return {
            "total_cost": round(total_cost, 2),
            "total_market_value": total_market_value_out,
            "total_profit": total_profit_out,
            "total_profit_percent": total_profit_percent_out,
            "position_count": len(position_details),
            "missing_quote_count": missing_quote_count,
            "positions": position_details,
        }

    # ============ 机构评级汇总 ============

    @cached(ttl_seconds=CacheTTL.NEWS, prefix="rating_summary")
    async def get_rating_summary(self, stock_code: str) -> Dict[str, Any]:
        """获取机构评级汇总(评级分布+一致预期目标价)"""
        stock_code = normalize_stock_code(stock_code)
        manager = await self._get_datasource_manager()
        return await manager.get_stock_rating_summary(stock_code)

    # ============ 历史资金流向明细 ============

    @cached(ttl_seconds=CacheTTL.MONEY_FLOW, prefix="money_flow_history")
    async def get_money_flow_history(self, stock_code: str, days: int = 30) -> List[Dict]:
        """获取个股历史资金流向(每日明细)"""
        stock_code = normalize_stock_code(stock_code)
        manager = await self._get_datasource_manager()
        return await manager.get_stock_money_flow_history(stock_code, days)

    # ============ 股东人数变化 ============

    @cached(ttl_seconds=CacheTTL.KLINE, prefix="shareholder_count")
    async def get_shareholder_count(self, stock_code: str) -> List[Dict]:
        """获取股东人数变化(筹码集中度)"""
        stock_code = normalize_stock_code(stock_code)
        manager = await self._get_datasource_manager()
        return await manager.get_shareholder_count(stock_code)

    # ============ 十大股东 ============

    @cached(ttl_seconds=CacheTTL.KLINE, prefix="top_holders")
    async def get_top_holders(self, stock_code: str, holder_type: str = "float") -> List[Dict]:
        """获取十大股东或十大流通股东"""
        stock_code = normalize_stock_code(stock_code)
        manager = await self._get_datasource_manager()
        return await manager.get_top_holders(stock_code, holder_type)

    # ============ 分红送转历史 ============

    @cached(ttl_seconds=CacheTTL.KLINE, prefix="dividend_history")
    async def get_dividend_history(self, stock_code: str) -> List[Dict]:
        """获取分红送转历史"""
        stock_code = normalize_stock_code(stock_code)
        manager = await self._get_datasource_manager()
        return await manager.get_dividend_history(stock_code)

    # ============ 筹码分布（成本分布/获利比例/集中度）===========

    @cached(ttl_seconds=CacheTTL.KLINE, prefix="chip_distribution")
    async def get_chip_distribution(self, stock_code: str) -> ChipDistributionResponse:
        """
        获取筹码分布（对标 daily_stock_analysis 的 ChipDistribution）

        说明：
        - 通过 akshare.stock_cyq_em 获取（内部基于东财数据计算）
        - ETF/指数/非 A 股一般无数据，返回 available=false
        """
        stock_code = normalize_stock_code(stock_code)
        market, pure_code = parse_stock_code(stock_code)

        # 仅支持 A 股普通股票（非指数/ETF 也可能无数据，由上游返回空决定）
        if market not in {"sh", "sz"} or not pure_code.isdigit():
            return ChipDistributionResponse(
                stock_code=stock_code,
                stock_name="",
                available=False,
                reason="仅支持A股股票代码",
                data=None,
            )

        basic = await self._get_basic_info(stock_code)
        stock_name = (basic or {}).get("name", "") if isinstance(basic, dict) else ""

        from app.datasources.chip_distribution import fetch_chip_distribution_em

        try:
            payload = await fetch_chip_distribution_em(pure_code)
            if not payload:
                return ChipDistributionResponse(
                    stock_code=stock_code,
                    stock_name=stock_name,
                    available=False,
                    reason="无筹码分布数据（可能为ETF/指数/停牌/数据源限制）",
                    data=None,
                )

            return ChipDistributionResponse(
                stock_code=stock_code,
                stock_name=stock_name,
                available=True,
                reason="",
                data=ChipDistribution(**payload),
            )
        except Exception as e:
            return ChipDistributionResponse(
                stock_code=stock_code,
                stock_name=stock_name,
                available=False,
                reason=str(e),
                data=None,
            )
