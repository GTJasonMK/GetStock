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

    async def _get_datasource_manager(self):
        """获取数据源管理器（按 DB 配置初始化）。"""
        from app.datasources.manager import get_datasource_manager

        manager = get_datasource_manager()
        await manager.initialize(self.db)
        return manager

    async def search_funds(
        self,
        keyword: str,
        fund_type: Optional[str] = None,
        limit: int = 20
    ) -> FundSearchResponse:
        """搜索基金"""
        manager = await self._get_datasource_manager()
        return await manager.search_funds(keyword, fund_type, limit)

    async def get_fund_detail(self, fund_code: str) -> Optional[FundDetail]:
        """获取基金详情"""
        manager = await self._get_datasource_manager()
        return await manager.get_fund_detail(fund_code)

    async def get_fund_net_value(
        self,
        fund_code: str,
        days: int = 30
    ) -> FundNetValueResponse:
        """获取基金净值历史"""
        manager = await self._get_datasource_manager()
        return await manager.get_fund_net_value(fund_code, days)
