# Sina 数据源客户端
"""
新浪财经数据接口 - 完整实现
"""

import ast
import json
import logging
import re
import asyncio
import math
from typing import List, Dict, Any
from datetime import datetime

import httpx

logger = logging.getLogger(__name__)

from app.schemas.stock import StockQuote, MinuteDataResponse, MinuteData
from app.schemas.news import NewsItem, GlobalIndex, GlobalIndexResponse, TelegraphItem, TelegraphResponse
from app.schemas.market import MarketIndex
from app.utils.helpers import normalize_stock_code


class SinaClient:
    """新浪财经客户端"""

    BASE_URL = "https://hq.sinajs.cn"
    NEWS_URL = "https://feed.mix.sina.com.cn/api/roll/get"
    LIVE_URL = "https://zhibo.sina.com.cn/api/zhibo/feed"
    MONEY_URL = "https://vip.stock.finance.sina.com.cn"
    # 新浪 7x24 财经快讯对应的 zhibo_id（来自 finance.sina.com.cn/7x24 的前端配置）
    LIVE_ZHIBO_ID_FINANCE = 152
    # 经验值：该接口会忽略 pagesize 参数并固定返回 10 条
    LIVE_PROVIDER_PAGE_SIZE = 10

    def __init__(self):
        self.client = httpx.AsyncClient(
            timeout=30.0,
            headers={
                "Referer": "https://finance.sina.com.cn",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            }
        )

    @staticmethod
    def _to_float(val: Any, default: float = 0.0) -> float:
        """安全转换为 float（新浪接口大量字段为字符串）。"""
        try:
            if val is None or val == "":
                return default
            return float(val)
        except (ValueError, TypeError):
            return default

    @staticmethod
    def _strip_cn_symbol_prefix(symbol: str) -> str:
        """
        将新浪 symbol（如 sh600000/sz000001/bj920046）裁剪为纯数字代码。

        注意：
        - 北交所为 bj 前缀，系统内部可能仍会以带前缀形式使用；这里裁剪主要用于排行榜展示。
        """
        s = (symbol or "").strip()
        if len(s) >= 3 and s[:2].isalpha() and s[2:].isdigit():
            return s[2:]
        return s

    async def _request_quotes_service_json(self, api: str, params: Dict[str, Any]) -> Any:
        """
        请求新浪 quotes_service，并尽量把返回解析为 Python 对象。

        说明：
        - 多数接口返回标准 JSON（list/dict）
        - 少数接口返回 Python 风格字面量（可用 ast.literal_eval 解析）
        """
        url = f"{self.MONEY_URL}/quotes_service/api/json_v2.php/{api}"
        # 经验：quotes_service 在部分环境下会对缺少 `_s_r_a` 的请求返回 456（拒绝访问）。
        # 该参数来自新浪页面的“分页请求”约定：`_s_r_a=page`。
        safe_params = dict(params or {})
        safe_params.setdefault("_s_r_a", "page")

        resp = await self.client.get(url, params=safe_params)
        if resp.status_code == 456:
            # 仍被拒绝时，优先返回可诊断错误，交由上层做 failover（东财/akshare）。
            raise RuntimeError(f"新浪接口拒绝访问(456): {api}")
        resp.raise_for_status()
        # 优先按 JSON 解析
        try:
            return resp.json()
        except Exception:
            text = (resp.text or "").strip()
            if not text:
                return []
            try:
                return json.loads(text)
            except Exception:
                try:
                    return ast.literal_eval(text)
                except Exception as e:
                    raise RuntimeError(f"解析新浪接口失败: {api}") from e

    async def close(self):
        await self.client.aclose()

    # ============ A股快照统计（用于市场概览兜底）===========

    async def _get_hq_node_stock_count(self, node: str = "hs_a") -> int:
        """
        获取市场节点股票数量（用于分页）。

        新浪接口返回示例：`"5476"`（字符串形式的 JSON）。
        """
        url = f"{self.MONEY_URL}/quotes_service/api/json_v2.php/Market_Center.getHQNodeStockCountSimple"
        params = {"node": node}
        resp = await self.client.get(url, params=params)
        try:
            raw = resp.json()
        except Exception:
            raw = (resp.text or "").strip().strip('"')
        try:
            return int(raw)
        except Exception as e:
            raise RuntimeError(f"解析新浪股票数量失败: {raw}") from e

    async def _fetch_hq_node_data_simple_page(
        self,
        page: int,
        num: int = 80,
        node: str = "hs_a",
    ) -> List[Dict[str, Any]]:
        """
        获取 Market_Center.getHQNodeDataSimple 单页数据。

        返回字段示例：
        - symbol: bj920000 / sh600000 / sz000001
        - name: 股票名称
        - changepercent: 涨跌幅（字符串，百分比数值，如 -2.145）
        - amount: 成交额（数值，单位：元）
        """
        url = f"{self.MONEY_URL}/quotes_service/api/json_v2.php/Market_Center.getHQNodeDataSimple"
        params = {
            "page": page,
            "num": num,
            "sort": "symbol",
            "asc": 1,
            "node": node,
            "symbol": "",
            "_s_r_a": "page",
        }

        last_error: Exception | None = None
        for attempt in range(1, 4):
            try:
                resp = await self.client.get(url, params=params)
                data = resp.json()
                if isinstance(data, list):
                    return data
                # 个别情况下会返回空字符串/非 JSON，按空处理
                return []
            except Exception as e:
                last_error = e
                if attempt < 3:
                    await asyncio.sleep(0.2 * attempt)
        raise RuntimeError(f"获取新浪A股快照失败(page={page}): {last_error}") from last_error

    async def get_a_spot_statistics(self) -> Dict[str, Any]:
        """
        获取市场概览统计（涨跌家数/涨跌停家数/两市成交额），用于东财快照失败时兜底。

        说明：
        - 数据来自新浪 Market_Center.getHQNodeDataSimple（分页）。
        - 为避免请求过慢，采用有限并发抓取（默认并发 4）。
        - 输出字段与 `EastMoneyClient.get_a_spot_statistics()` 对齐：
          up_count/down_count/flat_count/limit_up_count/limit_down_count/total_amount_yi
        """
        total = await self._get_hq_node_stock_count(node="hs_a")
        per_page = 80
        total_pages = int(math.ceil(total / per_page)) if total > 0 else 0

        counters: Dict[str, Any] = {
            "total": total,
            "up_count": 0,
            "down_count": 0,
            "flat_count": 0,
            "limit_up_count": 0,
            "limit_down_count": 0,
            "total_amount": 0.0,  # 原始金额（元）
        }

        def _accumulate(items: List[Dict[str, Any]]) -> None:
            for item in items or []:
                try:
                    change_percent = float(item.get("changepercent", 0) or 0)
                except (ValueError, TypeError):
                    change_percent = 0.0

                if change_percent > 0:
                    counters["up_count"] += 1
                elif change_percent < 0:
                    counters["down_count"] += 1
                else:
                    counters["flat_count"] += 1

                if change_percent >= 9.9:
                    counters["limit_up_count"] += 1
                elif change_percent <= -9.9:
                    counters["limit_down_count"] += 1

                try:
                    amount = float(item.get("amount", 0) or 0)
                except (ValueError, TypeError):
                    amount = 0.0
                counters["total_amount"] += amount

        if total_pages <= 0:
            counters["total_amount_yi"] = 0.0
            return counters

        # 先拉第一页，避免 total_pages 很大时“一上来就并发打爆”
        first = await self._fetch_hq_node_data_simple_page(1, num=per_page, node="hs_a")
        _accumulate(first)

        if total_pages == 1:
            counters["total_amount_yi"] = round(counters["total_amount"] / 1e8, 2)
            return counters

        sem = asyncio.Semaphore(4)

        async def _fetch_page(p: int) -> List[Dict[str, Any]]:
            async with sem:
                return await self._fetch_hq_node_data_simple_page(p, num=per_page, node="hs_a")

        pages = await asyncio.gather(*[asyncio.create_task(_fetch_page(p)) for p in range(2, total_pages + 1)])
        for items in pages:
            _accumulate(items)

        counters["total_amount_yi"] = round(counters["total_amount"] / 1e8, 2)
        return counters

    async def get_realtime_quotes(self, codes: List[str]) -> List[StockQuote]:
        """获取实时行情"""
        # 转换股票代码格式
        sina_codes = []
        for code in codes:
            # 统一输入规范，避免大小写/前缀差异导致代码拼接错误
            code = (code or "").strip()
            if not code:
                continue
            if not code.lower().startswith("gb_"):
                code = normalize_stock_code(code)

            if code.startswith("sh") or code.startswith("sz"):
                sina_codes.append(code)
            elif code.startswith("hk"):
                sina_codes.append(f"hk{code[2:]}")
            elif code.startswith("us"):
                sina_codes.append(f"gb_{code[2:]}")
            else:
                # 自动判断交易所
                if code.startswith("6"):
                    sina_codes.append(f"sh{code}")
                else:
                    sina_codes.append(f"sz{code}")

        url = f"{self.BASE_URL}/list={','.join(sina_codes)}"
        response = await self.client.get(url)
        response.encoding = "gbk"
        content = response.text

        quotes = []
        for line in content.strip().split("\n"):
            if not line or "=" not in line:
                continue

            match = re.match(r'var hq_str_(\w+)="(.*)";', line)
            if not match:
                continue

            code = match.group(1)
            data = match.group(2).split(",")

            # 港股格式 (hk开头)
            if code.startswith("hk"):
                if len(data) < 10:
                    continue
                try:
                    # 新浪港股格式: 名称,今开,昨收,最高,最低,现价,涨跌额,涨跌幅%,成交量,成交额...
                    prev_close = float(data[2]) if data[2] else 0
                    current = float(data[5]) if data[5] else 0
                    change_pct = float(data[7]) if data[7] else 0

                    quotes.append(StockQuote(
                        stock_code=normalize_stock_code(code),
                        stock_name=data[0],
                        current_price=current,
                        change_percent=change_pct,
                        change_amount=float(data[6]) if data[6] else 0,
                        open_price=float(data[1]) if data[1] else 0,
                        high_price=float(data[3]) if data[3] else 0,
                        low_price=float(data[4]) if data[4] else 0,
                        prev_close=prev_close,
                        volume=int(float(data[8])) if data[8] else 0,
                        amount=float(data[9]) if data[9] else 0,
                        update_time="",
                    ))
                except (ValueError, IndexError) as e:
                    logger.warning(f"解析港股行情失败: {code}, {e}")
                    continue
                continue

            # 美股格式 (gb_开头)
            if code.startswith("gb_"):
                if len(data) < 10:
                    continue
                try:
                    # 新浪美股格式: 名称,现价,涨跌额,涨跌幅%,今开,最高,最低,52周最高,52周最低,成交量...
                    current = float(data[1]) if data[1] else 0
                    change_pct = float(data[3].replace("%", "")) if data[3] else 0

                    quotes.append(StockQuote(
                        # 新浪美股返回 gb_xxx，统一映射回项目内部规范 usTICKER（ticker 大写）
                        stock_code=normalize_stock_code(code.replace("gb_", "us")),
                        stock_name=data[0],
                        current_price=current,
                        change_percent=change_pct,
                        change_amount=float(data[2]) if data[2] else 0,
                        open_price=float(data[4]) if data[4] else 0,
                        high_price=float(data[5]) if data[5] else 0,
                        low_price=float(data[6]) if data[6] else 0,
                        prev_close=current - float(data[2]) if data[2] else 0,
                        volume=int(float(data[9])) if len(data) > 9 and data[9] else 0,
                        amount=0,
                        update_time="",
                    ))
                except (ValueError, IndexError) as e:
                    logger.warning(f"解析美股行情失败: {code}, {e}")
                    continue
                continue

            # A股格式
            if len(data) < 32:
                continue

            if code.startswith("sh") or code.startswith("sz"):
                try:
                    prev_close = float(data[2]) if data[2] else 0
                    current = float(data[3]) if data[3] else 0
                    change_pct = round((current - prev_close) / prev_close * 100, 2) if prev_close > 0 else 0

                    quotes.append(StockQuote(
                        stock_code=normalize_stock_code(code),
                        stock_name=data[0],
                        current_price=current,
                        change_percent=change_pct,
                        change_amount=round(current - prev_close, 2) if current and prev_close else 0,
                        open_price=float(data[1]) if data[1] else 0,
                        high_price=float(data[4]) if data[4] else 0,
                        low_price=float(data[5]) if data[5] else 0,
                        prev_close=prev_close,
                        volume=int(float(data[8])) if data[8] else 0,
                        amount=float(data[9]) if data[9] else 0,
                        update_time=f"{data[30]} {data[31]}" if len(data) > 31 else "",
                    ))
                except (ValueError, IndexError):
                    continue

        return quotes

    async def get_minute_data(self, stock_code: str) -> MinuteDataResponse:
        """获取分时数据"""
        url = f"https://quotes.sina.cn/cn/api/json_v2.php/CN_MarketDataService.getMinlineData?symbol={stock_code}"
        response = await self.client.get(url)

        try:
            payload = response.json()
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"解析分时数据失败: {stock_code}, {e}")
            payload = []

        # 新浪该接口在部分环境下会返回错误对象，例如：
        # {"__ERROR":3,"__ERRORMSG":"Service not found"}
        if isinstance(payload, dict) and (payload.get("__ERROR") is not None or payload.get("__ERRORMSG")):
            msg = payload.get("__ERRORMSG") or payload.get("__ERROR") or "未知错误"
            raise RuntimeError(f"新浪分时接口不可用: {msg}")

        # 兼容不同返回结构：优先提取 list
        data = payload
        if isinstance(payload, dict):
            if isinstance(payload.get("result"), dict) and isinstance(payload["result"].get("data"), list):
                data = payload["result"]["data"]
            elif isinstance(payload.get("data"), list):
                data = payload.get("data")
            else:
                raise RuntimeError("新浪分时返回结构异常：未找到数据列表")

        if not isinstance(data, list):
            raise RuntimeError(f"新浪分时返回结构异常：期望 list，实际 {type(data).__name__}")

        minute_list = []
        for item in data or []:
            if not isinstance(item, dict):
                continue
            minute_list.append(MinuteData(
                time=item.get("d", ""),
                price=self._to_float(item.get("p", 0.0)),
                volume=int(self._to_float(item.get("v", 0.0))),
                avg_price=self._to_float(item.get("a", 0.0)),
            ))

        return MinuteDataResponse(
            stock_code=stock_code,
            stock_name="",
            data=minute_list,
        )

    async def get_money_trend(self, stock_code: str, days: int = 10) -> List[Dict]:
        """获取资金流向趋势"""
        # 旧的 moneyflow/api/data 已逐步下线（常见返回 File not found.），这里先退化为“返回空”，
        # 避免接口报错导致前端阻断；需要更完整的资金趋势可改走东财日K资金流向接口（项目内已有）。
        _ = (stock_code, days)
        return []

    async def get_industry_money_rank(
        self,
        category: str = "hangye",
        sort: str = "zjlr"
    ) -> List[Dict]:
        """获取行业资金排名"""
        # 使用新浪 MoneyFlow.ssl_bkzj_bk（行业/概念板块资金），替代已下线的 moneyflow/api/data。
        sort_map = {
            "zjlr": "netamount",
            "netamount": "netamount",
            "change_percent": "avg_changeratio",
            "avg_changeratio": "avg_changeratio",
        }
        sort_field = sort_map.get(sort, "netamount")
        fenlei = 0 if category in ("hangye", "industry") else 1

        params = {"page": 1, "num": 50, "sort": sort_field, "asc": 0, "fenlei": fenlei}
        try:
            data = await self._request_quotes_service_json("MoneyFlow.ssl_bkzj_bk", params=params)
            results = []
            for item in data or []:
                results.append({
                    "bk_code": item.get("category", ""),
                    "name": item.get("name", ""),
                    "change_percent": self._to_float(item.get("avg_changeratio")) * 100,
                    "main_net_inflow": self._to_float(item.get("netamount")),
                    "main_net_inflow_percent": self._to_float(item.get("ratioamount")) * 100,
                    "leader_stock_code": normalize_stock_code(item.get("ts_symbol", "")),
                    "leader_stock_name": item.get("ts_name", ""),
                    "leader_change_percent": self._to_float(item.get("ts_changeratio")) * 100,
                })
            return results
        except Exception as e:
            logger.error(f"获取行业资金排名失败: {e}")
            return []

    async def get_money_rank(self, sort: str = "zjlr") -> List[Dict]:
        """获取个股资金排名"""
        # 使用新浪 MoneyFlow.ssl_bkzj_ssggzj（个股资金排名），替代已下线的 moneyflow/api/data。
        sort_map = {
            "zjlr": "r0_net",
            "r0_net": "r0_net",
            "trade": "trade",
            "changeratio": "changeratio",
        }
        sort_field = sort_map.get(sort, "r0_net")
        params = {"page": 1, "num": 50, "sort": sort_field, "asc": 0, "bankuai": "", "shichang": ""}

        try:
            data = await self._request_quotes_service_json("MoneyFlow.ssl_bkzj_ssggzj", params=params)
            results = []
            for item in data or []:
                inflow_yuan = self._to_float(item.get("r0_net", item.get("netamount", 0)))
                results.append({
                    "stock_code": self._strip_cn_symbol_prefix(item.get("symbol", "")),
                    "stock_name": item.get("name", ""),
                    "current_price": self._to_float(item.get("trade")),
                    "change_percent": self._to_float(item.get("changeratio")) * 100,
                    # 统一返回“万”口径（与东财 money-flow-rank 对齐）
                    "main_net_inflow": inflow_yuan / 1e4,
                    "main_net_inflow_percent": self._to_float(item.get("r0_ratio", item.get("ratioamount", 0))) * 100,
                })
            return results
        except Exception as e:
            logger.error(f"获取个股资金排名失败: {e}")
            return []

    async def get_board_money_flow_rank(
        self,
        category: str = "hangye",
        limit: int = 50,
        sort: str = "netamount",
        order: str = "desc",
    ) -> List[Dict[str, Any]]:
        """
        获取行业/概念板块资金流向排名（新浪）。

        返回字段与 MarketPanel 需求对齐：
        - bk_code/name/change_percent/main_net_inflow/main_net_inflow_percent
        - leader_stock_code/leader_stock_name/leader_change_percent（用于“行业/概念排名”兜底）
        """
        fenlei = 0 if category in ("hangye", "industry") else 1
        params = {
            "page": 1,
            "num": int(limit),
            "sort": sort,
            "asc": 1 if (order or "").lower() == "asc" else 0,
            "fenlei": fenlei,
        }

        data = await self._request_quotes_service_json("MoneyFlow.ssl_bkzj_bk", params=params)
        results: List[Dict[str, Any]] = []
        for item in data or []:
            results.append({
                "bk_code": item.get("category", ""),
                "name": item.get("name", ""),
                "change_percent": self._to_float(item.get("avg_changeratio")) * 100,
                "main_net_inflow": self._to_float(item.get("netamount")),
                "main_net_inflow_percent": self._to_float(item.get("ratioamount")) * 100,
                "leader_stock_code": normalize_stock_code(item.get("ts_symbol", "")),
                "leader_stock_name": item.get("ts_name", ""),
                "leader_change_percent": self._to_float(item.get("ts_changeratio")) * 100,
            })
        return results

    async def get_stock_money_rank(
        self,
        limit: int = 50,
        sort: str = "r0_net",
        order: str = "desc",
    ) -> List[Dict[str, Any]]:
        """获取个股资金流入排名（新浪）"""
        params = {
            "page": 1,
            "num": int(limit),
            "sort": sort,
            "asc": 1 if (order or "").lower() == "asc" else 0,
            "bankuai": "",
            "shichang": "",
        }
        data = await self._request_quotes_service_json("MoneyFlow.ssl_bkzj_ssggzj", params=params)
        results: List[Dict[str, Any]] = []
        for item in data or []:
            inflow_yuan = self._to_float(item.get("r0_net", item.get("netamount", 0)))
            results.append({
                "stock_code": self._strip_cn_symbol_prefix(item.get("symbol", "")),
                "stock_name": item.get("name", ""),
                "current_price": self._to_float(item.get("trade")),
                "change_percent": self._to_float(item.get("changeratio")) * 100,
                # 统一返回“万”口径（与东财 money-flow-rank 对齐）
                "main_net_inflow": inflow_yuan / 1e4,
                "main_net_inflow_percent": self._to_float(item.get("r0_ratio", item.get("ratioamount", 0))) * 100,
            })
        return results

    async def get_stock_rank(
        self,
        sort_by: str = "change_percent",
        order: str = "desc",
        limit: int = 50,
        market: str = "all",
    ) -> List[Dict[str, Any]]:
        """获取股票排行榜（新浪兜底，含 PB/PE）"""
        node_map = {
            "all": "hs_a",
            "main": "hs_a",
            "cyb": "cyb",
            "kcb": "kcb",
            # 新浪节点未稳定暴露北交所专用 node，这里退化为全市场节点
            "bj": "hs_a",
        }
        sort_map = {
            "change_percent": "changepercent",
            "volume": "volume",
            "amount": "amount",
            "turnover_rate": "turnoverratio",
            "pe": "per",
            "pb": "pb",
            "market_cap": "mktcap",
        }

        node = node_map.get((market or "").lower(), "hs_a")
        sort_field = sort_map.get(sort_by, "changepercent")
        asc = 1 if (order or "").lower() == "asc" else 0

        params = {"page": 1, "num": int(limit), "sort": sort_field, "asc": asc, "node": node}
        data = await self._request_quotes_service_json("Market_Center.getHQNodeData", params=params)

        results: List[Dict[str, Any]] = []
        for item in data or []:
            pe = item.get("per")
            pb = item.get("pb")
            results.append({
                "stock_code": item.get("code") or self._strip_cn_symbol_prefix(item.get("symbol", "")),
                "stock_name": item.get("name", ""),
                "current_price": self._to_float(item.get("trade")),
                "change_percent": self._to_float(item.get("changepercent")),
                "change_amount": self._to_float(item.get("pricechange")),
                "volume": int(float(item.get("volume", 0) or 0)),
                "amount": self._to_float(item.get("amount")),
                "turnover_rate": self._to_float(item.get("turnoverratio")),
                # 前端 MarketPanel 期望字段名为 pe/pb
                "pe": self._to_float(pe, default=0.0) if pe not in (None, "") else None,
                "pb": self._to_float(pb, default=0.0) if pb not in (None, "") else None,
                "total_market_cap": self._to_float(item.get("mktcap"), default=0.0) if item.get("mktcap") not in (None, "") else None,
                "float_market_cap": self._to_float(item.get("nmc"), default=0.0) if item.get("nmc") not in (None, "") else None,
            })

        return results

    async def get_news(self, limit: int = 20) -> List[NewsItem]:
        """获取新浪财经资讯"""
        params = {
            "pageid": "153",
            "lid": "2516",
            "num": limit,
            "versionNumber": "1.2.4",
        }
        response = await self.client.get(self.NEWS_URL, params=params)

        try:
            data = response.json()
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"解析新闻数据失败: {e}")
            return []

        items = []
        for item in data.get("result", {}).get("data", []) or []:
            raw_ctime = item.get("ctime", 0)
            try:
                ts = int(raw_ctime)
            except Exception:
                try:
                    ts = int(float(raw_ctime or 0))
                except Exception:
                    ts = 0
            items.append(NewsItem(
                news_id=str(item.get("oid", "")),
                title=item.get("title", ""),
                content=item.get("intro", ""),
                source="sina",
                publish_time=datetime.fromtimestamp(ts),
                url=item.get("url", ""),
                image_url=item.get("images", [{}])[0].get("u", "") if item.get("images") else "",
            ))

        return items

    @staticmethod
    def _parse_live_time(text: str) -> datetime:
        """解析新浪 7x24 create_time 字符串。"""
        t = (text or "").strip()
        if not t:
            return datetime.fromtimestamp(0)
        try:
            return datetime.strptime(t, "%Y-%m-%d %H:%M:%S")
        except Exception:
            return datetime.fromtimestamp(0)

    @staticmethod
    def _extract_live_title_and_body(rich_text: str) -> tuple[str, str]:
        """
        从新浪 7x24 rich_text 中提取标题与正文。

        规则：
        - 常见格式：`【标题】正文...`
        - 若不匹配，则 title 为空，body 为原文
        """
        text = (rich_text or "").strip()
        if text.startswith("【") and "】" in text:
            idx = text.find("】")
            title = text[1:idx].strip()
            body = text[idx + 1 :].strip()
            return title, body or title
        return "", text

    async def _get_live_feed_raw_page(self, page: int = 1, tag_id: int = 0) -> Dict[str, Any]:
        """请求新浪 7x24 feed 单页原始数据。"""
        params = {
            "page": page,
            "pagesize": self.LIVE_PROVIDER_PAGE_SIZE,
            "zhibo_id": self.LIVE_ZHIBO_ID_FINANCE,
            "tag_id": tag_id,
            "dire": "f",
            "dpc": 1,
        }
        resp = await self.client.get(self.LIVE_URL, params=params)
        resp.raise_for_status()
        try:
            payload = resp.json()
        except Exception as e:
            raise RuntimeError("新浪7x24返回非JSON（可能被拦截/接口变更）") from e

        result = payload.get("result") or {}
        status = result.get("status") or {}
        code = status.get("code")
        if isinstance(code, int) and code != 0:
            raise RuntimeError(f"新浪7x24接口返回错误: code={code}, msg={status.get('msg')}")

        data = result.get("data") or {}
        feed = data.get("feed") or {}
        if not isinstance(feed, dict):
            raise RuntimeError("新浪7x24接口返回结构异常（feed 非 dict）")
        return feed

    async def get_live_news(self, limit: int = 30) -> List[NewsItem]:
        """
        获取新浪 7x24 财经快讯（作为资讯兜底）。

        说明：
        - 该接口在部分网络环境中比 feed.mix 更稳定；
        - 由于服务端固定每页 10 条，这里按需要拉取多页后截断。
        """
        safe_limit = max(1, min(int(limit or 0), 200))
        pages = (safe_limit + self.LIVE_PROVIDER_PAGE_SIZE - 1) // self.LIVE_PROVIDER_PAGE_SIZE
        pages = max(1, min(pages, 20))

        items: List[NewsItem] = []
        for p in range(1, pages + 1):
            feed = await self._get_live_feed_raw_page(page=p, tag_id=0)
            rows = feed.get("list") or []
            if not isinstance(rows, list) or not rows:
                break

            for row in rows:
                if not isinstance(row, dict):
                    continue
                rich_text = row.get("rich_text") or ""
                title, body = self._extract_live_title_and_body(rich_text)
                docurl = row.get("docurl") or ""
                pic = row.get("pic") or ""
                items.append(
                    NewsItem(
                        news_id=f"sina7x24-{row.get('id', '')}",
                        title=title or (body[:50] + "..." if len(body) > 50 else body),
                        content=body,
                        source="sina7x24",
                        publish_time=self._parse_live_time(str(row.get("create_time") or "")),
                        url=str(docurl),
                        image_url=str(pic),
                    )
                )

            if len(items) >= safe_limit:
                break

        return items[:safe_limit]

    async def get_live_telegraph(self, page: int = 1, page_size: int = 20) -> TelegraphResponse:
        """
        获取新浪 7x24 财经快讯，并映射为统一 TelegraphResponse。

        说明：
        - 新浪接口固定每页 10 条，且 page 表示服务端页码；
        - 本方法实现项目侧 page/page_size 语义：按索引切片，并按需拉取多页。
        """
        safe_page = max(1, int(page or 1))
        safe_page_size = max(1, min(int(page_size or 0), 100))

        start = (safe_page - 1) * safe_page_size
        end = start + safe_page_size

        provider_start_page = start // self.LIVE_PROVIDER_PAGE_SIZE + 1
        provider_end_page = (end - 1) // self.LIVE_PROVIDER_PAGE_SIZE + 1
        # 安全上限：单次请求最多拉取 12 页（最多 120 条），避免过度放大
        provider_end_page = min(provider_end_page, provider_start_page + 11)

        feeds: List[Dict[str, Any]] = []
        total_num = 0

        for p in range(provider_start_page, provider_end_page + 1):
            feed = await self._get_live_feed_raw_page(page=p, tag_id=0)
            page_info = feed.get("page_info") or {}
            try:
                total_num = int(page_info.get("totalNum") or 0)
            except Exception:
                total_num = total_num or 0

            rows = feed.get("list") or []
            if not isinstance(rows, list) or not rows:
                break
            feeds.extend([r for r in rows if isinstance(r, dict)])

        provider_start_index = (provider_start_page - 1) * self.LIVE_PROVIDER_PAGE_SIZE
        rel_start = max(0, start - provider_start_index)
        rel_end = rel_start + safe_page_size
        page_rows = feeds[rel_start:rel_end] if rel_start < len(feeds) else []

        telegraph_items: List[TelegraphItem] = []
        for row in page_rows:
            rich_text = row.get("rich_text") or ""
            title, body = self._extract_live_title_and_body(rich_text)
            tags = []
            for t in (row.get("tag") or []) or []:
                if isinstance(t, dict) and t.get("name"):
                    tags.append(str(t.get("name")))

            telegraph_items.append(
                TelegraphItem(
                    telegraph_id=f"sina7x24-{row.get('id', '')}",
                    publish_time=self._parse_live_time(str(row.get("create_time") or "")),
                    title=title,
                    content=body,
                    source="sina7x24",
                    importance=1,
                    tags=tags,
                )
            )

        if total_num <= 0:
            # 兜底：按已拉取的数量估算一个“至少不小于 end”的 total
            total_num = max(end, provider_start_index + len(feeds))

        has_more = end < total_num
        return TelegraphResponse(
            items=telegraph_items,
            total=total_num,
            has_more=has_more,
            source="sina7x24",
            notice="财联社接口不可用，已降级为新浪7x24快讯",
        )

    async def get_global_indexes(self) -> GlobalIndexResponse:
        """获取全球指数"""
        # 全球主要指数代码
        index_codes = [
            "hkHSI",      # 恒生指数
            "hkHSCEI",    # 恒生国企
            "gb_$dji",    # 道琼斯
            "gb_$ixic",   # 纳斯达克
            "gb_$inx",    # 标普500
            "sh000001",   # 上证指数
            "sz399001",   # 深证成指
            "sz399006",   # 创业板指
        ]

        url = f"{self.BASE_URL}/list={','.join(index_codes)}"
        response = await self.client.get(url)
        response.encoding = "gbk"
        content = response.text

        indexes = []
        for line in content.strip().split("\n"):
            if not line or "=" not in line:
                continue

            match = re.match(r'var hq_str_(\w+)="(.*)";', line)
            if not match:
                continue

            code = match.group(1)
            data = match.group(2).split(",")

            if len(data) < 5:
                continue

            try:
                # 根据不同市场解析
                if code.startswith("hk"):
                    indexes.append(GlobalIndex(
                        code=code,
                        name=data[1] if len(data) > 1 else code,
                        current=float(data[6]) if len(data) > 6 and data[6] else 0,
                        change_percent=float(data[8]) if len(data) > 8 and data[8] else 0,
                        change_amount=float(data[7]) if len(data) > 7 and data[7] else 0,
                        update_time=f"{data[17]} {data[18]}" if len(data) > 18 else "",
                    ))
                elif code.startswith("gb_"):
                    indexes.append(GlobalIndex(
                        code=code,
                        name=data[0] if data[0] else code,
                        current=float(data[1]) if data[1] else 0,
                        change_percent=float(data[2]) if len(data) > 2 and data[2] else 0,
                        change_amount=float(data[4]) if len(data) > 4 and data[4] else 0,
                        update_time=data[3] if len(data) > 3 else "",
                    ))
                else:
                    prev_close = float(data[2]) if data[2] else 0
                    current = float(data[3]) if data[3] else 0
                    indexes.append(GlobalIndex(
                        code=code,
                        name=data[0] if data[0] else code,
                        current=current,
                        change_percent=round((current - prev_close) / prev_close * 100, 2) if prev_close > 0 else 0,
                        change_amount=round(current - prev_close, 2) if current and prev_close else 0,
                        update_time=f"{data[30]} {data[31]}" if len(data) > 31 else "",
                    ))
            except (ValueError, IndexError):
                continue

        return GlobalIndexResponse(indexes=indexes)

    async def get_market_indices(self, index_codes: List[str]) -> List[MarketIndex]:
        """
        获取指数行情（用于大盘概览）

        说明：
        - 该接口用于解析 A 股指数的完整字段（开高低/成交量/成交额/振幅）。
        - 输入代码示例：sh000001、sz399001、sz399006。
        """
        codes = [c.strip() for c in (index_codes or []) if (c or "").strip()]
        if not codes:
            return []

        url = f"{self.BASE_URL}/list={','.join(codes)}"
        resp = await self.client.get(url)
        resp.encoding = "gbk"
        content = resp.text

        results: List[MarketIndex] = []
        for line in content.strip().split("\n"):
            if not line or "=" not in line:
                continue

            match = re.match(r'var hq_str_(\w+)="(.*)";', line)
            if not match:
                continue

            code = match.group(1)
            data = match.group(2).split(",")
            if len(data) < 10:
                continue

            try:
                name = data[0] if data[0] else code
                open_price = float(data[1]) if data[1] else 0.0
                prev_close = float(data[2]) if data[2] else 0.0
                current = float(data[3]) if data[3] else 0.0
                high = float(data[4]) if data[4] else 0.0
                low = float(data[5]) if data[5] else 0.0
                volume = float(data[8]) if data[8] else 0.0
                amount = float(data[9]) if data[9] else 0.0
                update_time = f"{data[30]} {data[31]}" if len(data) > 31 else ""

                change_amount = round(current - prev_close, 4) if prev_close else 0.0
                change_percent = round((current - prev_close) / prev_close * 100, 4) if prev_close > 0 else 0.0
                amplitude = round((high - low) / prev_close * 100, 4) if prev_close > 0 else 0.0

                results.append(MarketIndex(
                    code=code,
                    name=name,
                    current=current,
                    change_percent=change_percent,
                    change_amount=change_amount,
                    open=open_price,
                    high=high,
                    low=low,
                    prev_close=prev_close,
                    volume=volume,
                    amount=amount,
                    amplitude=amplitude,
                    update_time=update_time,
                ))
            except (ValueError, IndexError):
                continue

        return results

    async def get_top_rank(self, rank_type: str = "day_rise") -> List[Dict]:
        """
        获取涨跌排名
        rank_type: day_rise(涨幅), day_fall(跌幅), volume(成交量), amount(成交额)
        """
        type_map = {
            "day_rise": "rise",
            "day_fall": "fall",
            "volume": "volume",
            "amount": "amount",
        }

        url = f"https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData"
        params = {
            "page": 1,
            "num": 50,
            "sort": type_map.get(rank_type, "rise"),
            "asc": 0 if rank_type != "day_fall" else 1,
            "node": "hs_a",
        }

        try:
            response = await self.client.get(url, params=params)
            # 解析JSONP格式 - 使用ast.literal_eval替代eval避免安全风险
            text = response.text
            # 尝试JSON解析
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                # 新浪可能返回Python格式数据，使用安全的literal_eval
                try:
                    data = ast.literal_eval(text)
                except (ValueError, SyntaxError) as e:
                    logger.warning(f"解析新浪排名数据失败: {e}")
                    return []

            results = []
            for item in data or []:
                results.append({
                    "stock_code": item.get("symbol", ""),
                    "stock_name": item.get("name", ""),
                    "current_price": float(item.get("trade", 0)),
                    "change_percent": float(item.get("changepercent", 0)),
                    "change_amount": float(item.get("pricechange", 0)),
                    "volume": int(float(item.get("volume", 0))),
                    "amount": float(item.get("amount", 0)),
                    "turnover_rate": float(item.get("turnoverratio", 0)),
                })

            return results
        except httpx.HTTPError as e:
            logger.error(f"获取涨跌排名网络错误: {e}")
            return []
        except Exception as e:
            logger.error(f"获取涨跌排名失败: {e}")
            return []
