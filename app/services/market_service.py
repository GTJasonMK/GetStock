# Market Service
"""
市场数据服务
"""

import logging
from typing import Optional
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.market import (
    IndustryRank,
    IndustryRankResponse,
    MoneyFlowItem,
    MoneyFlowResponse,
    LongTigerItem,
    LongTigerResponse,
    EconomicDataResponse,
    SectorStockResponse,
    MarketOverview,
)
from app.utils.cache import cached, CacheTTL

logger = logging.getLogger(__name__)


def _safe_float(val, default: float = 0.0) -> float:
    """安全转换为 float（兼容 pandas NaN/空字符串等）。"""
    try:
        if val is None or val == "":
            return default
        f = float(val)
        # pandas NaN: float("nan") != float("nan")
        if f != f:  # noqa: PLR0124
            return default
        return f
    except Exception:
        return default


def _df_is_empty(df: object) -> bool:
    """判断 DataFrame 是否为空（避免直接依赖 pandas 类型）。"""
    try:
        return df is None or bool(getattr(df, "empty"))  # type: ignore[attr-defined]
    except Exception:
        return df is None


class MarketService:
    """市场数据服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def _get_datasource_manager(self):
        """获取数据源管理器（按 DB 配置初始化）。"""
        from app.datasources.manager import get_datasource_manager

        manager = get_datasource_manager()
        await manager.initialize(self.db)
        return manager

    @cached(ttl_seconds=CacheTTL.INDUSTRY_RANK, prefix="industry_rank")
    async def get_industry_rank(
        self,
        sort_by: str = "change_percent",
        order: str = "desc",
        limit: int = 20
    ) -> IndustryRankResponse:
        """获取行业排名"""
        manager = await self._get_datasource_manager()

        try:
            # push2 在部分网络环境不可用时，可能直接抛错或返回空；空数据也需要兜底
            return await manager.get_industry_rank(sort_by=sort_by, order=order, limit=limit)
        except Exception as e:
            logger.warning(f"获取行业排名失败，尝试使用新浪兜底: {e}")

        # 新浪兜底：MoneyFlow.ssl_bkzj_bk（行业板块）
        sort_map = {
            "change_percent": "avg_changeratio",
            "turnover": "turnover",
        }
        sina_sort = sort_map.get(sort_by, "avg_changeratio")

        try:
            rows = await manager.execute_with_failover(
                "get_board_money_flow_rank",
                category="hangye",
                limit=limit,
                sort=sina_sort,
                order=order,
                sources=["sina"],
            )

            items = []
            for r in rows or []:
                items.append(IndustryRank(
                    bk_code=str(r.get("bk_code", "") or ""),
                    bk_name=str(r.get("name", "") or ""),
                    change_percent=float(r.get("change_percent", 0.0) or 0.0),
                    # 新浪该接口的 turnover 字段口径与“换手率(%)”不一致，避免误导：置 0，由前端显示为 "-"
                    turnover=0.0,
                    leader_stock_code=str(r.get("leader_stock_code", "") or ""),
                    leader_stock_name=str(r.get("leader_stock_name", "") or ""),
                    leader_change_percent=float(r.get("leader_change_percent", 0.0) or 0.0),
                    stock_count=0,
                ))

            return IndustryRankResponse(items=items, update_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        except Exception as e:
            logger.warning(f"获取行业排名失败（新浪兜底也失败），尝试使用 akshare: {e}")

        # AkShare 兜底：stock_board_industry_name_em 或 stock_fund_flow_industry（对标 daily_stock_analysis）
        try:
            from app.datasources.akshare_bridge import get_board_industry_name_em_df, get_fund_flow_industry_df

            df = await get_board_industry_name_em_df()
            if not _df_is_empty(df):
                records = df.to_dict("records")  # type: ignore[call-arg]
                ak_items = [
                    IndustryRank(
                        bk_code=str(r.get("板块代码", "") or ""),
                        bk_name=str(r.get("板块名称", "") or ""),
                        change_percent=_safe_float(r.get("涨跌幅", 0.0)),
                        turnover=_safe_float(r.get("换手率", 0.0)),
                        leader_stock_code="",
                        leader_stock_name=str(r.get("领涨股票", "") or ""),
                        leader_change_percent=_safe_float(r.get("领涨股票-涨跌幅", 0.0)),
                        stock_count=0,
                    )
                    for r in (records or [])
                ]

                key_fn = (lambda x: x.change_percent) if sort_by == "change_percent" else (lambda x: x.turnover)
                ak_items.sort(key=key_fn, reverse=(order != "asc"))
                return IndustryRankResponse(items=ak_items[:limit], update_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

            # 进一步兜底：行业资金流接口也包含涨跌幅（但不含换手率）
            df2 = await get_fund_flow_industry_df(symbol="即时")
            if not _df_is_empty(df2):
                records2 = df2.to_dict("records")  # type: ignore[call-arg]
                ak_items = [
                    IndustryRank(
                        bk_code="",
                        bk_name=str(r.get("行业", "") or ""),
                        change_percent=_safe_float(r.get("行业-涨跌幅", 0.0)),
                        turnover=0.0,
                        leader_stock_code="",
                        leader_stock_name=str(r.get("领涨股", "") or ""),
                        leader_change_percent=_safe_float(r.get("领涨股-涨跌幅", 0.0)),
                        stock_count=int(_safe_float(r.get("公司家数", 0), default=0.0)),
                    )
                    for r in (records2 or [])
                ]
                ak_items.sort(key=(lambda x: x.change_percent), reverse=(order != "asc"))
                return IndustryRankResponse(items=ak_items[:limit], update_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        except Exception as e:
            logger.error(f"获取行业排名失败（akshare 兜底也失败）: {e}")

        return IndustryRankResponse(items=[], update_time="")

    @cached(ttl_seconds=CacheTTL.MONEY_FLOW, prefix="money_flow")
    async def get_money_flow(
        self,
        sort_by: str = "main_net_inflow",
        order: str = "desc",
        limit: int = 20
    ) -> MoneyFlowResponse:
        """获取资金流向"""
        manager = await self._get_datasource_manager()

        def _validate_money_flow(resp: object) -> bool:
            try:
                items = getattr(resp, "items", None)
                return bool(items)
            except Exception:
                return False

        try:
            return await manager.execute_with_failover(
                "get_money_flow",
                sort_by,
                order,
                limit,
                validate=_validate_money_flow,
            )
        except Exception as e:
            logger.warning(f"获取资金流向失败，尝试使用新浪兜底: {e}")

        # 新浪兜底：MoneyFlow.ssl_bkzj_ssggzj
        # 说明：新浪资金接口通常只提供“主力净流入/占比”，缺少超大/大/中/小单拆分；这里用 0 填充避免前端空白。
        sort_map = {
            "main_net_inflow": "r0_net",
            "current_price": "trade",
            "change_percent": "changeratio",
        }
        sina_sort = sort_map.get(sort_by, "r0_net")

        try:
            rows = await manager.execute_with_failover(
                "get_stock_money_rank",
                limit=limit,
                sort=sina_sort,
                order=order,
                sources=["sina"],
            )

            items = []
            for r in rows or []:
                if not isinstance(r, dict):
                    continue
                items.append(MoneyFlowItem(
                    stock_code=str(r.get("stock_code", "") or ""),
                    stock_name=str(r.get("stock_name", "") or ""),
                    current_price=_safe_float(r.get("current_price", 0.0)),
                    change_percent=_safe_float(r.get("change_percent", 0.0)),
                    main_net_inflow=_safe_float(r.get("main_net_inflow", 0.0)),
                    main_net_inflow_percent=_safe_float(r.get("main_net_inflow_percent", 0.0)),
                    super_large_net_inflow=0.0,
                    large_net_inflow=0.0,
                    medium_net_inflow=0.0,
                    small_net_inflow=0.0,
                ))

            return MoneyFlowResponse(items=items, update_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        except Exception as e:
            logger.error(f"获取资金流向失败（新浪兜底也失败）: {e}")
            return MoneyFlowResponse(items=[], update_time="")

    @cached(ttl_seconds=CacheTTL.INDUSTRY_RANK, prefix="long_tiger")
    async def get_long_tiger(self, trade_date: Optional[str] = None) -> LongTigerResponse:
        """获取龙虎榜"""
        manager = await self._get_datasource_manager()

        # 指定日期：严格按用户输入查询（不做回溯）
        if trade_date:
            try:
                return await manager.get_long_tiger(trade_date)
            except Exception as e:
                logger.warning(f"获取龙虎榜失败（东财），尝试使用 akshare: {e}")

            # AkShare 兜底：stock_lhb_detail_em(start=end=YYYYMMDD)
            try:
                from app.datasources.akshare_bridge import get_long_tiger_detail_em_df

                date_no_dash = trade_date.replace("-", "")
                df = await get_long_tiger_detail_em_df(date_no_dash, date_no_dash)
                if not _df_is_empty(df):
                    records = df.to_dict("records")  # type: ignore[call-arg]
                    items = []
                    for r in records or []:
                        items.append(LongTigerItem(
                            trade_date=trade_date,
                            stock_code=str(r.get("代码", "") or ""),
                            stock_name=str(r.get("名称", "") or ""),
                            close_price=_safe_float(r.get("收盘价", 0.0)),
                            change_percent=_safe_float(r.get("涨跌幅", 0.0)),
                            net_buy_amount=_safe_float(r.get("龙虎榜净买额", 0.0)) / 10000.0,
                            buy_amount=_safe_float(r.get("龙虎榜买入额", 0.0)) / 10000.0,
                            sell_amount=_safe_float(r.get("龙虎榜卖出额", 0.0)) / 10000.0,
                            reason=str(r.get("上榜原因", "") or ""),
                        ))
                    return LongTigerResponse(items=items, trade_date=trade_date)
            except Exception as e:
                logger.error(f"获取龙虎榜失败（akshare 兜底也失败）: {e}")

            return LongTigerResponse(items=[], trade_date=trade_date)

        # 未指定日期：自动回溯最近“有数据”的交易日
        # 典型场景：
        # - 非交易日/节假日：当天一定无数据
        # - 交易日盘中/刚收盘：当天数据可能尚未发布（需要回退到上一交易日）
        from app.utils.helpers import get_market_timezone, is_trading_day

        tz = get_market_timezone()
        base_day = datetime.now(tz).date()
        max_lookback_days = 15
        last_checked: Optional[str] = None

        try:
            for offset in range(max_lookback_days):
                day = base_day - timedelta(days=offset)
                if not is_trading_day(day, tz=tz):
                    continue

                date_str = day.strftime("%Y-%m-%d")
                last_checked = date_str

                resp = None
                try:
                    resp = await manager.get_long_tiger(date_str)
                except Exception as e:
                    logger.warning(f"获取龙虎榜失败（{date_str}），将尝试兜底并继续回溯: {e}")

                if resp and resp.items:
                    return resp

                # AkShare 兜底：该日若东财返回空/失败，则尝试 AkShare（通常更稳定）
                try:
                    from app.datasources.akshare_bridge import get_long_tiger_detail_em_df

                    date_no_dash = date_str.replace("-", "")
                    df = await get_long_tiger_detail_em_df(date_no_dash, date_no_dash)
                    if not _df_is_empty(df):
                        records = df.to_dict("records")  # type: ignore[call-arg]
                        items = []
                        for r in records or []:
                            items.append(LongTigerItem(
                                trade_date=date_str,
                                stock_code=str(r.get("代码", "") or ""),
                                stock_name=str(r.get("名称", "") or ""),
                                close_price=_safe_float(r.get("收盘价", 0.0)),
                                change_percent=_safe_float(r.get("涨跌幅", 0.0)),
                                net_buy_amount=_safe_float(r.get("龙虎榜净买额", 0.0)) / 10000.0,
                                buy_amount=_safe_float(r.get("龙虎榜买入额", 0.0)) / 10000.0,
                                sell_amount=_safe_float(r.get("龙虎榜卖出额", 0.0)) / 10000.0,
                                reason=str(r.get("上榜原因", "") or ""),
                            ))
                        if items:
                            return LongTigerResponse(items=items, trade_date=date_str)
                except Exception as e:
                    logger.debug(f"AkShare 龙虎榜兜底失败（{date_str}）: {e}")

            # 回溯范围内仍无数据：返回最后一次尝试的日期（便于前端提示）
            return LongTigerResponse(items=[], trade_date=last_checked or base_day.strftime("%Y-%m-%d"))
        except Exception as e:
            logger.error(f"获取龙虎榜失败: {e}")
            return LongTigerResponse(items=[], trade_date=last_checked or base_day.strftime("%Y-%m-%d"))

    @cached(ttl_seconds=300, prefix="economic_data")
    async def get_economic_data(
        self,
        indicator: str,
        count: int = 20
    ) -> EconomicDataResponse:
        """获取宏观经济数据"""
        manager = await self._get_datasource_manager()

        try:
            return await manager.get_economic_data(indicator, count)
        except Exception as e:
            logger.error(f"获取宏观经济数据失败: {e}")
            return EconomicDataResponse(indicator=indicator, items=[])

    @cached(ttl_seconds=300, prefix="sector_stocks")
    async def get_sector_stocks(
        self,
        bk_code: str,
        limit: int = 50
    ) -> SectorStockResponse:
        """获取板块成分股"""
        manager = await self._get_datasource_manager()

        try:
            return await manager.get_sector_stocks(bk_code, limit)
        except Exception as e:
            logger.error(f"获取板块成分股失败: {e}")
            return SectorStockResponse(bk_code=bk_code, bk_name="", stocks=[])

    # ============ 概念板块排名 ============

    @cached(ttl_seconds=CacheTTL.CONCEPT_RANK, prefix="concept_rank")
    async def get_concept_rank(
        self,
        sort_by: str = "change_percent",
        order: str = "desc",
        limit: int = 20
    ):
        """获取概念板块排名"""
        manager = await self._get_datasource_manager()

        try:
            resp = await manager.get_concept_rank(sort_by, order, limit)
            if resp and getattr(resp, "items", None):
                if resp.items:
                    return resp
        except Exception as e:
            logger.warning(f"获取概念板块排名失败，尝试使用新浪兜底: {e}")

        try:
            rows = await manager.get_board_money_flow_rank(
                category="gainian",
                order=order,
                limit=limit,
                sort_by=sort_by,
                sources=["sina"],
            )

            items = []
            for r in rows or []:
                items.append(IndustryRank(
                    bk_code=str(r.get("bk_code", "") or ""),
                    bk_name=str(r.get("name", "") or ""),
                    change_percent=float(r.get("change_percent", 0.0) or 0.0),
                    # 口径不一致，置 0 由前端显示为 "-"
                    turnover=0.0,
                    leader_stock_code=str(r.get("leader_stock_code", "") or ""),
                    leader_stock_name=str(r.get("leader_stock_name", "") or ""),
                    leader_change_percent=float(r.get("leader_change_percent", 0.0) or 0.0),
                    stock_count=0,
                ))

            return IndustryRankResponse(items=items, update_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        except Exception as e:
            logger.warning(f"获取概念板块排名失败（新浪兜底也失败），尝试使用 akshare: {e}")

        # AkShare 兜底：使用概念资金流接口（包含涨跌幅与领涨股）
        try:
            from app.datasources.akshare_bridge import get_fund_flow_concept_df

            df = await get_fund_flow_concept_df(symbol="即时")
            if not _df_is_empty(df):
                records = df.to_dict("records")  # type: ignore[call-arg]
                ak_items = [
                    IndustryRank(
                        bk_code="",
                        bk_name=str(r.get("行业", "") or ""),
                        change_percent=_safe_float(r.get("行业-涨跌幅", 0.0)),
                        turnover=0.0,
                        leader_stock_code="",
                        leader_stock_name=str(r.get("领涨股", "") or ""),
                        leader_change_percent=_safe_float(r.get("领涨股-涨跌幅", 0.0)),
                        stock_count=int(_safe_float(r.get("公司家数", 0), default=0.0)),
                    )
                    for r in (records or [])
                ]
                ak_items.sort(key=(lambda x: x.change_percent), reverse=(order != "asc"))
                return IndustryRankResponse(items=ak_items[:limit], update_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        except Exception as e:
            logger.error(f"获取概念板块排名失败（akshare 兜底也失败）: {e}")

        return IndustryRankResponse(items=[], update_time="")

    # ============ 行业资金流入排名 ============

    @cached(ttl_seconds=CacheTTL.MONEY_FLOW, prefix="industry_money_flow")
    async def get_industry_money_flow(self, category: str, sort_by: str):
        """获取行业/概念资金流向排名"""
        manager = await self._get_datasource_manager()
        normalized_sort_by = "main_net_inflow" if sort_by in ("main_inflow", "main_net_inflow") else sort_by

        try:
            rows = await manager.get_board_money_flow_rank(
                category=category,
                sort_by=normalized_sort_by,
                order="desc",
                limit=50,
            )
            # 对齐前端表格字段
            return [
                {
                    "bk_code": r.get("bk_code", ""),
                    "name": r.get("name", ""),
                    "change_percent": r.get("change_percent", 0.0),
                    "main_net_inflow": r.get("main_net_inflow", 0.0),
                    "main_net_inflow_percent": r.get("main_net_inflow_percent", 0.0),
                }
                for r in (rows or [])
            ]
        except Exception as e:
            logger.warning(f"获取行业资金流向失败，尝试使用 akshare: {e}")

        # AkShare 兜底：行业/概念资金流（返回口径为“亿”，这里统一转为“元”）
        try:
            from app.datasources.akshare_bridge import get_fund_flow_industry_df, get_fund_flow_concept_df

            df = await (get_fund_flow_industry_df(symbol="即时") if category in ("hangye", "industry") else get_fund_flow_concept_df(symbol="即时"))
            if _df_is_empty(df):
                return []

            records = df.to_dict("records")  # type: ignore[call-arg]
            result = []
            for r in records or []:
                inflow = _safe_float(r.get("流入资金", 0.0))
                outflow = _safe_float(r.get("流出资金", 0.0))
                net_yi = _safe_float(r.get("净额", 0.0))
                denom = abs(inflow) + abs(outflow)
                percent = (net_yi / denom * 100.0) if denom > 0 else 0.0
                result.append({
                    "bk_code": "",
                    "name": r.get("行业", ""),
                    "change_percent": _safe_float(r.get("行业-涨跌幅", 0.0)),
                    "main_net_inflow": net_yi * 1e8,
                    "main_net_inflow_percent": percent,
                })

            # 资金接口默认按净额降序
            result.sort(key=lambda x: _safe_float(x.get("main_net_inflow", 0.0)), reverse=True)
            return result[:50]
        except Exception as e:
            logger.error(f"获取行业资金流向失败（akshare 兜底也失败）: {e}")
            return []

    # ============ 股票资金流入排名 ============

    @cached(ttl_seconds=CacheTTL.MONEY_FLOW, prefix="stock_money_rank")
    async def get_stock_money_rank(self, sort_by: str, limit: int):
        """获取股票资金流入排名"""
        manager = await self._get_datasource_manager()
        try:
            return await manager.get_stock_money_rank(sort_by=sort_by, order="desc", limit=limit)
        except Exception as e:
            logger.error(f"获取股票资金排名失败: {e}")
            return []

    # ============ 量比排名 ============

    async def get_volume_ratio_rank(self, min_ratio: float, limit: int):
        """获取量比排名"""
        manager = await self._get_datasource_manager()

        try:
            return await manager.get_volume_ratio_rank(min_ratio=min_ratio, limit=limit)
        except Exception as e:
            logger.error(f"获取量比排名失败: {e}")
            return []

    # ============ 涨跌停统计 ============

    @cached(ttl_seconds=CacheTTL.LIMIT_STATS, prefix="limit_stats")
    async def get_limit_stats(self):
        """获取涨跌停统计"""
        manager = await self._get_datasource_manager()

        try:
            limit_up = await manager.get_limit_up_stocks()
            limit_down = await manager.get_limit_down_stocks()

            return {
                "limit_up_count": len(limit_up),
                "limit_down_count": len(limit_down),
                "limit_up_stocks": limit_up,
                "limit_down_stocks": limit_down,
            }
        except Exception as e:
            logger.error(f"获取涨跌停统计失败: {e}")
            return {
                "limit_up_count": 0,
                "limit_down_count": 0,
                "limit_up_stocks": [],
                "limit_down_stocks": [],
            }

    # ============ 北向资金 ============

    @cached(ttl_seconds=CacheTTL.NORTH_FLOW, prefix="north_flow")
    async def get_north_flow(self, days: int):
        """获取北向资金数据"""
        manager = await self._get_datasource_manager()

        try:
            return await manager.get_north_flow(days)
        except Exception as e:
            logger.warning(f"获取北向资金数据失败（东财），尝试使用 akshare: {e}")

        # AkShare 兜底：stock_hsgt_hist_em（沪股通/深股通）
        try:
            from app.datasources.akshare_bridge import get_hsgt_hist_em_df

            df_sh = await get_hsgt_hist_em_df(symbol="沪股通")
            df_sz = await get_hsgt_hist_em_df(symbol="深股通")
            if _df_is_empty(df_sh) or _df_is_empty(df_sz):
                return {"current": None, "history": []}

            sh_map = {}
            for r in (df_sh.to_dict("records") or []):  # type: ignore[call-arg]
                date = str(r.get("日期", "") or "")
                if not date:
                    continue
                sh_map[date] = {
                    "inflow": _safe_float(r.get("当日成交净买额", r.get("当日资金流入", 0.0))) * 1e8,
                    "balance": _safe_float(r.get("当日余额", 0.0)) * 1e8,
                }

            sz_map = {}
            for r in (df_sz.to_dict("records") or []):  # type: ignore[call-arg]
                date = str(r.get("日期", "") or "")
                if not date:
                    continue
                sz_map[date] = {
                    "inflow": _safe_float(r.get("当日成交净买额", r.get("当日资金流入", 0.0))) * 1e8,
                    "balance": _safe_float(r.get("当日余额", 0.0)) * 1e8,
                }

            all_dates = sorted(set(sh_map.keys()) | set(sz_map.keys()))
            # 取最近 days 个交易日
            tail_dates = all_dates[-max(1, int(days)) :]

            history = []
            for d in reversed(tail_dates):
                sh = sh_map.get(d) or {"inflow": 0.0, "balance": 0.0}
                sz = sz_map.get(d) or {"inflow": 0.0, "balance": 0.0}
                sh_in = float(sh.get("inflow", 0.0) or 0.0)
                sz_in = float(sz.get("inflow", 0.0) or 0.0)
                history.append({
                    "date": d,
                    "sh_inflow": sh_in,
                    "sz_inflow": sz_in,
                    "total_inflow": sh_in + sz_in,
                    "sh_balance": float(sh.get("balance", 0.0) or 0.0),
                    "sz_balance": float(sz.get("balance", 0.0) or 0.0),
                })

            current = history[0] if history else None
            return {
                "metric": "成交净买额",
                "unit": "元",
                "source": "akshare",
                "asof_date": (current or {}).get("date", "") if isinstance(current, dict) else "",
                "current": current,
                "history": history,
            }
        except Exception as e:
            logger.error(f"获取北向资金数据失败（akshare 兜底也失败）: {e}")
            return {"current": None, "history": []}

    # ============ 板块字典 ============

    async def get_bk_dict(self, bk_type: str):
        """获取板块字典"""
        manager = await self._get_datasource_manager()

        try:
            return await manager.get_bk_dict(bk_type)
        except Exception as e:
            logger.error(f"获取板块字典失败: {e}")
            return {"items": []}

    # ============ 股票研究报告 ============

    async def get_stock_research_reports(self, stock_code: str, limit: int):
        """获取股票研究报告"""
        manager = await self._get_datasource_manager()

        try:
            return await manager.get_stock_research_reports(stock_code, limit)
        except Exception as e:
            logger.error(f"获取股票研究报告失败: {e}")
            return []

    # ============ 股票公告 ============

    async def get_stock_notices(self, stock_code: str, limit: int):
        """获取股票公告"""
        manager = await self._get_datasource_manager()

        try:
            return await manager.get_stock_notices(stock_code, limit)
        except Exception as e:
            logger.error(f"获取股票公告失败: {e}")
            return []

    # ============ 市场概览（大盘复盘口径）===========

    @cached(ttl_seconds=60, prefix="market_overview")
    async def get_market_overview(self) -> MarketOverview:
        """
        获取市场概览（对齐 daily_stock_analysis 的复盘口径）

        包含：
        - 主要指数行情（上证/深成指/创业板等）
        - 上涨/下跌/平盘家数
        - 涨停/跌停家数
        - 两市成交额（亿元）
        - 板块涨跌榜（行业前5/后5）
        - （可选）北向资金净流入（亿元）
        """
        from app.utils.helpers import get_market_timezone

        today = datetime.now(get_market_timezone()).strftime("%Y-%m-%d")
        overview = MarketOverview(date=today)
        reasons: list[str] = []
        manager = await self._get_datasource_manager()

        # 1) 指数行情（使用新浪指数报价，字段更完整）
        try:
            overview.indices = await manager.get_market_indices([
                "sh000001",  # 上证指数
                "sz399001",  # 深证成指
                "sz399006",  # 创业板指
                "sh000688",  # 科创50
                "sh000016",  # 上证50
                "sh000300",  # 沪深300
            ])
        except Exception as e:
            logger.error(f"获取大盘指数失败: {e}")
            overview.indices = []
            reasons.append(f"指数行情获取失败: {e}")

        # 2) 市场统计（上涨/下跌/平盘、成交额、涨跌停家数）
        try:
            try:
                stats = await manager.get_a_spot_statistics()
            except Exception as e:
                logger.warning(f"获取A股快照失败，尝试使用 akshare: {e}")
                from app.datasources.akshare_bridge import get_a_spot_em_df

                df = await get_a_spot_em_df()
                if _df_is_empty(df):
                    raise RuntimeError("akshare A股快照返回为空") from e

                try:
                    import pandas as pd  # type: ignore
                except Exception as e3:  # pragma: no cover
                    raise RuntimeError("缺少 pandas，无法计算 akshare A股快照统计") from e3

                change_col = "涨跌幅"
                amount_col = "成交额"
                df2 = df.copy()
                if change_col in getattr(df2, "columns", []):
                    df2[change_col] = pd.to_numeric(df2[change_col], errors="coerce")
                if amount_col in getattr(df2, "columns", []):
                    df2[amount_col] = pd.to_numeric(df2[amount_col], errors="coerce")

                up_count = int((df2[change_col] > 0).sum()) if change_col in df2.columns else 0
                down_count = int((df2[change_col] < 0).sum()) if change_col in df2.columns else 0
                flat_count = int((df2[change_col] == 0).sum()) if change_col in df2.columns else 0
                limit_up_count = int((df2[change_col] >= 9.9).sum()) if change_col in df2.columns else 0
                limit_down_count = int((df2[change_col] <= -9.9).sum()) if change_col in df2.columns else 0
                total_amount_yi = float(df2[amount_col].sum() / 1e8) if amount_col in df2.columns else 0.0

                stats = {
                    "up_count": up_count,
                    "down_count": down_count,
                    "flat_count": flat_count,
                    "limit_up_count": limit_up_count,
                    "limit_down_count": limit_down_count,
                    "total_amount_yi": round(total_amount_yi, 2),
                }

            overview.up_count = int(stats.get("up_count", 0) or 0)
            overview.down_count = int(stats.get("down_count", 0) or 0)
            overview.flat_count = int(stats.get("flat_count", 0) or 0)
            overview.limit_up_count = int(stats.get("limit_up_count", 0) or 0)
            overview.limit_down_count = int(stats.get("limit_down_count", 0) or 0)
            overview.total_amount = float(stats.get("total_amount_yi", 0.0) or 0.0)

            # 3) 板块涨跌榜：使用行业涨幅榜（前5/后5）
            try:
                # 复用 service 层的 failover（东财 → 新浪 → AkShare）
                top = await self.get_industry_rank(sort_by="change_percent", order="desc", limit=5)
                bottom = await self.get_industry_rank(sort_by="change_percent", order="asc", limit=5)
                overview.top_sectors = [
                    {"code": i.bk_code, "name": i.bk_name, "change_pct": i.change_percent}
                    for i in (top.items or [])
                ]
                overview.bottom_sectors = [
                    {"code": i.bk_code, "name": i.bk_name, "change_pct": i.change_percent}
                    for i in (bottom.items or [])
                ]
            except Exception as e:
                logger.warning(f"获取板块涨跌榜失败: {e}")

            # 4) 北向资金（可选）
            try:
                # 复用 service 层的 failover（东财 → AkShare）
                north = await self.get_north_flow(days=1)
                current = (north or {}).get("current")
                if current and isinstance(current, dict):
                    # 若上游字段缺失（0 值）则保持 None，避免误导
                    total_inflow = current.get("total_inflow")
                    if total_inflow not in (None, 0, 0.0):
                        # north-flow 接口返回“元”，MarketOverview 口径为“亿元”
                        overview.north_flow = round(float(total_inflow) / 1e8, 4)
            except Exception as e:
                logger.debug(f"获取北向资金失败（可忽略）: {e}")

        except Exception as e:
            logger.error(f"获取市场统计失败: {e}")
            reasons.append(f"市场统计获取失败: {e}")

        if reasons:
            overview.available = False
            overview.reason = "; ".join(reasons)[:500]

        return overview

    # ============ 投资者问答 ============

    async def get_interactive_qa(self, keyword: str, page: int, page_size: int):
        """获取投资者问答"""
        manager = await self._get_datasource_manager()

        try:
            return await manager.get_interactive_qa(keyword, page, page_size)
        except Exception as e:
            logger.error(f"获取投资者问答失败: {e}")
            return {"items": [], "total": 0, "page": page, "page_size": page_size}
