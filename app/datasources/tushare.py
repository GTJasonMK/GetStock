# Tushare 数据源客户端
"""
Tushare Pro 数据接口
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta

import httpx


class TushareClient:
    """Tushare客户端"""

    BASE_URL = "https://api.tushare.pro"

    def __init__(self, token: str = ""):
        self.token = token
        self.client = httpx.AsyncClient(timeout=30.0)

    async def close(self):
        await self.client.aclose()

    async def _request(self, api_name: str, params: Dict = None, fields: str = "") -> Dict:
        """发送API请求"""
        if not self.token:
            return {"code": -1, "msg": "Tushare token未配置"}

        payload = {
            "api_name": api_name,
            "token": self.token,
            "params": params or {},
            "fields": fields,
        }

        response = await self.client.post(self.BASE_URL, json=payload)
        return response.json()

    # ============ 股票基础信息 ============

    async def get_stock_basic(
        self,
        exchange: str = "",
        list_status: str = "L"
    ) -> List[Dict]:
        """
        获取股票基础信息
        exchange: SSE(上交所)/SZSE(深交所)/BSE(北交所)
        list_status: L(上市)/D(退市)/P(暂停上市)
        """
        params = {"list_status": list_status}
        if exchange:
            params["exchange"] = exchange

        result = await self._request(
            "stock_basic",
            params,
            "ts_code,symbol,name,area,industry,market,list_date,exchange"
        )

        if result.get("code") != 0:
            return []

        items = result.get("data", {}).get("items", [])
        fields = result.get("data", {}).get("fields", [])

        return [dict(zip(fields, item)) for item in items]

    async def get_index_basic(self, market: str = "SSE") -> List[Dict]:
        """
        获取指数基础信息
        market: SSE(上交所)/SZSE(深交所)/CSI(中证)
        """
        result = await self._request(
            "index_basic",
            {"market": market},
            "ts_code,name,fullname,market,publisher,base_date,base_point"
        )

        if result.get("code") != 0:
            return []

        items = result.get("data", {}).get("items", [])
        fields = result.get("data", {}).get("fields", [])

        return [dict(zip(fields, item)) for item in items]

    # ============ 日线行情 ============

    async def get_daily(
        self,
        ts_code: str = "",
        trade_date: str = "",
        start_date: str = "",
        end_date: str = ""
    ) -> List[Dict]:
        """
        获取A股日线行情
        ts_code: 股票代码 (如 000001.SZ)
        trade_date: 交易日期 (YYYYMMDD)
        """
        params = {}
        if ts_code:
            params["ts_code"] = ts_code
        if trade_date:
            params["trade_date"] = trade_date
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date

        result = await self._request(
            "daily",
            params,
            "ts_code,trade_date,open,high,low,close,pre_close,change,pct_chg,vol,amount"
        )

        if result.get("code") != 0:
            return []

        items = result.get("data", {}).get("items", [])
        fields = result.get("data", {}).get("fields", [])

        return [dict(zip(fields, item)) for item in items]

    async def get_hk_daily(
        self,
        ts_code: str = "",
        trade_date: str = "",
        start_date: str = "",
        end_date: str = ""
    ) -> List[Dict]:
        """获取港股日线行情"""
        params = {}
        if ts_code:
            params["ts_code"] = ts_code
        if trade_date:
            params["trade_date"] = trade_date
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date

        result = await self._request(
            "hk_daily",
            params,
            "ts_code,trade_date,open,high,low,close,pre_close,change,pct_chg,vol,amount"
        )

        if result.get("code") != 0:
            return []

        items = result.get("data", {}).get("items", [])
        fields = result.get("data", {}).get("fields", [])

        return [dict(zip(fields, item)) for item in items]

    async def get_us_daily(
        self,
        ts_code: str = "",
        trade_date: str = "",
        start_date: str = "",
        end_date: str = ""
    ) -> List[Dict]:
        """获取美股日线行情"""
        params = {}
        if ts_code:
            params["ts_code"] = ts_code
        if trade_date:
            params["trade_date"] = trade_date
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date

        result = await self._request(
            "us_daily",
            params,
            "ts_code,trade_date,open,high,low,close,pre_close,change,pct_chg,vol,amount"
        )

        if result.get("code") != 0:
            return []

        items = result.get("data", {}).get("items", [])
        fields = result.get("data", {}).get("fields", [])

        return [dict(zip(fields, item)) for item in items]

    # ============ 复权因子 ============

    async def get_adj_factor(
        self,
        ts_code: str,
        start_date: str = "",
        end_date: str = ""
    ) -> List[Dict]:
        """获取复权因子"""
        params = {"ts_code": ts_code}
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date

        result = await self._request(
            "adj_factor",
            params,
            "ts_code,trade_date,adj_factor"
        )

        if result.get("code") != 0:
            return []

        items = result.get("data", {}).get("items", [])
        fields = result.get("data", {}).get("fields", [])

        return [dict(zip(fields, item)) for item in items]

    # ============ 财务数据 ============

    async def get_income(
        self,
        ts_code: str,
        period: str = ""
    ) -> List[Dict]:
        """获取利润表"""
        params = {"ts_code": ts_code}
        if period:
            params["period"] = period

        result = await self._request(
            "income",
            params,
            "ts_code,ann_date,f_ann_date,end_date,report_type,comp_type,basic_eps,diluted_eps,total_revenue,revenue,total_cogs,oper_cost,total_profit,n_income"
        )

        if result.get("code") != 0:
            return []

        items = result.get("data", {}).get("items", [])
        fields = result.get("data", {}).get("fields", [])

        return [dict(zip(fields, item)) for item in items]

    async def get_balancesheet(
        self,
        ts_code: str,
        period: str = ""
    ) -> List[Dict]:
        """获取资产负债表"""
        params = {"ts_code": ts_code}
        if period:
            params["period"] = period

        result = await self._request(
            "balancesheet",
            params,
            "ts_code,ann_date,f_ann_date,end_date,report_type,comp_type,total_assets,total_liab,total_hldr_eqy_exc_min_int"
        )

        if result.get("code") != 0:
            return []

        items = result.get("data", {}).get("items", [])
        fields = result.get("data", {}).get("fields", [])

        return [dict(zip(fields, item)) for item in items]

    # ============ 技术指标 ============

    async def get_daily_basic(
        self,
        ts_code: str = "",
        trade_date: str = ""
    ) -> List[Dict]:
        """
        获取每日指标
        包含市盈率、市净率、换手率等
        """
        params = {}
        if ts_code:
            params["ts_code"] = ts_code
        if trade_date:
            params["trade_date"] = trade_date

        result = await self._request(
            "daily_basic",
            params,
            "ts_code,trade_date,close,turnover_rate,turnover_rate_f,volume_ratio,pe,pe_ttm,pb,ps,ps_ttm,dv_ratio,dv_ttm,total_share,float_share,free_share,total_mv,circ_mv"
        )

        if result.get("code") != 0:
            return []

        items = result.get("data", {}).get("items", [])
        fields = result.get("data", {}).get("fields", [])

        return [dict(zip(fields, item)) for item in items]

    # ============ 龙虎榜 ============

    async def get_top_list(self, trade_date: str) -> List[Dict]:
        """获取龙虎榜数据"""
        result = await self._request(
            "top_list",
            {"trade_date": trade_date},
            "trade_date,ts_code,name,close,pct_change,turnover_rate,amount,l_sell,l_buy,l_amount,net_amount,net_rate,amount_rate,float_values,reason"
        )

        if result.get("code") != 0:
            return []

        items = result.get("data", {}).get("items", [])
        fields = result.get("data", {}).get("fields", [])

        return [dict(zip(fields, item)) for item in items]

    # ============ 资金流向 ============

    async def get_moneyflow(
        self,
        ts_code: str = "",
        trade_date: str = ""
    ) -> List[Dict]:
        """获取个股资金流向"""
        params = {}
        if ts_code:
            params["ts_code"] = ts_code
        if trade_date:
            params["trade_date"] = trade_date

        result = await self._request(
            "moneyflow",
            params,
            "ts_code,trade_date,buy_sm_vol,buy_sm_amount,sell_sm_vol,sell_sm_amount,buy_md_vol,buy_md_amount,sell_md_vol,sell_md_amount,buy_lg_vol,buy_lg_amount,sell_lg_vol,sell_lg_amount,buy_elg_vol,buy_elg_amount,sell_elg_vol,sell_elg_amount,net_mf_vol,net_mf_amount"
        )

        if result.get("code") != 0:
            return []

        items = result.get("data", {}).get("items", [])
        fields = result.get("data", {}).get("fields", [])

        return [dict(zip(fields, item)) for item in items]

    # ============ 工具方法 ============

    @staticmethod
    def convert_code(stock_code: str) -> str:
        """
        转换股票代码格式
        sh600000 -> 600000.SH
        sz000001 -> 000001.SZ
        """
        if stock_code.startswith("sh"):
            return f"{stock_code[2:]}.SH"
        elif stock_code.startswith("sz"):
            return f"{stock_code[2:]}.SZ"
        elif stock_code.startswith("hk"):
            return f"{stock_code[2:]}.HK"
        elif "." in stock_code:
            return stock_code
        else:
            # 自动判断
            if stock_code.startswith("6"):
                return f"{stock_code}.SH"
            else:
                return f"{stock_code}.SZ"

    @staticmethod
    def reverse_code(ts_code: str) -> str:
        """
        反向转换股票代码
        600000.SH -> sh600000
        """
        if "." not in ts_code:
            return ts_code

        code, market = ts_code.split(".")
        if market == "SH":
            return f"sh{code}"
        elif market == "SZ":
            return f"sz{code}"
        elif market == "HK":
            return f"hk{code}"
        return ts_code
