# Fund 数据源客户端
"""
天天基金数据接口
"""

from typing import List, Optional
import re

import httpx

from app.schemas.fund import (
    FundSearchResult,
    FundSearchResponse,
    FundDetail,
    FundNetValueHistory,
    FundNetValueResponse,
)


class TianTianFundClient:
    """天天基金客户端"""

    BASE_URL = "https://fundsuggest.eastmoney.com"
    DETAIL_URL = "https://fundgz.1234567.com.cn"

    def __init__(self):
        self.client = httpx.AsyncClient(
            timeout=30.0,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://fund.eastmoney.com/",
            }
        )

    async def close(self):
        await self.client.aclose()

    async def search_funds(
        self,
        keyword: str,
        fund_type: Optional[str] = None,
        limit: int = 20
    ) -> FundSearchResponse:
        """搜索基金"""
        url = f"{self.BASE_URL}/FundSearch/api/FundSearchAPI.ashx"
        params = {
            "m": "1",
            "key": keyword,
            "pageindex": 0,
            "pagesize": limit,
        }

        response = await self.client.get(url, params=params)
        data = response.json()

        results = []
        for item in data.get("Datas", []) or []:
            # 基金类型过滤
            item_type = item.get("FundType", "")
            if fund_type and fund_type not in item_type:
                continue

            results.append(FundSearchResult(
                fund_code=item.get("CODE", ""),
                fund_name=item.get("NAME", ""),
                fund_type=item_type,
                company=item.get("JJGSNAME", ""),
            ))

        return FundSearchResponse(results=results[:limit], total=len(results))

    async def get_fund_detail(self, fund_code: str) -> Optional[FundDetail]:
        """获取基金详情"""
        # 获取基金基本信息
        url = f"https://fund.eastmoney.com/pingzhongdata/{fund_code}.js"
        response = await self.client.get(url)
        content = response.text

        # 解析JavaScript变量
        def extract_var(name: str, content: str):
            match = re.search(rf'var {name}\s*=\s*"?([^";]+)"?;', content)
            return match.group(1) if match else ""

        def extract_array(name: str, content: str):
            match = re.search(rf'var {name}\s*=\s*(\[.*?\]);', content, re.DOTALL)
            if match:
                import json
                try:
                    return json.loads(match.group(1))
                except:
                    return []
            return []

        fund_name = extract_var("fS_name", content)
        fund_code_parsed = extract_var("fS_code", content)

        if not fund_name:
            return None

        # 获取净值数据
        net_value_data = extract_array("Data_netWorthTrend", content)
        latest_nv = net_value_data[-1] if net_value_data else {}

        # 获取收益数据
        growth_data = extract_array("syl_1n", content)

        return FundDetail(
            fund_code=fund_code,
            name=fund_name,
            short_name=fund_name,
            fund_type="",
            establish_date="",
            company="",
            manager="",
            fund_scale=0,
            net_value=float(latest_nv.get("y", 0)) if latest_nv else 0,
            total_value=0,
            day_growth=float(latest_nv.get("equityReturn", 0)) if latest_nv else 0,
        )

    async def get_fund_net_value(
        self,
        fund_code: str,
        days: int = 30
    ) -> FundNetValueResponse:
        """获取基金净值历史"""
        url = f"https://fund.eastmoney.com/pingzhongdata/{fund_code}.js"
        response = await self.client.get(url)
        content = response.text

        # 解析净值数据
        match = re.search(r'var Data_netWorthTrend\s*=\s*(\[.*?\]);', content, re.DOTALL)
        data_list = []
        if match:
            import json
            try:
                data_list = json.loads(match.group(1))
            except:
                pass

        # 取最近N天
        data_list = data_list[-days:] if len(data_list) > days else data_list

        history = []
        for item in data_list:
            from datetime import datetime
            timestamp = item.get("x", 0) / 1000
            history.append(FundNetValueHistory(
                date=datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d"),
                net_value=float(item.get("y", 0)),
                total_value=float(item.get("y", 0)),  # 暂用单位净值
                day_growth=float(item.get("equityReturn", 0)),
            ))

        # 获取基金名称
        name_match = re.search(r'var fS_name\s*=\s*"([^"]+)";', content)
        fund_name = name_match.group(1) if name_match else ""

        return FundNetValueResponse(
            fund_code=fund_code,
            fund_name=fund_name,
            data=history,
        )
