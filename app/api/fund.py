# Fund API
"""
基金数据API路由
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.fund import FollowedFund
from app.schemas.fund import (
    FollowedFundCreate,
    FollowedFundUpdate,
    FollowedFundResponse,
    FundSearchResponse,
    FundDetail,
    FundNetValueResponse,
)
from app.schemas.common import Response

router = APIRouter()


# ============ Followed Funds API ============

@router.get("/follow", response_model=Response[List[FollowedFundResponse]])
async def get_followed_funds(db: AsyncSession = Depends(get_db)):
    """获取关注的基金列表"""
    result = await db.execute(
        select(FollowedFund).order_by(FollowedFund.sort_order, FollowedFund.id)
    )
    funds = result.scalars().all()
    return Response(data=[FollowedFundResponse.model_validate(f) for f in funds])


@router.post("/follow", response_model=Response[FollowedFundResponse])
async def add_followed_fund(
    data: FollowedFundCreate,
    db: AsyncSession = Depends(get_db)
):
    """添加关注基金"""
    # 检查是否已存在
    result = await db.execute(
        select(FollowedFund).where(FollowedFund.fund_code == data.fund_code)
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="基金已在关注列表中")

    fund = FollowedFund(**data.model_dump())
    db.add(fund)
    await db.commit()
    await db.refresh(fund)

    return Response(data=FollowedFundResponse.model_validate(fund))


@router.put("/follow/{fund_code}", response_model=Response[FollowedFundResponse])
async def update_followed_fund(
    fund_code: str,
    data: FollowedFundUpdate,
    db: AsyncSession = Depends(get_db)
):
    """更新关注基金"""
    result = await db.execute(
        select(FollowedFund).where(FollowedFund.fund_code == fund_code)
    )
    fund = result.scalar_one_or_none()

    if not fund:
        raise HTTPException(status_code=404, detail="关注基金不存在")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(fund, key, value)

    await db.commit()
    await db.refresh(fund)

    return Response(data=FollowedFundResponse.model_validate(fund))


@router.delete("/follow/{fund_code}", response_model=Response)
async def delete_followed_fund(
    fund_code: str,
    db: AsyncSession = Depends(get_db)
):
    """取消关注基金"""
    result = await db.execute(
        select(FollowedFund).where(FollowedFund.fund_code == fund_code)
    )
    fund = result.scalar_one_or_none()

    if not fund:
        raise HTTPException(status_code=404, detail="关注基金不存在")

    await db.delete(fund)
    await db.commit()

    return Response(message="删除成功")


# ============ Fund Search API ============

@router.get("/list", response_model=Response[FundSearchResponse])
async def search_funds(
    keyword: str = Query(..., min_length=1),
    fund_type: Optional[str] = Query(None, description="基金类型"),
    limit: int = Query(20, le=100),
    db: AsyncSession = Depends(get_db)
):
    """搜索基金"""
    from app.services.fund_service import FundService

    service = FundService(db)
    results = await service.search_funds(keyword, fund_type, limit)

    return Response(data=results)


# ============ Fund Detail API ============

@router.get("/{fund_code}", response_model=Response[FundDetail])
async def get_fund_detail(
    fund_code: str,
    db: AsyncSession = Depends(get_db)
):
    """获取基金详情"""
    from app.services.fund_service import FundService

    service = FundService(db)
    detail = await service.get_fund_detail(fund_code)

    if not detail:
        raise HTTPException(status_code=404, detail="基金不存在")

    return Response(data=detail)


@router.get("/{fund_code}/net-value", response_model=Response[FundNetValueResponse])
async def get_fund_net_value(
    fund_code: str,
    days: int = Query(30, le=365),
    db: AsyncSession = Depends(get_db)
):
    """获取基金净值历史"""
    from app.services.fund_service import FundService

    service = FundService(db)
    data = await service.get_fund_net_value(fund_code, days)

    return Response(data=data)
