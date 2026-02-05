# EastMoney 数据源客户端
"""
东方财富数据接口 - 完整实现
"""

import logging
import asyncio
import math
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta

import httpx

from app.schemas.market import (
    IndustryRank,
    IndustryRankResponse,
    MoneyFlowItem,
    MoneyFlowResponse,
    LongTigerItem,
    LongTigerResponse,
    EconomicDataItem,
    EconomicDataResponse,
    SectorStock,
    SectorStockResponse,
)
from app.schemas.stock import KLineResponse, KLineData, MinuteDataResponse, MinuteData
from app.utils.helpers import parse_stock_code, get_last_trading_date


logger = logging.getLogger(__name__)


class EastMoneyClient:
    """东方财富客户端"""

    BASE_URL = "https://push2.eastmoney.com"
    DATA_URL = "https://datacenter-web.eastmoney.com"
    QUOTE_URL = "https://push2his.eastmoney.com"
    REPORT_URL = "https://reportapi.eastmoney.com"

    def __init__(self):
        self.client = httpx.AsyncClient(
            timeout=30.0,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://data.eastmoney.com",
            }
        )

    @staticmethod
    def _to_cn_secucode(stock_code: str) -> tuple[str, str]:
        """
        将内部股票代码标准化为东财 datacenter 使用的 SECUCODE。

        例：
        - sh600000 -> ("600000", "600000.SH")
        - sz000001 -> ("000001", "000001.SZ")
        """
        market, pure_code = parse_stock_code(stock_code)
        code = (pure_code or "").strip()
        if market not in {"sh", "sz"} or not code.isdigit():
            return "", ""
        suffix = "SH" if market == "sh" else "SZ"
        return code, f"{code}.{suffix}"

    @staticmethod
    def _to_float(val: Any, default: float | None = None) -> float | None:
        """安全转换为 float（东财接口字段可能为 '-' / '' / '不变' / None）。"""
        if val is None:
            return default
        if isinstance(val, (int, float)):
            try:
                f = float(val)
                if math.isfinite(f):
                    return f
                return default
            except Exception:
                return default
        if isinstance(val, str):
            s = val.strip()
            if not s or s in {"-", "--"}:
                return default
            if s in {"不变", "持平"}:
                return 0.0
            try:
                f = float(s)
                if math.isfinite(f):
                    return f
                return default
            except Exception:
                return default
        return default

    @staticmethod
    def _to_int(val: Any, default: int | None = None) -> int | None:
        """安全转换为 int（支持 str/float，兼容 '不变'）。"""
        if val is None:
            return default
        if isinstance(val, bool):
            return default
        if isinstance(val, int):
            return val
        if isinstance(val, float):
            try:
                return int(val)
            except Exception:
                return default
        if isinstance(val, str):
            s = val.strip()
            if not s or s in {"-", "--"}:
                return default
            if s in {"不变", "持平"}:
                return 0
            try:
                return int(float(s))
            except Exception:
                return default
        return default

    async def close(self):
        await self.client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.close()
        return False

    # ============ K线数据 ============

    async def get_kline(
        self,
        stock_code: str,
        period: str = "day",
        count: int = 100,
        adjust: str = "qfq",
    ) -> KLineResponse:
        """
        获取K线数据（支持复权类型）

        说明：
        - 接口：push2his.eastmoney.com/api/qt/stock/kline/get
        - period 映射：day=101, week=102, month=103, 5min=5, 15min=15, 30min=30, 60min=60
        - adjust 映射：none=0, qfq=1(前复权), hfq=2(后复权)
        """
        market, pure_code = parse_stock_code(stock_code)
        code = pure_code if pure_code else (stock_code or "").strip()
        # 东方财富 secid: 1=沪市, 0=深市；这里按 A 股规则做兼容处理
        if market == "sh" or code.startswith("6"):
            secid = f"1.{code}"
        else:
            secid = f"0.{code}"

        klt_map = {
            "day": 101,
            "week": 102,
            "month": 103,
            "5min": 5,
            "15min": 15,
            "30min": 30,
            "60min": 60,
        }
        klt = klt_map.get(period)
        if klt is None:
            raise ValueError(f"东方财富K线不支持该周期: {period}")

        fqt_map = {"none": 0, "qfq": 1, "hfq": 2}
        fqt = fqt_map.get((adjust or "").strip().lower())
        if fqt is None:
            raise ValueError(f"东方财富K线不支持该复权类型: {adjust}")

        url = f"{self.QUOTE_URL}/api/qt/stock/kline/get"
        params = {
            "secid": secid,
            "klt": klt,
            "fqt": fqt,
            "lmt": count,
            "fields1": "f1,f2,f3,f4,f5,f6,f7,f8",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        }

        try:
            response = await self.client.get(url, params=params)
            payload = response.json()
        except Exception as e:
            raise RuntimeError(f"东方财富K线请求失败: {e}") from e

        # 部分网络环境下可能返回 JSON 字符串/异常提示，避免出现 `'str' object has no attribute 'get'`
        if not isinstance(payload, dict):
            snippet = (response.text or "")[:200]
            raise RuntimeError(f"东方财富K线返回异常：期望 object，实际 {type(payload).__name__}，响应片段：{snippet}")

        data = (payload or {}).get("data") or {}
        if not data:
            raise RuntimeError("东方财富K线返回为空")

        raw_klines = data.get("klines") or []
        if not raw_klines:
            raise RuntimeError("东方财富K线数据为空")

        klines: List[KLineData] = []
        for item in raw_klines:
            parts = (item or "").split(",")
            if len(parts) < 6:
                continue
            try:
                klines.append(
                    KLineData(
                        date=parts[0],
                        open=float(parts[1]),
                        close=float(parts[2]),
                        high=float(parts[3]),
                        low=float(parts[4]),
                        volume=int(float(parts[5])),
                        amount=float(parts[6]) if len(parts) > 6 else 0.0,
                        change_percent=float(parts[8]) if len(parts) > 8 and parts[8] else 0.0,
                    )
                )
            except (ValueError, TypeError):
                continue

        if not klines:
            raise RuntimeError("东方财富K线解析后为空")

        return KLineResponse(
            stock_code=stock_code,
            stock_name=data.get("name", ""),
            period=period,
            data=klines,
        )

    async def get_minute_data(self, stock_code: str) -> MinuteDataResponse:
        """
        获取分时数据（1日分时，分钟级）

        说明：
        - 使用东财 trends2 接口（push2.eastmoney.com），返回 1 日 241 个点（含午休）。
        - 返回的 trends 为字符串数组：`YYYY-MM-DD HH:MM,价格,...,成交量,成交额,均价`
        """
        market, pure_code = parse_stock_code(stock_code)
        code = pure_code if pure_code else (stock_code or "").strip()
        if not code:
            raise ValueError("股票代码不能为空")

        if market == "sh" or code.startswith("6"):
            secid = f"1.{code}"
        else:
            secid = f"0.{code}"

        url = f"{self.BASE_URL}/api/qt/stock/trends2/get"
        params = {
            "secid": secid,
            "fields1": "f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58",
            "ndays": 1,
            "iscr": 0,
            "isca": 0,
        }

        try:
            resp = await self.client.get(url, params=params)
            payload = resp.json()
        except Exception as e:
            raise RuntimeError(f"东方财富分时请求失败: {e}") from e

        if not isinstance(payload, dict):
            snippet = (resp.text or "")[:200]
            raise RuntimeError(f"东方财富分时返回异常：期望 object，实际 {type(payload).__name__}，响应片段：{snippet}")

        data = payload.get("data") or {}
        if not isinstance(data, dict):
            raise RuntimeError(f"东方财富分时返回异常：data 字段类型错误（{type(data).__name__}）")

        trends = data.get("trends") or []
        if not isinstance(trends, list):
            raise RuntimeError(f"东方财富分时返回异常：trends 字段类型错误（{type(trends).__name__}）")

        minute_list: list[MinuteData] = []
        for line in trends:
            if not isinstance(line, str) or "," not in line:
                continue
            parts = line.split(",")
            # 预期至少 6 段；典型为 8 段：time,price,prev,avg,?,vol,amount,avg_price
            if len(parts) < 6:
                continue
            time_raw = parts[0].strip()
            # "YYYY-MM-DD HH:MM" -> "HH:MM"
            time_str = time_raw.split(" ")[-1] if time_raw else ""
            try:
                price = float(parts[1]) if parts[1] else 0.0
            except Exception:
                price = 0.0

            # 成交量字段通常在第 6 段（索引5）；若格式不一致则尽量回退
            volume_raw = parts[5] if len(parts) > 5 else "0"
            try:
                volume = int(float(volume_raw)) if volume_raw else 0
            except Exception:
                volume = 0

            # 均价字段通常在最后一段（索引7），否则回退到价格
            avg_raw = parts[-1] if parts else ""
            try:
                avg_price = float(avg_raw) if avg_raw else price
            except Exception:
                avg_price = price

            minute_list.append(MinuteData(time=time_str, price=price, volume=volume, avg_price=avg_price))

        if not minute_list:
            raise RuntimeError("东方财富分时数据为空")

        return MinuteDataResponse(
            stock_code=stock_code,
            stock_name=str(data.get("name", "") or ""),
            data=minute_list,
        )

    # ============ 个股基本面数据 ============

    async def get_stock_fundamental(self, stock_code: str) -> Dict[str, Any]:
        """
        获取个股基本面数据 (PE/PB/ROE/市值/每股指标等)
        使用东方财富个股行情+F10接口
        """
        market, pure_code = parse_stock_code(stock_code)
        code = (pure_code or "").strip()
        if market not in {"sh", "sz"} or not code:
            return {}

        # 1) 首选 push2 行情接口：字段更全，但在部分网络环境会出现“空响应断连”。
        if market == "sh" or code.startswith("6"):
            secid = f"1.{code}"
        else:
            secid = f"0.{code}"

        url = f"{self.BASE_URL}/api/qt/stock/get"
        params = {
            "secid": secid,
            "fields": (
                "f43,f44,f45,f46,f47,f48,f50,f51,f52,f55,f57,f58,"
                "f9,f20,f21,f23,f37,f38,f39,f100,f115,f116,f117,"
                "f162,f167,f168,f170,f171,f173,f177,f183,f184,f185,f186,f187"
            ),
            "ut": "fa5fd1943c7b386f172d6893dbfba10b",
            "fltt": 2,
            "invt": 2,
        }

        try:
            response = await self.client.get(url, params=params)
            payload = response.json() if response is not None else {}
            data = (payload or {}).get("data") or {}
            if isinstance(data, dict) and data:
                return {
                    "stock_code": stock_code,
                    "stock_name": data.get("f58", ""),
                    "current_price": data.get("f43", 0) / 100 if data.get("f43") else 0,
                    "high": data.get("f44", 0) / 100 if data.get("f44") else 0,
                    "low": data.get("f45", 0) / 100 if data.get("f45") else 0,
                    "open": data.get("f46", 0) / 100 if data.get("f46") else 0,
                    "volume": data.get("f47", 0),
                    "amount": data.get("f48", 0),
                    # 兼容字段漂移：优先使用 f162/f167/f173 等（stock/get 口径更稳定），回退旧字段
                    "pe_dynamic": data.get("f162", data.get("f9")),
                    "pe_ttm": data.get("f115", None),
                    "pe_static": data.get("f116", None),
                    "pb": data.get("f167", data.get("f23")),
                    # 市值字段在不同接口口径不一致，优先取 f20/f21，缺失时回退到 f116/f117
                    "total_market_cap": data.get("f20", data.get("f116")),
                    "float_market_cap": data.get("f21", data.get("f117")),
                    "roe": data.get("f173", data.get("f37")),
                    "total_shares": data.get("f38", None),
                    "float_shares": data.get("f39", None),
                    "industry": data.get("f127", data.get("f100", "")),
                    "52w_high": data.get("f51", 0) / 100 if data.get("f51") else 0,
                    "52w_low": data.get("f52", 0) / 100 if data.get("f52") else 0,
                    "volume_ratio": data.get("f50", None),
                    "turnover_rate": data.get("f168", None),
                    "amplitude": data.get("f171", None),
                    "eps": data.get("f183", None),
                    "bvps": data.get("f184", None),
                    "profit_yoy": data.get("f185", None),
                    "revenue_yoy": data.get("f186", None),
                    "gross_margin": data.get("f187", None),
                }
        except Exception as e:
            logger.warning(f"获取个股基本面（push2）失败，尝试使用 datacenter/sina 兜底: {e}")

        # 2) 兜底：用 datacenter 的财务字段 + 新浪实时价推导 PB/PE（不保证动态/TTM，但至少返回可用估值骨架）。
        try:
            _, secucode = self._to_cn_secucode(stock_code)
            if not secucode:
                return {}

            # 最新一期利润表（包含 EPS/BPS/ROE/同比/毛利率等）
            income_url = f"{self.DATA_URL}/api/data/v1/get"
            income_params = {
                "reportName": "RPT_LICO_FN_CPD",
                "columns": "REPORTDATE,BASIC_EPS,BPS,WEIGHTAVG_ROE,YSTZ,SJLTZ,XSMLL",
                "filter": f'(SECUCODE="{secucode}")',
                "pageNumber": 1,
                "pageSize": 1,
                "sortColumns": "REPORTDATE",
                "sortTypes": -1,
            }
            income_resp = await self.client.get(income_url, params=income_params)
            income_payload = income_resp.json() or {}
            income_items = (income_payload.get("result") or {}).get("data") or []
            latest = income_items[0] if isinstance(income_items, list) and income_items else {}

            eps = self._to_float(latest.get("BASIC_EPS"))
            bvps = self._to_float(latest.get("BPS"))
            roe = self._to_float(latest.get("WEIGHTAVG_ROE"))
            revenue_yoy = self._to_float(latest.get("YSTZ"))
            profit_yoy = self._to_float(latest.get("SJLTZ"))
            gross_margin = self._to_float(latest.get("XSMLL"))

            # 新浪实时报价用于推导 PB/PE
            from app.datasources.sina import SinaClient

            sina = SinaClient()
            try:
                quotes = await sina.get_realtime_quotes([stock_code])
            finally:
                await sina.close()

            current_price = quotes[0].current_price if quotes else None
            pb = (current_price / bvps) if (current_price is not None and bvps not in (None, 0.0)) else None
            pe_static = (current_price / eps) if (current_price is not None and eps not in (None, 0.0)) else None

            return {
                "stock_code": stock_code,
                "stock_name": quotes[0].stock_name if quotes else "",
                "current_price": current_price or 0,
                "pe_dynamic": None,
                "pe_ttm": None,
                "pe_static": pe_static,
                "pb": pb,
                "roe": roe,
                "total_market_cap": None,
                "float_market_cap": None,
                "industry": "",
                "volume_ratio": None,
                "turnover_rate": None,
                "eps": eps,
                "bvps": bvps,
                "profit_yoy": profit_yoy,
                "revenue_yoy": revenue_yoy,
                "gross_margin": gross_margin,
            }
        except Exception as e:
            logger.warning(f"获取个股基本面兜底失败: {e}")
            return {}

    async def get_stock_rank_enhanced(
        self,
        sort_by: str = "change_percent",
        order: str = "desc",
        limit: int = 50,
        market: str = "all",
    ) -> List[Dict]:
        """
        增强版股票排行榜，包含估值字段
        sort_by: change_percent/volume/amount/turnover_rate/pe/pb/market_cap
        market: all/main/cyb/kcb/bj
        """
        field_map = {
            "change_percent": "f3",
            "volume": "f5",
            "amount": "f6",
            "turnover_rate": "f8",
            "pe": "f9",
            "pb": "f23",
            "market_cap": "f20",
        }
        sort_field = field_map.get(sort_by, "f3")

        market_map = {
            "all": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
            "main": "m:0+t:6,m:0+t:13,m:1+t:2",
            "cyb": "m:0+t:80",
            "kcb": "m:1+t:23",
            "bj": "m:0+t:81",
        }
        fs = market_map.get(market, market_map["all"])

        url = f"{self.BASE_URL}/api/qt/clist/get"
        params = {
            "pn": 1,
            "pz": limit,
            "po": 0 if order == "asc" else 1,
            "np": 1,
            "fltt": 2,
            "invt": 2,
            "fid": sort_field,
            "fs": fs,
            "fields": "f2,f3,f4,f5,f6,f7,f8,f9,f12,f14,f20,f21,f23,f37,f100,f115",
        }

        try:
            response = await self.client.get(url, params=params)
            data = response.json()

            results = []
            for item in data.get("data", {}).get("diff", []) or []:
                results.append({
                    "stock_code": item.get("f12", ""),
                    "stock_name": item.get("f14", ""),
                    "current_price": float(item.get("f2", 0)) if item.get("f2") else 0,
                    "change_percent": float(item.get("f3", 0)) if item.get("f3") else 0,
                    "change_amount": float(item.get("f4", 0)) if item.get("f4") else 0,
                    "volume": item.get("f5", 0),
                    "amount": float(item.get("f6", 0)) if item.get("f6") else 0,
                    "amplitude": float(item.get("f7", 0)) if item.get("f7") else 0,
                    "turnover_rate": float(item.get("f8", 0)) if item.get("f8") else 0,
                    "pe_dynamic": float(item.get("f9", 0)) if item.get("f9") else None,
                    "pe_ttm": float(item.get("f115", 0)) if item.get("f115") else None,
                    "pb": float(item.get("f23", 0)) if item.get("f23") else None,
                    "total_market_cap": float(item.get("f20", 0)) if item.get("f20") else None,
                    "float_market_cap": float(item.get("f21", 0)) if item.get("f21") else None,
                    "roe": float(item.get("f37", 0)) if item.get("f37") else None,
                    "industry": item.get("f100", ""),
                })

            return results
        except Exception:
            return []

    # ============ 行业排名 ============

    async def get_industry_rank(
        self,
        sort_by: str = "change_percent",
        order: str = "desc",
        limit: int = 20
    ) -> IndustryRankResponse:
        """获取行业排名"""
        field_map = {
            "change_percent": "f3",
            "turnover": "f8",
        }
        sort_field = field_map.get(sort_by, "f3")

        url = f"{self.BASE_URL}/api/qt/clist/get"
        params = {
            "pn": 1,
            "pz": limit,
            "po": 0 if order == "asc" else 1,
            "np": 1,
            "fltt": 2,
            "invt": 2,
            "fid": sort_field,
            "fs": "m:90+t:2",
            "fields": "f2,f3,f4,f8,f12,f14,f104,f105,f128,f140,f141",
        }

        response = await self.client.get(url, params=params)
        data = response.json()

        items = []
        for item in data.get("data", {}).get("diff", []) or []:
            items.append(IndustryRank(
                bk_code=item.get("f12", ""),
                bk_name=item.get("f14", ""),
                # fltt=2 时，f3 为百分比数值（如 1.98 表示 1.98%）
                change_percent=float(item.get("f3", 0) or 0),
                # f8 为换手率（%），前端展示为“换手率”
                turnover=float(item.get("f8", 0) or 0),
                leader_stock_code=item.get("f140", ""),
                leader_stock_name=item.get("f128", ""),
                leader_change_percent=float(item.get("f141", 0) or 0),
                stock_count=item.get("f104", 0),
            ))

        return IndustryRankResponse(
            items=items,
            update_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )

    # ============ 资金流向 ============

    async def get_money_flow(
        self,
        sort_by: str = "main_net_inflow",
        order: str = "desc",
        limit: int = 20
    ) -> MoneyFlowResponse:
        """获取资金流向"""
        field_map = {
            # 资金净流入（默认）
            "main_net_inflow": "f62",
            # 价格/涨跌幅排序（用于前端切换）
            "current_price": "f2",
            "change_percent": "f3",
        }
        sort_field = field_map.get(sort_by, "f62")

        url = f"{self.BASE_URL}/api/qt/clist/get"
        params = {
            "pn": 1,
            "pz": limit,
            "po": 0 if order == "asc" else 1,
            "np": 1,
            "fltt": 2,
            "invt": 2,
            "fid": sort_field,
            "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
            "fields": "f2,f3,f12,f14,f62,f184,f66,f69,f72,f75,f78,f81,f84,f87",
        }

        response = await self.client.get(url, params=params)
        data = response.json()

        items = []
        for item in data.get("data", {}).get("diff", []) or []:
            items.append(MoneyFlowItem(
                stock_code=item.get("f12", ""),
                stock_name=item.get("f14", ""),
                # fltt=2 时，f2/f3 已是“真实价格/百分比”，不要再缩放
                current_price=float(item.get("f2", 0) or 0),
                change_percent=float(item.get("f3", 0) or 0),
                main_net_inflow=item.get("f62", 0) / 10000 if item.get("f62") else 0,
                # f184 为百分比数值（如 6.12 表示 6.12%）
                main_net_inflow_percent=float(item.get("f184", 0) or 0),
                super_large_net_inflow=item.get("f66", 0) / 10000 if item.get("f66") else 0,
                large_net_inflow=item.get("f72", 0) / 10000 if item.get("f72") else 0,
                medium_net_inflow=item.get("f78", 0) / 10000 if item.get("f78") else 0,
                small_net_inflow=item.get("f84", 0) / 10000 if item.get("f84") else 0,
            ))

        return MoneyFlowResponse(
            items=items,
            update_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )

    async def get_money_flow_rank(
        self,
        sort_by: str = "main_net_inflow",
        order: str = "desc",
        limit: int = 50
    ) -> List[Dict]:
        """获取资金流向排名"""
        result = await self.get_money_flow(sort_by, order, limit)
        return [item.model_dump() for item in result.items]

    async def get_board_money_flow_rank(
        self,
        category: str = "hangye",
        sort_by: str = "main_net_inflow",
        order: str = "desc",
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        获取板块资金流向排名（行业/概念/地域）

        说明：
        - 复用东财板块资金页面（data.eastmoney.com/bkzj）同源接口
        - 返回字段与前端 MarketPanel 的 money 表格对齐：name/change_percent/main_net_inflow/main_net_inflow_percent

        Args:
            category: hangye(行业)/gainian(概念)/diqu(地域)
            sort_by: main_net_inflow/change_percent（目前前端仅使用 main_net_inflow）
            order: asc/desc
            limit: 条数
        """
        category_map = {
            "hangye": "m:90 t:2",
            "gainian": "m:90 t:3",
            "diqu": "m:90 t:1",
        }
        fs = category_map.get(category, category_map["hangye"])

        field_map = {
            "main_net_inflow": "f62",
            "change_percent": "f3",
        }
        sort_field = field_map.get(sort_by, "f62")

        url = f"{self.BASE_URL}/api/qt/clist/get"
        params = {
            "pn": 1,
            "pz": limit,
            "po": 0 if order == "asc" else 1,
            "np": 1,
            "fltt": 2,
            "invt": 2,
            "fid": sort_field,
            "fs": fs,
            "stat": 1,
            # 仅取必要字段：板块代码/名称、涨跌幅、净流入、净流入占比
            "fields": "f12,f14,f3,f62,f184",
            # 东财部分页面同源参数，缺失时接口可能返回空/断连
            "ut": "8dec03ba335b81bf4ebdf7b29ec27d15",
        }

        response = await self.client.get(url, params=params)
        data = response.json() or {}

        results: List[Dict[str, Any]] = []
        for item in (data.get("data") or {}).get("diff", []) or []:
            results.append({
                "bk_code": item.get("f12", ""),
                "name": item.get("f14", ""),
                "change_percent": float(item.get("f3", 0) or 0),
                "main_net_inflow": float(item.get("f62", 0) or 0),
                "main_net_inflow_percent": float(item.get("f184", 0) or 0),
            })

        return results

    async def get_stock_money_flow(self, stock_code: str, days: int = 10) -> List[Dict]:
        """获取个股资金流向"""
        # 转换股票代码
        code = stock_code.replace("sh", "").replace("sz", "")
        if stock_code.startswith("sh"):
            secid = f"1.{code}"
        else:
            secid = f"0.{code}"

        # 注意：push2 域名在部分网络环境下会“空响应断连”，而 push2his 可用且返回结构一致
        url = f"{self.QUOTE_URL}/api/qt/stock/fflow/daykline/get"
        params = {
            "secid": secid,
            "fields1": "f1,f2,f3,f7",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65",
            "lmt": days,
        }

        response = await self.client.get(url, params=params)
        data = response.json()

        results = []
        klines = data.get("data", {}).get("klines", []) or []
        for line in klines:
            parts = line.split(",")
            if len(parts) >= 10:
                results.append({
                    "date": parts[0],
                    "main_net_inflow": float(parts[1]) / 10000,
                    "small_net_inflow": float(parts[5]) / 10000,
                    "medium_net_inflow": float(parts[4]) / 10000,
                    "large_net_inflow": float(parts[3]) / 10000,
                    "super_large_net_inflow": float(parts[2]) / 10000,
                })

        return results

    # ============ 龙虎榜 ============

    async def get_long_tiger(self, trade_date: Optional[str] = None) -> LongTigerResponse:
        """获取龙虎榜"""
        if not trade_date:
            # 默认使用“最近交易日”（包含节假日休市判断，避免取到无数据日期）
            trade_date = get_last_trading_date()

        url = f"{self.DATA_URL}/api/data/v1/get"
        params = {
            "reportName": "RPT_DAILYBILLBOARD_DETAILSNEW",
            "columns": "ALL",
            "filter": f"(TRADE_DATE='{trade_date}')",
            "pageSize": 50,
            # 2026-02-02：东财字段变更，旧 NET_BUY_AMT 不再存在
            "sortColumns": "BILLBOARD_NET_AMT",
            "sortTypes": -1,
        }

        response = await self.client.get(url, params=params)
        data = response.json()

        items = []
        for item in data.get("result", {}).get("data", []) or []:
            # 兼容字段变更：优先使用新字段，回退旧字段
            net_buy = item.get("BILLBOARD_NET_AMT", item.get("NET_BUY_AMT", 0)) or 0
            buy_amt = item.get("BILLBOARD_BUY_AMT", item.get("BUY_AMT", 0)) or 0
            sell_amt = item.get("BILLBOARD_SELL_AMT", item.get("SELL_AMT", 0)) or 0

            secucode = item.get("SECUCODE", "") or ""
            stock_code = ""
            if isinstance(secucode, str) and secucode:
                stock_code = secucode.split(".")[0]
            if not stock_code:
                stock_code = str(item.get("SECURITY_CODE", "") or "")

            items.append(LongTigerItem(
                trade_date=trade_date,
                stock_code=stock_code,
                stock_name=item.get("SECURITY_NAME_ABBR", ""),
                close_price=float(item.get("CLOSE_PRICE", 0)),
                change_percent=float(item.get("CHANGE_RATE", 0)),
                net_buy_amount=float(net_buy) / 10000,
                buy_amount=float(buy_amt) / 10000,
                sell_amount=float(sell_amt) / 10000,
                reason=item.get("EXPLANATION", "") or item.get("EXPLAIN", ""),
            ))

        return LongTigerResponse(items=items, trade_date=trade_date)

    # ============ 宏观经济数据 ============

    async def get_economic_data(
        self,
        indicator: str,
        count: int = 20
    ) -> EconomicDataResponse:
        """获取宏观经济数据"""
        indicator_map = {
            "GDP": "EMM00000592",
            "CPI": "EMM00000593",
            "PPI": "EMM00000594",
            "PMI": "EMM00000595",
        }

        code = indicator_map.get(indicator.upper(), "EMM00000592")

        url = f"{self.DATA_URL}/api/data/v1/get"
        params = {
            "reportName": "RPT_ECONOMY_MACRO_MAIN",
            "columns": "ALL",
            "filter": f'(INDICATOR_ID="{code}")',
            "pageSize": count,
            "sortColumns": "REPORT_DATE",
            "sortTypes": -1,
        }

        response = await self.client.get(url, params=params)
        data = response.json()

        items = []
        for item in data.get("result", {}).get("data", []) or []:
            items.append(EconomicDataItem(
                report_date=item.get("REPORT_DATE", "")[:10],
                indicator_name=item.get("INDICATOR_NAME", ""),
                value=float(item.get("INDICATOR_VALUE", 0)) if item.get("INDICATOR_VALUE") else 0,
                yoy_change=float(item.get("YOY", 0)) if item.get("YOY") else 0,
                mom_change=float(item.get("MOM", 0)) if item.get("MOM") else 0,
            ))

        return EconomicDataResponse(indicator=indicator, items=items)

    # ============ 板块成分股 ============

    async def get_sector_stocks(
        self,
        bk_code: str,
        limit: int = 50
    ) -> SectorStockResponse:
        """获取板块成分股"""
        url = f"{self.BASE_URL}/api/qt/clist/get"
        params = {
            "pn": 1,
            "pz": limit,
            "po": 1,
            "np": 1,
            "fltt": 2,
            "invt": 2,
            "fid": "f3",
            "fs": f"b:{bk_code}+f:!50",
            "fields": "f2,f3,f8,f12,f14,f20",
        }

        response = await self.client.get(url, params=params)
        data = response.json()

        stocks = []
        for item in data.get("data", {}).get("diff", []) or []:
            stocks.append(SectorStock(
                stock_code=item.get("f12", ""),
                stock_name=item.get("f14", ""),
                # fltt=2 时，f2/f3/f8 已是“真实价格/百分比”，不要再缩放
                current_price=float(item.get("f2", 0) or 0),
                change_percent=float(item.get("f3", 0) or 0),
                turnover_rate=float(item.get("f8", 0) or 0),
                market_value=item.get("f20", 0) / 100000000 if item.get("f20") else 0,
            ))

        return SectorStockResponse(bk_code=bk_code, bk_name="", stocks=stocks)

    # ============ 股票排名 ============

    async def get_stock_rank(
        self,
        sort_by: str = "change_percent",
        order: str = "desc",
        limit: int = 50
    ) -> List[Dict]:
        """获取股票排名"""
        field_map = {
            "change_percent": "f3",
            "volume": "f5",
            "amount": "f6",
            "turnover_rate": "f8",
        }
        sort_field = field_map.get(sort_by, "f3")

        url = f"{self.BASE_URL}/api/qt/clist/get"
        params = {
            "pn": 1,
            "pz": limit,
            "po": 0 if order == "asc" else 1,
            "np": 1,
            "fltt": 2,
            "invt": 2,
            "fid": sort_field,
            "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
            "fields": "f2,f3,f4,f5,f6,f7,f8,f12,f14",
        }

        response = await self.client.get(url, params=params)
        data = response.json()

        results = []
        for item in data.get("data", {}).get("diff", []) or []:
            results.append({
                "stock_code": item.get("f12", ""),
                "stock_name": item.get("f14", ""),
                "current_price": item.get("f2", 0) / 100 if item.get("f2") else 0,
                "change_percent": item.get("f3", 0) / 100 if item.get("f3") else 0,
                "change_amount": item.get("f4", 0) / 100 if item.get("f4") else 0,
                "volume": item.get("f5", 0),
                "amount": item.get("f6", 0),
                "turnover_rate": item.get("f8", 0) / 100 if item.get("f8") else 0,
            })

        return results

    # ============ 涨停/跌停 ============

    async def get_limit_up_stocks(self) -> List[Dict]:
        """获取涨停股"""
        url = f"{self.BASE_URL}/api/qt/clist/get"
        params = {
            "pn": 1,
            "pz": 100,
            "po": 1,
            "np": 1,
            "fltt": 2,
            "invt": 2,
            "fid": "f3",
            "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
            "fields": "f2,f3,f4,f5,f6,f7,f8,f12,f14,f15,f16,f17,f18",
        }

        try:
            results: List[Dict[str, Any]] = []
            pn = 1

            while True:
                params["pn"] = pn
                response = await self.client.get(url, params=params)
                payload = response.json() or {}
                diff = (payload.get("data") or {}).get("diff") or []
                if not diff:
                    break

                should_stop = False
                for item in diff:
                    # fltt=2 时，f3 直接返回百分比数值（如 10.50 表示 10.50%）
                    try:
                        change_percent = float(item.get("f3", 0) or 0)
                    except (ValueError, TypeError):
                        change_percent = 0.0

                    # 涨停判断：默认按 >=9.9%（与现有逻辑保持一致）
                    if change_percent >= 9.9:
                        results.append({
                            "stock_code": item.get("f12", ""),
                            "stock_name": item.get("f14", ""),
                            "current_price": float(item.get("f2", 0) or 0),
                            "change_percent": change_percent,
                            "volume": item.get("f5", 0),
                            "amount": float(item.get("f6", 0) or 0),
                        })
                        continue

                    # 已按涨跌幅降序排序，首次低于阈值即可停止翻页
                    should_stop = True
                    break

                if should_stop:
                    break
                pn += 1

            return results
        except Exception:
            return []

    async def get_limit_down_stocks(self) -> List[Dict]:
        """获取跌停股"""
        url = f"{self.BASE_URL}/api/qt/clist/get"
        params = {
            "pn": 1,
            "pz": 100,
            "po": 0,  # 升序，跌幅最大的在前
            "np": 1,
            "fltt": 2,
            "invt": 2,
            "fid": "f3",
            "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
            "fields": "f2,f3,f4,f5,f6,f7,f8,f12,f14",
        }

        try:
            results: List[Dict[str, Any]] = []
            pn = 1

            while True:
                params["pn"] = pn
                response = await self.client.get(url, params=params)
                payload = response.json() or {}
                diff = (payload.get("data") or {}).get("diff") or []
                if not diff:
                    break

                should_stop = False
                for item in diff:
                    # fltt=2 时，f3 直接返回百分比数值（如 -10.50 表示 -10.50%）
                    try:
                        change_percent = float(item.get("f3", 0) or 0)
                    except (ValueError, TypeError):
                        change_percent = 0.0

                    # 跌停判断：默认按 <=-9.9%（与现有逻辑保持一致）
                    if change_percent <= -9.9:
                        results.append({
                            "stock_code": item.get("f12", ""),
                            "stock_name": item.get("f14", ""),
                            "current_price": float(item.get("f2", 0) or 0),
                            "change_percent": change_percent,
                            "volume": item.get("f5", 0),
                            "amount": float(item.get("f6", 0) or 0),
                        })
                        continue

                    # 已按涨跌幅升序排序，首次高于阈值即可停止翻页
                    should_stop = True
                    break

                if should_stop:
                    break
                pn += 1

            return results
        except Exception:
            return []

    # ============ 大盘统计（涨跌家数/成交额）===========

    async def _fetch_a_spot_page(self, pn: int, pz: int = 100) -> Dict[str, Any]:
        """
        获取 A 股全市场快照分页数据（用于统计，不做业务层过滤）

        返回结构示例：
        {
          "total": 5506,
          "diff": [ {"f3": 1.23, "f6": 123456.0, ...}, ... ]
        }
        """
        url = f"{self.BASE_URL}/api/qt/clist/get"
        params = {
            "pn": pn,
            "pz": pz,
            "po": 1,
            "np": 1,
            "fltt": 2,
            "invt": 2,
            "fid": "f3",
            "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
            # 统计只需要：涨跌幅、成交额；附带代码/名称便于排查
            "fields": "f3,f6,f12,f14",
        }

        # 简单重试：避免偶发网络抖动导致统计全部失败
        last_error: Optional[Exception] = None
        for attempt in range(1, 3):
            try:
                resp = await self.client.get(url, params=params)
                data = (resp.json() or {}).get("data") or {}
                return {
                    "total": int(data.get("total", 0) or 0),
                    "diff": data.get("diff") or [],
                }
            except Exception as e:
                last_error = e
                if attempt < 2:
                    await asyncio.sleep(0.2)
        raise RuntimeError(f"获取A股快照失败: {last_error}") from last_error

    async def get_a_spot_statistics(self) -> Dict[str, Any]:
        """
        获取市场概览统计（涨跌家数/涨跌停家数/两市成交额）

        说明：
        - 东方财富 clist/get 单页 diff 固定上限 100，需要分页汇总。
        - 为避免请求过慢，这里采用有限并发抓取（默认并发 6）。
        - 成交额单位按东财返回口径汇总后换算为“亿元”。
        """
        first = await self._fetch_a_spot_page(1, pz=100)
        total = int(first.get("total", 0) or 0)
        total_pages = int(math.ceil(total / 100)) if total > 0 else 0

        counters = {
            "total": total,
            "up_count": 0,
            "down_count": 0,
            "flat_count": 0,
            "limit_up_count": 0,
            "limit_down_count": 0,
            "total_amount": 0.0,  # 原始金额（元）
        }

        def _accumulate(diff: List[Dict[str, Any]]) -> None:
            for item in diff or []:
                try:
                    change_percent = float(item.get("f3", 0) or 0)
                except (ValueError, TypeError):
                    change_percent = 0.0

                if change_percent > 0:
                    counters["up_count"] += 1
                elif change_percent < 0:
                    counters["down_count"] += 1
                else:
                    counters["flat_count"] += 1

                # 与现有逻辑保持一致：>=9.9 视为涨停，<=-9.9 视为跌停
                if change_percent >= 9.9:
                    counters["limit_up_count"] += 1
                elif change_percent <= -9.9:
                    counters["limit_down_count"] += 1

                try:
                    amount = float(item.get("f6", 0) or 0)
                except (ValueError, TypeError):
                    amount = 0.0
                counters["total_amount"] += amount

        _accumulate(first.get("diff") or [])

        if total_pages <= 1:
            counters["total_amount_yi"] = round(counters["total_amount"] / 1e8, 2)
            return counters

        sem = asyncio.Semaphore(6)

        async def _fetch_and_accumulate(pn: int) -> None:
            async with sem:
                page = await self._fetch_a_spot_page(pn, pz=100)
                _accumulate(page.get("diff") or [])

        tasks = [asyncio.create_task(_fetch_and_accumulate(pn)) for pn in range(2, total_pages + 1)]
        # 等待全部完成（如任一抛错，直接向上抛，避免返回半套统计）
        await asyncio.gather(*tasks)

        counters["total_amount_yi"] = round(counters["total_amount"] / 1e8, 2)
        return counters

    # ============ 量比排名 ============

    async def get_volume_ratio_rank(self, min_ratio: float = 2.0, limit: int = 50) -> List[Dict]:
        """获取量比排名"""
        url = f"{self.BASE_URL}/api/qt/clist/get"
        params = {
            "pn": 1,
            "pz": limit,
            "po": 1,
            "np": 1,
            "fltt": 2,
            "invt": 2,
            "fid": "f10",  # 量比
            "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
            "fields": "f2,f3,f5,f6,f10,f12,f14",
        }

        response = await self.client.get(url, params=params)
        data = response.json()

        results = []
        for item in data.get("data", {}).get("diff", []) or []:
            volume_ratio = item.get("f10", 0) / 100 if item.get("f10") else 0
            if volume_ratio >= min_ratio:
                results.append({
                    "stock_code": item.get("f12", ""),
                    "stock_name": item.get("f14", ""),
                    "current_price": item.get("f2", 0) / 100 if item.get("f2") else 0,
                    "change_percent": item.get("f3", 0) / 100 if item.get("f3") else 0,
                    "volume_ratio": volume_ratio,
                    "volume": item.get("f5", 0),
                    "amount": item.get("f6", 0),
                })

        return results

    # ============ 热门策略 ============

    async def get_hot_strategies(self) -> List[Dict]:
        """获取热门选股策略"""
        # 返回预定义的策略列表
        return [
            {"name": "涨停股", "words": "涨停", "description": "今日涨停的股票"},
            {"name": "主力资金流入", "words": "主力资金流入", "description": "主力资金净流入排名"},
            {"name": "量比异动", "words": "量比大于3", "description": "量比大于3的股票"},
            {"name": "龙虎榜", "words": "龙虎榜", "description": "今日龙虎榜股票"},
            {"name": "放量上涨", "words": "放量上涨", "description": "成交量放大且上涨的股票"},
            {"name": "突破均线", "words": "突破均线", "description": "股价突破重要均线"},
        ]

    # ============ 股票概念 ============

    async def get_stock_concepts(self, stock_code: str) -> List[Dict]:
        """获取股票所属概念"""
        code = stock_code.replace("sh", "").replace("sz", "")
        if stock_code.startswith("sh"):
            secid = f"1.{code}"
        else:
            secid = f"0.{code}"

        url = f"{self.BASE_URL}/api/qt/slist/get"
        params = {
            "secid": secid,
            "spt": 3,
            "fields": "f12,f14,f3,f152",
        }

        response = await self.client.get(url, params=params)
        data = response.json()

        results = []
        for item in data.get("data", []) or []:
            results.append({
                "bk_code": item.get("f12", ""),
                "bk_name": item.get("f14", ""),
                "change_percent": item.get("f3", 0) / 100 if item.get("f3") else 0,
            })

        return results

    # ============ 热门股票 ============

    async def get_hot_stocks(self, market: str = "A", limit: int = 20) -> List[Dict]:
        """获取热门股票"""
        # 使用成交额排名作为热门股票
        return await self.get_stock_rank("amount", "desc", limit)

    # ============ 研究报告 ============

    async def get_stock_research_reports(self, stock_code: str, limit: int = 20) -> List[Dict]:
        """获取股票研究报告"""
        _, code = parse_stock_code(stock_code)
        code = (code or "").strip()
        if not code:
            return []

        # datacenter 的 RPT_RES_REPORT 在 2026-02 期间已不稳定/部分报表下线，且不支持 like 查询；
        # 这里改用 reportapi（东方财富研报列表）作为主数据源。
        today = datetime.now().date()
        begin = (today - timedelta(days=365 * 2)).strftime("%Y-%m-%d")
        end = (today + timedelta(days=365)).strftime("%Y-%m-%d")

        url = f"{self.REPORT_URL}/report/list"
        params = {"pageNo": 1, "pageSize": int(limit), "code": code, "beginTime": begin, "endTime": end, "qType": 0}
        resp = await self.client.get(url, params=params)
        payload = resp.json() or {}
        items = payload.get("data") or []
        if not isinstance(items, list):
            return []

        results: List[Dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            author = item.get("author")
            if isinstance(author, list):
                author_out = ",".join([str(a) for a in author if a])
            else:
                author_out = str(author or "")

            rating = item.get("emRatingName") or item.get("sRatingName") or ""
            target_price = self._to_float(item.get("indvAimPriceT"))
            if target_price in (None, 0.0):
                target_price = self._to_float(item.get("indvAimPriceL"))

            results.append(
                {
                    "title": str(item.get("title", "") or ""),
                    "publish_date": str(item.get("publishDate", "") or "")[:10],
                    "org_name": str(item.get("orgSName", "") or item.get("orgName", "") or ""),
                    "author": author_out,
                    "rating": str(rating or ""),
                    "target_price": target_price,
                    "url": str(item.get("encodeUrl", "") or ""),
                }
            )

        return results[: int(limit)]

    # ============ 股票公告 ============

    async def get_stock_notices(self, stock_code: str, limit: int = 20) -> List[Dict]:
        """获取股票公告"""
        code = stock_code.replace("sh", "").replace("sz", "")

        url = f"{self.DATA_URL}/api/data/v1/get"
        params = {
            "reportName": "RPT_CUSTOM_STOCK_NOTICE",
            "columns": "ALL",
            "filter": f'(SECUCODE like "{code}%")',
            "pageSize": limit,
            "sortColumns": "NOTICE_DATE",
            "sortTypes": -1,
        }

        response = await self.client.get(url, params=params)
        data = response.json()

        results = []
        for item in data.get("result", {}).get("data", []) or []:
            results.append({
                "title": item.get("NOTICE_TITLE", ""),
                "notice_date": item.get("NOTICE_DATE", "")[:10],
                "notice_type": item.get("NOTICE_TYPE", ""),
                "url": item.get("URL", ""),
            })

        return results

    # ============ 搜索概念/行业 ============

    async def search_concept(self, keyword: str) -> List[Dict]:
        """搜索概念板块"""
        url = f"{self.BASE_URL}/api/qt/clist/get"
        params = {
            "pn": 1,
            "pz": 20,
            "po": 1,
            "np": 1,
            "fltt": 2,
            "invt": 2,
            "fid": "f3",
            "fs": "m:90+t:3",  # 概念板块
            "fields": "f2,f3,f12,f14,f104",
        }

        response = await self.client.get(url, params=params)
        data = response.json()

        results = []
        for item in data.get("data", {}).get("diff", []) or []:
            name = item.get("f14", "")
            if keyword in name:
                results.append({
                    "bk_code": item.get("f12", ""),
                    "bk_name": name,
                    "bk_type": "concept",
                    "change_percent": item.get("f3", 0) / 100 if item.get("f3") else 0,
                    "stock_count": item.get("f104", 0),
                })

        return results

    async def search_industry(self, keyword: str) -> List[Dict]:
        """搜索行业板块"""
        url = f"{self.BASE_URL}/api/qt/clist/get"
        params = {
            "pn": 1,
            "pz": 20,
            "po": 1,
            "np": 1,
            "fltt": 2,
            "invt": 2,
            "fid": "f3",
            "fs": "m:90+t:2",  # 行业板块
            "fields": "f2,f3,f12,f14,f104",
        }

        response = await self.client.get(url, params=params)
        data = response.json()

        results = []
        for item in data.get("data", {}).get("diff", []) or []:
            name = item.get("f14", "")
            if keyword in name:
                results.append({
                    "bk_code": item.get("f12", ""),
                    "bk_name": name,
                    "bk_type": "industry",
                    "change_percent": item.get("f3", 0) / 100 if item.get("f3") else 0,
                    "stock_count": item.get("f104", 0),
                })

        return results

    # ============ 机构评级汇总 ============

    async def get_stock_rating_summary(self, stock_code: str, limit: int = 50) -> Dict[str, Any]:
        """
        获取机构评级汇总
        统计近6个月内各机构的评级分布和一致预期目标价
        """
        _, code = parse_stock_code(stock_code)
        code = (code or "").strip()
        if not code:
            return {"stock_code": stock_code, "rating_count": 0, "ratings": {}, "reports": []}

        # reportapi 需要 beginTime/endTime，否则会 4xx/5xx；这里取近 1 年，覆盖“近 6 个月”统计需求。
        today = datetime.now().date()
        begin = (today - timedelta(days=365)).strftime("%Y-%m-%d")
        end = (today + timedelta(days=30)).strftime("%Y-%m-%d")

        try:
            url = f"{self.REPORT_URL}/report/list"
            params = {"pageNo": 1, "pageSize": int(limit), "code": code, "beginTime": begin, "endTime": end, "qType": 0}
            resp = await self.client.get(url, params=params)
            payload = resp.json() or {}
            reports = payload.get("data") or []
            if not isinstance(reports, list) or not reports:
                return {"stock_code": stock_code, "rating_count": 0, "ratings": {}, "reports": []}

            rating_counts: Dict[str, int] = {}
            target_prices: list[float] = []
            org_ratings: list[Dict[str, Any]] = []

            for item in reports:
                if not isinstance(item, dict):
                    continue
                rating = item.get("emRatingName") or item.get("sRatingName") or ""
                rating_str = str(rating or "").strip()
                if rating_str:
                    rating_counts[rating_str] = rating_counts.get(rating_str, 0) + 1

                tp = self._to_float(item.get("indvAimPriceT"))
                if tp in (None, 0.0):
                    tp = self._to_float(item.get("indvAimPriceL"))
                if tp is not None and tp > 0:
                    target_prices.append(tp)

                author = item.get("author")
                if isinstance(author, list):
                    author_out = ",".join([str(a) for a in author if a])
                else:
                    author_out = str(author or "")

                org_ratings.append(
                    {
                        "org_name": str(item.get("orgSName", "") or item.get("orgName", "") or ""),
                        "author": author_out,
                        "rating": rating_str,
                        "target_price": tp,
                        "publish_date": str(item.get("publishDate", "") or "")[:10],
                        "title": str(item.get("title", "") or ""),
                        "url": str(item.get("encodeUrl", "") or ""),
                    }
                )

            avg_target = round(sum(target_prices) / len(target_prices), 2) if target_prices else None
            max_target = max(target_prices) if target_prices else None
            min_target = min(target_prices) if target_prices else None

            return {
                "stock_code": stock_code,
                "rating_count": len(org_ratings),
                "ratings": rating_counts,
                "consensus_target_price": avg_target,
                "max_target_price": max_target,
                "min_target_price": min_target,
                "target_price_count": len(target_prices),
                "reports": org_ratings,
            }
        except Exception as e:
            logger.warning(f"获取机构评级汇总失败: {e}")
            return {"stock_code": stock_code, "rating_count": 0, "ratings": {}, "reports": []}

    # ============ 个股历史资金流向 ============

    async def get_stock_money_flow_history(self, stock_code: str, days: int = 30) -> List[Dict]:
        """
        获取个股历史资金流向(每日明细)
        包含主力/超大单/大单/中单/小单的净流入
        """
        code = stock_code.replace("sh", "").replace("sz", "")
        if stock_code.startswith("sh") or code.startswith("6"):
            secid = f"1.{code}"
        else:
            secid = f"0.{code}"

        # 注意：push2 域名在部分网络环境下会“空响应断连”，而 push2his 可用且返回结构一致
        url = f"{self.QUOTE_URL}/api/qt/stock/fflow/daykline/get"
        params = {
            "secid": secid,
            "lmt": days,
            "klt": 101,
            "fields1": "f1,f2,f3,f7",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65",
            "ut": "b2884a393a59ad64002292a3e90d46a5",
        }

        try:
            response = await self.client.get(url, params=params)
            data = response.json().get("data", {})
            klines = data.get("klines", [])

            results = []
            for line in klines:
                parts = line.split(",")
                if len(parts) >= 13:
                    results.append({
                        "date": parts[0],
                        "main_net_inflow": float(parts[1]),        # 主力净流入
                        "small_net_inflow": float(parts[2]),       # 小单净流入
                        "mid_net_inflow": float(parts[3]),         # 中单净流入
                        "large_net_inflow": float(parts[4]),       # 大单净流入
                        "super_large_net_inflow": float(parts[5]), # 超大单净流入
                        "main_net_inflow_pct": float(parts[6]),    # 主力净占比
                        "small_net_inflow_pct": float(parts[7]),   # 小单净占比
                        "mid_net_inflow_pct": float(parts[8]),     # 中单净占比
                        "large_net_inflow_pct": float(parts[9]),   # 大单净占比
                        "super_large_net_inflow_pct": float(parts[10]),  # 超大单净占比
                        "close": float(parts[11]),                 # 收盘价
                        "change_percent": float(parts[12]),        # 涨跌幅
                    })

            return results
        except Exception:
            return []

    # ============ 股东人数变化 ============

    async def get_shareholder_count(self, stock_code: str) -> List[Dict]:
        """
        获取股东人数变化数据
        反映筹码集中度趋势
        """
        _, secucode = self._to_cn_secucode(stock_code)
        if not secucode:
            return []

        url = f"{self.DATA_URL}/api/data/v1/get"
        params = {
            # 股东人数变化：RPT_F10_EH_HOLDERNUM（原实现误用 FREEHOLDERS 导致字段缺失而静默空）
            "reportName": "RPT_F10_EH_HOLDERNUM",
            "columns": "ALL",
            # datacenter 已不支持 like 查询（9501），必须使用等号
            "filter": f'(SECUCODE="{secucode}")',
            "pageNumber": 1,
            "pageSize": 10,
            "sortColumns": "END_DATE",
            "sortTypes": -1,
        }

        try:
            response = await self.client.get(url, params=params)
            data = response.json()
            items = data.get("result", {}).get("data", []) or []

            results = []
            for item in items:
                holder_num = self._to_int(item.get("HOLDER_TOTAL_NUM") or item.get("HOLDER_A_NUM") or item.get("HOLDER_NUM"))
                change_pct = self._to_float(item.get("TOTAL_NUM_RATIO") or item.get("HOLDER_ANUM_RATIO") or item.get("HOLDER_NUM_CHANGE_RATIO"))
                avg_hold_amt = self._to_float(item.get("AVG_HOLD_AMT") or item.get("AVG_HOLD_AMOUNT"))
                results.append({
                    "end_date": item.get("END_DATE", "")[:10],
                    "holder_num": holder_num,
                    "holder_num_change": self._to_int(item.get("HOLDER_NUM_CHANGE")),
                    "holder_num_change_pct": change_pct,
                    "avg_hold_amount": avg_hold_amt,
                    "avg_hold_amount_change": self._to_float(item.get("AVG_HOLD_AMOUNT_CHANGE")),
                })

            return results
        except Exception:
            return []

    # ============ 十大股东/流通股东 ============

    async def get_top_holders(self, stock_code: str, holder_type: str = "float") -> List[Dict]:
        """
        获取十大股东或十大流通股东
        holder_type: "float"=流通股东, "total"=总股东
        """
        _, secucode = self._to_cn_secucode(stock_code)
        if not secucode:
            return []

        report_name = "RPT_F10_EH_FREEHOLDERS" if holder_type == "float" else "RPT_F10_EH_HOLDERS"
        url = f"{self.DATA_URL}/api/data/v1/get"
        params = {
            "reportName": report_name,
            "columns": "ALL",
            # datacenter 已不支持 like 查询（9501），必须使用等号
            "filter": f'(SECUCODE="{secucode}")',
            "pageNumber": 1,
            "pageSize": 10,
            "sortColumns": "HOLD_NUM",
            "sortTypes": -1,
        }

        try:
            response = await self.client.get(url, params=params)
            data = response.json()
            items = data.get("result", {}).get("data", []) or []

            results = []
            for item in items:
                hold_ratio = self._to_float(item.get("HOLD_RATIO") or item.get("HOLD_NUM_RATIO"))
                hold_num = self._to_int(item.get("HOLD_NUM"))
                change_num = self._to_int(item.get("HOLD_NUM_CHANGE") or item.get("HOLD_CHANGE"))
                change_ratio = self._to_float(item.get("HOLD_RATIO_CHANGE") or item.get("CHANGE_RATIO") or item.get("HOLD_CHANGE_RATIOTB"))
                results.append({
                    "holder_name": item.get("HOLDER_NAME", ""),
                    "hold_num": hold_num,
                    "hold_ratio": hold_ratio,
                    "change": change_num,
                    "change_ratio": change_ratio,
                    "holder_type": item.get("HOLDER_TYPE", ""),
                    "end_date": item.get("END_DATE", "")[:10] if item.get("END_DATE") else "",
                })

            return results
        except Exception:
            return []

    # ============ 分红送转历史 ============

    async def get_dividend_history(self, stock_code: str) -> List[Dict]:
        """获取分红送转历史"""
        _, secucode = self._to_cn_secucode(stock_code)
        if not secucode:
            return []

        url = f"{self.DATA_URL}/api/data/v1/get"
        params = {
            "reportName": "RPT_SHAREBONUS_DET",
            "columns": "ALL",
            # datacenter 已不支持 like 查询（9501），必须使用等号
            "filter": f'(SECUCODE="{secucode}")',
            "pageNumber": 1,
            "pageSize": 20,
            "sortColumns": "EX_DIVIDEND_DATE",
            "sortTypes": -1,
        }

        try:
            response = await self.client.get(url, params=params)
            data = response.json()
            items = data.get("result", {}).get("data", []) or []

            results = []
            for item in items:
                plan = item.get("IMPL_PLAN_PROFILE") or item.get("PLAN_EXPLAIN") or ""
                results.append({
                    "report_date": item.get("REPORT_DATE", "")[:10] if item.get("REPORT_DATE") else "",
                    "plan": plan,
                    "ex_dividend_date": item.get("EX_DIVIDEND_DATE", "")[:10] if item.get("EX_DIVIDEND_DATE") else "",
                    "register_date": item.get("EQUITY_RECORD_DATE", "")[:10] if item.get("EQUITY_RECORD_DATE") else "",
                    "progress": item.get("ASSIGN_PROGRESS", ""),
                    "bonus_ratio": item.get("BONUS_IT_RATIO"),      # 每股送股
                    "transfer_ratio": item.get("IT_RATIO"),          # 送转总计（部分股票无拆分字段）
                    "cash_dividend": item.get("PRETAX_BONUS_RMB"),   # 每股分红(税前)
                })

            return results
        except Exception:
            return []

    # ============ 投资者互动问答 ============

    async def get_interactive_qa(
        self,
        keyword: str,
        page: int = 1,
        page_size: int = 20
    ) -> Dict[str, Any]:
        """获取投资者互动问答"""
        url = "https://sns.sseinfo.com/ajax/userfeeds.do"
        params = {
            "type": "11",
            "keyword": keyword,
            "page": page,
            "pagesize": page_size,
        }

        try:
            response = await self.client.get(url, params=params)
            data = response.json()

            items = []
            for item in data.get("data", []) or []:
                items.append({
                    "question": item.get("question", ""),
                    "answer": item.get("answer", ""),
                    "stock_code": item.get("stockcode", ""),
                    "stock_name": item.get("stockname", ""),
                    "publish_time": item.get("pubtime", ""),
                })

            return {
                "items": items,
                "total": data.get("total", len(items)),
                "page": page,
                "page_size": page_size,
            }
        except Exception:
            return {"items": [], "total": 0, "page": page, "page_size": page_size}

    # ============ 概念板块排名 ============

    async def get_concept_rank(
        self,
        sort_by: str = "change_percent",
        order: str = "desc",
        limit: int = 20
    ) -> IndustryRankResponse:
        """获取概念板块排名"""
        field_map = {
            "change_percent": "f3",
            "turnover": "f8",
        }
        sort_field = field_map.get(sort_by, "f3")

        url = f"{self.BASE_URL}/api/qt/clist/get"
        params = {
            "pn": 1,
            "pz": limit,
            "po": 0 if order == "asc" else 1,
            "np": 1,
            "fltt": 2,
            "invt": 2,
            "fid": sort_field,
            "fs": "m:90+t:3",  # 概念板块
            "fields": "f2,f3,f4,f8,f12,f14,f104,f105,f128,f140,f141",
        }

        response = await self.client.get(url, params=params)
        data = response.json()

        items = []
        for item in data.get("data", {}).get("diff", []) or []:
            items.append(IndustryRank(
                bk_code=item.get("f12", ""),
                bk_name=item.get("f14", ""),
                change_percent=float(item.get("f3", 0) or 0),
                turnover=float(item.get("f8", 0) or 0),
                leader_stock_code=item.get("f140", ""),
                leader_stock_name=item.get("f128", ""),
                leader_change_percent=float(item.get("f141", 0) or 0),
                stock_count=item.get("f104", 0),
            ))

        return IndustryRankResponse(
            items=items,
            update_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )

    # ============ 财务报表 ============

    async def get_financial_report(self, stock_code: str) -> Dict[str, Any]:
        """获取股票财务报表数据"""
        _, secucode = self._to_cn_secucode(stock_code)
        if not secucode:
            return {"stock_code": stock_code, "income": [], "balance": []}

        # 获取利润表数据
        income_url = f"{self.DATA_URL}/api/data/v1/get"
        income_params = {
            "reportName": "RPT_LICO_FN_CPD",
            # REPORTDATE/TOTAL_OPERATE_INCOME/PARENT_NETPROFIT/BASIC_EPS 等字段稳定可用；使用 ALL 容易受字段变更影响
            "columns": "REPORTDATE,TOTAL_OPERATE_INCOME,PARENT_NETPROFIT,BASIC_EPS,BPS,XSMLL,YSTZ,SJLTZ,WEIGHTAVG_ROE",
            # datacenter 已不支持 like 查询（9501），必须使用等号
            "filter": f'(SECUCODE="{secucode}")',
            "pageNumber": 1,
            "pageSize": 4,
            # 2026-02：利润表使用 REPORTDATE（REPORT_DATE 不存在）
            "sortColumns": "REPORTDATE",
            "sortTypes": -1,
        }

        # 获取资产负债表
        balance_url = f"{self.DATA_URL}/api/data/v1/get"
        balance_params = {
            "reportName": "RPT_DMSK_FN_BALANCE",
            "columns": "REPORT_DATE,TOTAL_ASSETS,TOTAL_LIABILITIES,TOTAL_EQUITY",
            "filter": f'(SECUCODE="{secucode}")',
            "pageNumber": 1,
            "pageSize": 4,
            "sortColumns": "REPORT_DATE",
            "sortTypes": -1,
        }

        income_data = []
        balance_data = []

        try:
            income_resp = await self.client.get(income_url, params=income_params)
            income_json = income_resp.json()
            for item in income_json.get("result", {}).get("data", []) or []:
                income_data.append({
                    "report_date": str(item.get("REPORTDATE", "") or "")[:10],
                    "total_revenue": self._to_float(item.get("TOTAL_OPERATE_INCOME")),
                    "net_profit": self._to_float(item.get("PARENT_NETPROFIT")),
                    "basic_eps": self._to_float(item.get("BASIC_EPS")),
                    "bvps": self._to_float(item.get("BPS")),
                    # 销售毛利率/营收同比/净利同比等用于“基本面”补充展示
                    "gross_margin": self._to_float(item.get("XSMLL")),
                    "revenue_yoy": self._to_float(item.get("YSTZ")),
                    "profit_yoy": self._to_float(item.get("SJLTZ")),
                    "roe": self._to_float(item.get("WEIGHTAVG_ROE")),
                })
        except Exception:
            pass

        try:
            balance_resp = await self.client.get(balance_url, params=balance_params)
            balance_json = balance_resp.json()
            for item in balance_json.get("result", {}).get("data", []) or []:
                balance_data.append({
                    "report_date": item.get("REPORT_DATE", "")[:10],
                    "total_assets": item.get("TOTAL_ASSETS"),
                    "total_liabilities": item.get("TOTAL_LIABILITIES"),
                    "total_equity": item.get("TOTAL_EQUITY"),
                })
        except Exception:
            pass

        return {
            "stock_code": stock_code,
            "income": income_data,
            "balance": balance_data,
        }

    # ============ 行业研究报告 ============

    async def get_industry_research_reports(
        self,
        name: str = "",
        code: str = "",
        limit: int = 20
    ) -> List[Dict]:
        """获取行业研究报告"""
        url = f"{self.DATA_URL}/api/data/v1/get"
        params = {
            "reportName": "RPT_RES_INDUSTRY",
            "columns": "ALL",
            "pageSize": limit,
            "sortColumns": "PUBLISHDATE",
            "sortTypes": -1,
        }

        if name:
            params["filter"] = f'(INDUSTRY_NAME like "%{name}%")'
        elif code:
            params["filter"] = f'(INDUSTRY_CODE="{code}")'

        try:
            response = await self.client.get(url, params=params)
            data = response.json()

            results = []
            for item in data.get("result", {}).get("data", []) or []:
                results.append({
                    "title": item.get("TITLE", ""),
                    "publish_date": item.get("PUBLISHDATE", "")[:10],
                    "org_name": item.get("ORG_NAME", ""),
                    "author": item.get("AUTHOR", ""),
                    "industry_name": item.get("INDUSTRY_NAME", ""),
                    "rating": item.get("RATING", ""),
                })

            return results
        except Exception:
            return []

    # ============ 热门话题 ============

    async def get_hot_topics(self, size: int = 20) -> List[Dict]:
        """获取热门话题"""
        url = "https://guba.eastmoney.com/minihq/api/public/news/gethotlist"
        params = {
            "type": "1",
            "ps": size,
        }

        try:
            response = await self.client.get(url, params=params)
            data = response.json()

            results = []
            for item in data.get("data", {}).get("list", []) or []:
                results.append({
                    "id": str(item.get("id", "")),
                    "title": item.get("title", ""),
                    "hot_score": item.get("count", 0),
                    "change_count": item.get("change", 0),
                    "create_time": item.get("create_time"),
                })

            return results
        except Exception:
            return []

    # ============ 热门事件 ============

    async def get_hot_events(self, size: int = 20) -> List[Dict]:
        """获取热门事件"""
        url = "https://data.eastmoney.com/dataapi/event/getEventList"
        params = {
            "type": "1",
            "pageSize": size,
            "pageNo": 1,
        }

        try:
            response = await self.client.get(url, params=params)
            data = response.json()

            results = []
            for item in data.get("data", []) or []:
                results.append({
                    "id": str(item.get("eventId", "")),
                    "title": item.get("eventName", ""),
                    "description": item.get("eventDesc", ""),
                    "event_type": item.get("eventType", ""),
                    "create_time": item.get("updateTime"),
                })

            return results
        except Exception:
            return []

    # ============ 投资日历 ============

    async def get_invest_calendar(self, year_month: str) -> List[Dict]:
        """获取投资日历"""
        url = f"{self.DATA_URL}/api/data/v1/get"
        params = {
            "reportName": "RPT_ECONOMIC_CALENDAR",
            "columns": "ALL",
            "filter": f'(DATETIME like "{year_month}%")',
            "pageSize": 100,
            "sortColumns": "DATETIME",
            "sortTypes": 1,
        }

        try:
            response = await self.client.get(url, params=params)
            data = response.json()

            results = []
            for item in data.get("result", {}).get("data", []) or []:
                results.append({
                    "date": item.get("DATETIME", "")[:10],
                    "event": item.get("EVENT_NAME", ""),
                    "importance": item.get("IMPORTANCE", ""),
                    "country": item.get("COUNTRY", ""),
                    "actual": item.get("ACTUAL"),
                    "forecast": item.get("FORECAST"),
                    "previous": item.get("PREVIOUS"),
                })

            return results
        except Exception:
            return []

    # ============ 北向资金 ============

    async def get_north_flow(self, days: int = 30) -> Dict:
        """获取北向资金数据"""
        # 2026-02-02：RPT_MUTUAL_QUOTA 返回的是“额度状态/开闭市原因”，不含净流入数据
        # 改用 push2 的 kamt/get（同源于东财“港股通/沪深港通”页面）
        url = f"{self.BASE_URL}/api/qt/kamt/get"
        params = {
            "fields1": "f1,f3",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60",
        }

        def _to_yuan_from_wan(val: Any) -> float:
            try:
                # kamt/get 口径通常以“万元”为单位，统一转为“元”便于前端 formatMoney 展示（亿/万）
                return float(val or 0) * 10000.0
            except (ValueError, TypeError):
                return 0.0

        metric = "成交净买额"
        unit = "元"

        push2_current: Optional[Dict[str, Any]] = None
        push2_error: Optional[Exception] = None

        # 1) 优先尝试 push2 获取“当日”数据（可能更及时）
        try:
            response = await self.client.get(url, params=params)
            data = response.json() or {}

            payload = data.get("data") or {}
            if not isinstance(payload, dict):
                payload = {}

            hk2sh = payload.get("hk2sh") or {}
            hk2sz = payload.get("hk2sz") or {}

            date = (hk2sh.get("date2") or hk2sz.get("date2") or "")  # YYYY-MM-DD
            if date:
                sh_in = _to_yuan_from_wan(hk2sh.get("dayNetAmtIn"))
                sz_in = _to_yuan_from_wan(hk2sz.get("dayNetAmtIn"))
                push2_current = {
                    "date": date,
                    "sh_inflow": sh_in,
                    "sz_inflow": sz_in,
                    "total_inflow": sh_in + sz_in,
                    # 使用“当日剩余额度”作为余额口径（同样转为元）
                    "sh_balance": _to_yuan_from_wan(hk2sh.get("dayAmtRemain")),
                    "sz_balance": _to_yuan_from_wan(hk2sz.get("dayAmtRemain")),
                }
        except Exception as e:
            push2_error = e
            logger.warning(f"获取北向资金失败（push2），将尝试数据中心兜底: {e}")

        # 2) days<=1：仅返回 current（可直接用 push2；失败则走数据中心）
        if int(days) <= 1:
            if push2_current:
                return {
                    "metric": metric,
                    "unit": unit,
                    "source": "eastmoney_push2",
                    "asof_date": push2_current.get("date", "") or "",
                    "current": push2_current,
                    "history": [],
                }
            try:
                dc = await self._get_north_flow_from_datacenter(days=1)
                return {
                    "metric": metric,
                    "unit": unit,
                    "source": "eastmoney_datacenter",
                    "asof_date": (dc.get("current") or {}).get("date", "") if isinstance(dc, dict) else "",
                    **dc,
                }
            except Exception as e:
                logger.error(f"北向资金数据中心兜底失败: {e}")
                return {"metric": metric, "unit": unit, "source": "unavailable", "asof_date": "", "current": None, "history": []}

        # 3) days>1：返回 history（用数据中心），current 优先 push2（若存在）
        history_payload: Dict[str, Any] = {"current": None, "history": []}
        try:
            history_payload = await self._get_north_flow_from_datacenter(days=days)
        except Exception as e:
            logger.error(f"北向资金数据中心兜底失败: {e}")

        history = history_payload.get("history") if isinstance(history_payload, dict) else []
        dc_current = history_payload.get("current") if isinstance(history_payload, dict) else None

        used_push2_as_current = False

        # 仅当数据中心历史中不存在该日期时，才把 push2 结果插入到 history（避免用 0 覆盖数据中心的有效数据）
        if push2_current and push2_current.get("date"):
            date_str = str(push2_current.get("date"))
            exists_in_history = any(
                isinstance(h, dict) and h.get("date") == date_str for h in (history or [])
            )
            if exists_in_history:
                # 若同日已存在数据中心记录，仅把“额度余额”等补充字段同步过去（不覆盖净买额）
                for h in history or []:
                    if isinstance(h, dict) and h.get("date") == date_str:
                        h["sh_balance"] = float(push2_current.get("sh_balance", 0.0) or 0.0)
                        h["sz_balance"] = float(push2_current.get("sz_balance", 0.0) or 0.0)
                        break
            else:
                history = [push2_current] + list(history or [])
                used_push2_as_current = True

        # current 优先取 history 的首条（已经是最新日期）；若 history 为空再回退
        current = (history[0] if isinstance(history, list) and history else None) or push2_current or dc_current

        source = "eastmoney_datacenter"
        if used_push2_as_current and history_payload.get("history"):
            source = "eastmoney_push2+datacenter"
        elif used_push2_as_current:
            source = "eastmoney_push2"

        return {
            "metric": metric,
            "unit": unit,
            "source": source,
            "asof_date": (current or {}).get("date", "") if isinstance(current, dict) else "",
            "current": current,
            "history": history or [],
        }

    async def _get_north_flow_from_datacenter(self, days: int = 30) -> Dict[str, Any]:
        """
        北向资金兜底：使用数据中心报表 RPT_MUTUAL_DEAL_HISTORY 获取“成交净买额”。

        说明：
        - 该报表同时包含“成交额/净买额/合计”等多组 MUTUAL_TYPE。
          实测在 2026 年附近，净买额对应的 MUTUAL_TYPE 为：
          - 沪股通净买额：002
          - 深股通净买额：004
          - 北向合计净买额：006（通常约等于 002 + 004）
          旧组（001/003/005）在部分时段会出现净买额字段为空，因此这里做动态选择兜底。
        - 字段单位为“百万元”（与页面展示口径一致），这里统一转为“元”供前端 formatMoneyYuan 使用。
        - QUOTA_BALANCE 在部分时段为文本/空值，前端未展示余额字段，这里返回 0 避免校验失败。
        """
        url = f"{self.DATA_URL}/api/data/v1/get"
        target_days = max(1, int(days))

        # 过滤只取必要的 MUTUAL_TYPE，减少带宽与解析成本
        wanted_types = ("001", "002", "003", "004", "005", "006")

        # 每个交易日最多 6 行，取 300 行基本覆盖 50 个交易日；再按需翻页凑够 target_days
        page_size = min(1000, max(120, target_days * 6 + 30))

        # 按日期聚合（保留接口返回顺序：默认按日期倒序）
        date_map: Dict[str, Dict[str, Any]] = {}
        date_order: List[str] = []

        def _ensure(date_str: str) -> Dict[str, Any]:
            if date_str not in date_map:
                date_map[date_str] = {"date": date_str, "values": {}}
                date_order.append(date_str)
            return date_map[date_str]

        def _to_yuan_from_million(val: Any) -> Optional[float]:
            try:
                if val is None or val == "":
                    return None
                # 数据中心该字段口径为“百万元”，转为“元”
                return float(val) * 1_000_000.0
            except (ValueError, TypeError):
                return None

        def _pick_group(values: Dict[str, Optional[float]]) -> tuple[Optional[float], Optional[float], Optional[float]]:
            # 优先使用 002/004/006（净买额），其次 001/003/005（旧组）
            new_group = ("002", "004", "006")
            old_group = ("001", "003", "005")

            if any(values.get(k) is not None for k in new_group):
                return values.get("002"), values.get("004"), values.get("006")
            if any(values.get(k) is not None for k in old_group):
                return values.get("001"), values.get("003"), values.get("005")
            return None, None, None

        def _valid_date_count() -> int:
            cnt = 0
            for d in date_order:
                values = (date_map.get(d) or {}).get("values") or {}
                sh, sz, total = _pick_group(values)
                if sh is None and sz is None and total is None:
                    continue
                cnt += 1
                if cnt >= target_days:
                    break
            return cnt

        page_number = 1
        total_pages: Optional[int] = None
        # 无 pages 信息时的保护上限：避免出现“数据源返回重复页/缺失 pages 字段”导致死循环
        estimated_pages = int(math.ceil((target_days * 6) / page_size)) if page_size > 0 else 1
        max_pages = min(20, max(3, estimated_pages + 3))

        while True:
            before_dates = len(date_order)
            before_valid = _valid_date_count()
            params = {
                "reportName": "RPT_MUTUAL_DEAL_HISTORY",
                "columns": "MUTUAL_TYPE,TRADE_DATE,NET_DEAL_AMT,BUY_AMT,SELL_AMT",
                "filter": '(MUTUAL_TYPE in ("001","002","003","004","005","006"))',
                "pageNumber": page_number,
                "pageSize": page_size,
                "sortColumns": "TRADE_DATE",
                "sortTypes": "-1",
                "source": "WEB",
                "client": "WEB",
            }

            resp = await self.client.get(url, params=params)
            payload = resp.json() or {}
            result = payload.get("result") or {}
            rows = result.get("data") or []
            if total_pages is None:
                try:
                    total_pages = int(result.get("pages") or 0) or None
                except Exception:
                    total_pages = None

            if not rows:
                break

            for row in rows or []:
                trade_date = str(row.get("TRADE_DATE", "") or "")
                date_str = trade_date[:10]
                if not date_str:
                    continue

                mutual_type = str(row.get("MUTUAL_TYPE", "") or "")
                if mutual_type not in wanted_types:
                    continue

                info = _ensure(date_str)
                values = info.get("values") or {}

                # 优先使用 NET_DEAL_AMT；若缺失但 BUY/SELL 有值则计算差额
                amt = _to_yuan_from_million(row.get("NET_DEAL_AMT"))
                if amt is None:
                    buy = _to_yuan_from_million(row.get("BUY_AMT"))
                    sell = _to_yuan_from_million(row.get("SELL_AMT"))
                    if buy is not None and sell is not None:
                        amt = buy - sell

                values[mutual_type] = amt
                info["values"] = values

            after_valid = _valid_date_count()
            if after_valid >= target_days:
                break

            if total_pages is not None and page_number >= total_pages:
                break

            # 保护：若多次翻页无任何进展，则停止（避免服务端 pages 缺失/重复页导致死循环）
            if after_valid == before_valid and len(date_order) == before_dates:
                break

            if page_number >= max_pages:
                break

            page_number += 1

        history: List[Dict[str, Any]] = []
        for date_str in date_order:
            if len(history) >= target_days:
                break

            info = date_map.get(date_str) or {}
            values = info.get("values") or {}
            sh, sz, total = _pick_group(values)
            if sh is None and sz is None and total is None:
                continue

            sh_in = float(sh or 0.0)
            sz_in = float(sz or 0.0)
            total_in = float(total) if total is not None else sh_in + sz_in

            history.append({
                "date": date_str,
                "sh_inflow": sh_in,
                "sz_inflow": sz_in,
                "total_inflow": total_in,
                "sh_balance": 0.0,
                "sz_balance": 0.0,
            })

        current = history[0] if history else None
        return {"current": current, "history": history}

    # ============ 板块字典 ============

    async def get_bk_dict(self, bk_type: str = "all") -> List[Dict]:
        """
        获取板块字典
        bk_type: all/industry/concept/area
        """
        results = []

        # 行业板块
        if bk_type in ("all", "industry"):
            url = f"{self.QUOTE_URL}/api/qt/clist/get"
            params = {
                "pn": 1,
                "pz": 500,
                "fs": "m:90+t:2",  # 行业板块
                "fields": "f12,f14",
            }
            try:
                response = await self.client.get(url, params=params)
                data = response.json()
                for item in data.get("data", {}).get("diff", []) or []:
                    results.append({
                        "code": item.get("f12", ""),
                        "name": item.get("f14", ""),
                        "type": "industry",
                    })
            except Exception:
                pass

        # 概念板块
        if bk_type in ("all", "concept"):
            url = f"{self.QUOTE_URL}/api/qt/clist/get"
            params = {
                "pn": 1,
                "pz": 500,
                "fs": "m:90+t:3",  # 概念板块
                "fields": "f12,f14",
            }
            try:
                response = await self.client.get(url, params=params)
                data = response.json()
                for item in data.get("data", {}).get("diff", []) or []:
                    results.append({
                        "code": item.get("f12", ""),
                        "name": item.get("f14", ""),
                        "type": "concept",
                    })
            except Exception:
                pass

        # 地域板块
        if bk_type in ("all", "area"):
            url = f"{self.QUOTE_URL}/api/qt/clist/get"
            params = {
                "pn": 1,
                "pz": 100,
                "fs": "m:90+t:1",  # 地域板块
                "fields": "f12,f14",
            }
            try:
                response = await self.client.get(url, params=params)
                data = response.json()
                for item in data.get("data", {}).get("diff", []) or []:
                    results.append({
                        "code": item.get("f12", ""),
                        "name": item.get("f14", ""),
                        "type": "area",
                    })
            except Exception:
                pass

        return results
