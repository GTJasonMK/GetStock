# Fund Service
"""
基金服务
"""

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.fund import FundSearchResponse, FundDetail, FundNetValueResponse


class FundService:
    """基金服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def search_funds(
        self,
        keyword: str,
        fund_type: Optional[str] = None,
        limit: int = 20
    ) -> FundSearchResponse:
        """搜索基金"""
        from app.datasources.fund import TianTianFundClient

        client = TianTianFundClient()
        try:
            results = await client.search_funds(keyword, fund_type, limit)
            return results
        finally:
            await client.close()

    async def get_fund_detail(self, fund_code: str) -> Optional[FundDetail]:
        """获取基金详情"""
        from app.datasources.fund import TianTianFundClient

        client = TianTianFundClient()
        try:
            detail = await client.get_fund_detail(fund_code)
            return detail
        finally:
            await client.close()

    async def get_fund_net_value(
        self,
        fund_code: str,
        days: int = 30
    ) -> FundNetValueResponse:
        """获取基金净值历史"""
        from app.datasources.fund import TianTianFundClient

        client = TianTianFundClient()
        try:
            data = await client.get_fund_net_value(fund_code, days)
            return data
        finally:
            await client.close()
