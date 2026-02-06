# Search Service
"""
选股引擎服务 - 自然语言选股
"""

import re
from typing import List, Dict, Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession


class SearchService:
    """选股引擎服务"""

    # 选股条件关键词映射
    CONDITION_KEYWORDS = {
        # 涨跌相关
        "涨停": {"type": "limit_up"},
        "跌停": {"type": "limit_down"},
        "涨幅超过": {"type": "change_percent_gt"},
        "跌幅超过": {"type": "change_percent_lt"},

        # 资金相关
        "主力资金流入": {"type": "main_money_in"},
        "主力资金流出": {"type": "main_money_out"},
        "资金净流入": {"type": "net_money_in"},
        "大单买入": {"type": "big_order_buy"},

        # 技术指标
        "MACD金叉": {"type": "macd_golden"},
        "MACD死叉": {"type": "macd_death"},
        "KDJ金叉": {"type": "kdj_golden"},
        "RSI超买": {"type": "rsi_overbought"},
        "RSI超卖": {"type": "rsi_oversold"},
        "突破均线": {"type": "break_ma"},
        "站上5日均线": {"type": "above_ma5"},
        "站上10日均线": {"type": "above_ma10"},
        "站上20日均线": {"type": "above_ma20"},

        # 量价关系
        "放量上涨": {"type": "volume_up_price_up"},
        "缩量下跌": {"type": "volume_down_price_down"},
        "量比大于": {"type": "volume_ratio_gt"},

        # 龙虎榜
        "龙虎榜": {"type": "long_tiger"},
        "机构买入": {"type": "institution_buy"},

        # 基本面
        "市盈率低于": {"type": "pe_lt"},
        "市净率低于": {"type": "pb_lt"},
        "净利润增长": {"type": "profit_growth"},

        # 板块
        "创业板": {"type": "market", "value": "cyb"},
        "科创板": {"type": "market", "value": "kcb"},
        "主板": {"type": "market", "value": "main"},
        "北交所": {"type": "market", "value": "bj"},
    }

    def __init__(self, db: AsyncSession):
        self.db = db

    async def _get_datasource_manager(self):
        """获取数据源管理器（按 DB 配置初始化）。"""
        from app.datasources.manager import get_datasource_manager

        manager = get_datasource_manager()
        await manager.initialize(self.db)
        return manager

    async def search_by_words(self, words: str) -> Dict[str, Any]:
        """
        自然语言选股
        支持条件组合，如: "涨停股 主力资金流入 创业板除外"
        """
        # 解析条件
        conditions = self._parse_conditions(words)

        # 根据条件获取数据
        results = await self._fetch_stocks_by_conditions(conditions)

        return {
            "words": words,
            "conditions": conditions,
            "results": results,
            "total": len(results),
        }

    def _parse_conditions(self, words: str) -> List[Dict]:
        """解析自然语言条件"""
        conditions = []

        for keyword, config in self.CONDITION_KEYWORDS.items():
            if keyword in words:
                condition = {"keyword": keyword, **config}

                # 提取数值参数
                if "超过" in keyword or "大于" in keyword or "低于" in keyword:
                    # 尝试提取数字
                    pattern = rf"{keyword}(\d+(?:\.\d+)?)"
                    match = re.search(pattern, words)
                    if match:
                        condition["value"] = float(match.group(1))

                # 检查是否排除
                if f"{keyword}除外" in words or f"排除{keyword}" in words:
                    condition["exclude"] = True

                conditions.append(condition)

        return conditions

    async def _fetch_stocks_by_conditions(self, conditions: List[Dict]) -> List[Dict]:
        """根据条件获取股票"""
        manager = await self._get_datasource_manager()

        # 默认获取涨幅排名
        if not conditions:
            return await manager.get_stock_rank(sort_by="change_percent", order="desc", limit=50)

        # 分离主条件和过滤条件
        primary_condition = conditions[0]
        condition_type = primary_condition.get("type")
        filter_conditions = conditions[1:]  # noqa: F841

        # 收集市场过滤和排除条件
        market_filters = []
        excludes = []
        for c in conditions:
            if c.get("type") == "market":
                if c.get("exclude"):
                    excludes.append(c.get("value"))
                else:
                    market_filters.append(c.get("value"))

        results: list[dict] = []

        if condition_type == "limit_up":
            results = await manager.get_limit_up_stocks()
        elif condition_type == "limit_down":
            results = await manager.get_limit_down_stocks()
        elif condition_type in ["main_money_in", "net_money_in"]:
            results = await manager.get_money_flow_rank("main_net_inflow", "desc", 50)
        elif condition_type == "main_money_out":
            results = await manager.get_money_flow_rank("main_net_inflow", "asc", 50)
        elif condition_type == "big_order_buy":
            results = await manager.get_money_flow_rank("big_net_inflow", "desc", 50)
        elif condition_type == "long_tiger":
            result = await manager.get_long_tiger(None)
            results = [item.model_dump() for item in result.items]
        elif condition_type == "volume_ratio_gt":
            value = primary_condition.get("value", 2)
            results = await manager.get_volume_ratio_rank(min_ratio=value, limit=50)
        elif condition_type == "change_percent_gt":
            # 获取涨幅排名，然后按阈值过滤
            value = primary_condition.get("value", 5)
            all_stocks = await manager.get_stock_rank(sort_by="change_percent", order="desc", limit=200)
            results = [s for s in all_stocks if s.get("change_percent", 0) > value]
        elif condition_type == "change_percent_lt":
            # 获取跌幅排名，然后按阈值过滤
            value = primary_condition.get("value", 5)
            all_stocks = await manager.get_stock_rank(sort_by="change_percent", order="asc", limit=200)
            results = [s for s in all_stocks if s.get("change_percent", 0) < -value]
        elif condition_type == "pe_lt":
            # 获取股票列表并按市盈率过滤
            value = primary_condition.get("value", 20)
            all_stocks = await manager.get_stock_rank(sort_by="pe", order="asc", limit=200)
            results = [s for s in all_stocks if 0 < (s.get("pe") or 0) < value]
        elif condition_type == "pb_lt":
            # 获取股票列表并按市净率过滤
            value = primary_condition.get("value", 2)
            all_stocks = await manager.get_stock_rank(sort_by="pb", order="asc", limit=200)
            results = [s for s in all_stocks if 0 < (s.get("pb") or 0) < value]
        elif condition_type == "volume_up_price_up":
            # 放量上涨: 获取涨幅排名，按量比过滤
            all_stocks = await manager.get_stock_rank(sort_by="change_percent", order="desc", limit=200)
            results = [s for s in all_stocks if s.get("change_percent", 0) > 0 and s.get("volume_ratio", 0) > 1.5]
        elif condition_type == "volume_down_price_down":
            # 缩量下跌: 获取跌幅排名，按低量比过滤
            all_stocks = await manager.get_stock_rank(sort_by="change_percent", order="asc", limit=200)
            results = [s for s in all_stocks if s.get("change_percent", 0) < 0 and s.get("volume_ratio", 0) < 0.8]
        elif condition_type == "institution_buy":
            # 机构买入: 从龙虎榜获取机构相关数据
            result = await manager.get_long_tiger(None)
            results = [item.model_dump() for item in result.items if "机构" in (item.reason or "")]
        elif condition_type == "market":
            # 按板块筛选
            market_value = primary_condition.get("value", "main")
            results = await manager.get_stock_rank(sort_by="change_percent", order="desc", limit=50, market=market_value)
        else:
            # 未实现的条件，使用默认排名
            results = await manager.get_stock_rank(sort_by="change_percent", order="desc", limit=50)

        # 应用市场过滤
        if market_filters:
            results = self._filter_by_market(results, market_filters)

        # 应用排除条件
        if excludes:
            results = self._exclude_by_market(results, excludes)

        return results[:50]

    @staticmethod
    def _get_market_node(market: str) -> str:
        """获取市场节点标识"""
        market_nodes = {
            "cyb": "m:0+t:80",     # 创业板
            "kcb": "m:1+t:23",     # 科创板
            "main": "m:0+t:6,m:0+t:13,m:0+t:80,m:1+t:2,m:1+t:23",  # 主板
            "bj": "m:0+t:81",      # 北交所
        }
        return market_nodes.get(market, "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23")

    @staticmethod
    def _filter_by_market(stocks: List[Dict], markets: List[str]) -> List[Dict]:
        """按市场过滤股票"""
        filtered = []
        seen_codes = set()  # 用于去重

        for stock in stocks:
            code = stock.get("stock_code", "")
            if code in seen_codes:
                continue

            for market in markets:
                matched = False
                if market == "cyb" and code.startswith("3"):
                    matched = True
                elif market == "kcb" and code.startswith("68"):
                    matched = True
                # 主板：6开头但排除68（科创板），或者0开头但排除3（创业板）
                elif market == "main" and (
                    (code.startswith("6") and not code.startswith("68")) or
                    (code.startswith("0") and not code.startswith("3"))
                ):
                    matched = True
                elif market == "bj" and (code.startswith("4") or code.startswith("8")):
                    matched = True

                if matched:
                    filtered.append(stock)
                    seen_codes.add(code)
                    break  # 一只股票只添加一次

        return filtered

    @staticmethod
    def _exclude_by_market(stocks: List[Dict], excludes: List[str]) -> List[Dict]:
        """排除指定市场的股票"""
        filtered = []
        for stock in stocks:
            code = stock.get("stock_code", "")
            excluded = False
            for market in excludes:
                if market == "cyb" and code.startswith("3"):
                    excluded = True
                elif market == "kcb" and code.startswith("68"):
                    excluded = True
                # 主板排除：6开头但不是68，或者0开头但不是3
                elif market == "main" and (
                    (code.startswith("6") and not code.startswith("68")) or
                    (code.startswith("0") and not code.startswith("3"))
                ):
                    excluded = True
                elif market == "bj" and (code.startswith("4") or code.startswith("8")):
                    excluded = True

                if excluded:
                    break

            if not excluded:
                filtered.append(stock)
        return filtered

    async def get_hot_strategies(self) -> List[Dict]:
        """获取热门选股策略"""
        manager = await self._get_datasource_manager()

        return await manager.get_hot_strategies()

    async def search_sector(self, words: str) -> Dict[str, Any]:
        """搜索板块/概念"""
        manager = await self._get_datasource_manager()

        # 判断搜索类型
        if "概念" in words:
            results = await manager.search_concept(words.replace("概念", "").strip())
        elif "行业" in words:
            results = await manager.search_industry(words.replace("行业", "").strip())
        else:
            # 同时搜索
            concepts = await manager.search_concept(words)
            industries = await manager.search_industry(words)
            results = concepts + industries

        return {
            "words": words,
            "results": results,
            "total": len(results),
        }
