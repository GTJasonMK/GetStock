# Group API
"""
分组管理API路由
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.stock import Group, GroupStock
from app.utils.helpers import normalize_stock_code
from app.schemas.stock import (
    GroupCreate,
    GroupUpdate,
    GroupResponse,
    GroupStockItem,
)
from app.schemas.common import Response

router = APIRouter()


@router.get("", response_model=Response[List[GroupResponse]])
async def get_groups(db: AsyncSession = Depends(get_db)):
    """获取所有分组"""
    result = await db.execute(select(Group).order_by(Group.sort_order, Group.id))
    groups = result.scalars().all()

    response_list = []
    for group in groups:
        # 获取分组中的股票
        stock_result = await db.execute(
            select(GroupStock)
            .where(GroupStock.group_id == group.id)
            .order_by(GroupStock.sort_order)
        )
        stocks = stock_result.scalars().all()

        group_dict = {
            "id": group.id,
            "created_at": group.created_at,
            "updated_at": group.updated_at,
            "name": group.name,
            "description": group.description,
            "sort_order": group.sort_order,
            "stocks": [
                GroupStockItem(stock_code=s.stock_code, sort_order=s.sort_order)
                for s in stocks
            ],
        }
        response_list.append(GroupResponse(**group_dict))

    return Response(data=response_list)


@router.post("", response_model=Response[GroupResponse])
async def create_group(
    data: GroupCreate,
    db: AsyncSession = Depends(get_db)
):
    """创建分组"""
    # 检查名称是否重复
    result = await db.execute(select(Group).where(Group.name == data.name))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="分组名称已存在")

    group = Group(**data.model_dump())
    db.add(group)
    await db.commit()
    await db.refresh(group)

    return Response(data=GroupResponse(
        id=group.id,
        created_at=group.created_at,
        updated_at=group.updated_at,
        name=group.name,
        description=group.description,
        sort_order=group.sort_order,
        stocks=[],
    ))


@router.put("/{group_id}", response_model=Response[GroupResponse])
async def update_group(
    group_id: int,
    data: GroupUpdate,
    db: AsyncSession = Depends(get_db)
):
    """更新分组"""
    result = await db.execute(select(Group).where(Group.id == group_id))
    group = result.scalar_one_or_none()

    if not group:
        raise HTTPException(status_code=404, detail="分组不存在")

    # 检查名称是否重复
    if data.name and data.name != group.name:
        name_result = await db.execute(select(Group).where(Group.name == data.name))
        if name_result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="分组名称已存在")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(group, key, value)

    await db.commit()
    await db.refresh(group)

    # 获取分组中的股票
    stock_result = await db.execute(
        select(GroupStock).where(GroupStock.group_id == group.id)
    )
    stocks = stock_result.scalars().all()

    return Response(data=GroupResponse(
        id=group.id,
        created_at=group.created_at,
        updated_at=group.updated_at,
        name=group.name,
        description=group.description,
        sort_order=group.sort_order,
        stocks=[
            GroupStockItem(stock_code=s.stock_code, sort_order=s.sort_order)
            for s in stocks
        ],
    ))


@router.delete("/{group_id}", response_model=Response)
async def delete_group(
    group_id: int,
    db: AsyncSession = Depends(get_db)
):
    """删除分组"""
    result = await db.execute(select(Group).where(Group.id == group_id))
    group = result.scalar_one_or_none()

    if not group:
        raise HTTPException(status_code=404, detail="分组不存在")

    # 删除关联的股票
    from sqlalchemy import delete
    await db.execute(
        delete(GroupStock).where(GroupStock.group_id == group_id)
    )

    await db.delete(group)
    await db.commit()

    return Response(message="删除成功")


@router.post("/{group_id}/stock", response_model=Response)
async def add_stock_to_group(
    group_id: int,
    stock_code: str,
    db: AsyncSession = Depends(get_db)
):
    """添加股票到分组"""
    stock_code = normalize_stock_code(stock_code)
    if not stock_code:
        raise HTTPException(status_code=400, detail="股票代码不能为空")

    # 检查分组是否存在
    result = await db.execute(select(Group).where(Group.id == group_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="分组不存在")

    # 检查是否已在分组中
    stock_result = await db.execute(
        select(GroupStock).where(
            GroupStock.group_id == group_id,
            func.lower(GroupStock.stock_code) == stock_code.lower()
        )
    )
    if stock_result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="股票已在分组中")

    group_stock = GroupStock(group_id=group_id, stock_code=stock_code)
    db.add(group_stock)
    await db.commit()

    return Response(message="添加成功")


@router.delete("/{group_id}/stock/{stock_code}", response_model=Response)
async def remove_stock_from_group(
    group_id: int,
    stock_code: str,
    db: AsyncSession = Depends(get_db)
):
    """从分组移除股票"""
    stock_code = normalize_stock_code(stock_code)
    if not stock_code:
        raise HTTPException(status_code=400, detail="股票代码不能为空")

    result = await db.execute(
        select(GroupStock).where(
            GroupStock.group_id == group_id,
            func.lower(GroupStock.stock_code) == stock_code.lower()
        )
    )
    group_stock = result.scalar_one_or_none()

    if not group_stock:
        raise HTTPException(status_code=404, detail="股票不在分组中")

    await db.delete(group_stock)
    await db.commit()

    return Response(message="移除成功")


# ============ 分组排序 ============

@router.put("/{group_id}/sort", response_model=Response)
async def update_group_sort(
    group_id: int,
    new_sort: int,
    db: AsyncSession = Depends(get_db)
):
    """更新分组排序"""
    result = await db.execute(select(Group).where(Group.id == group_id))
    group = result.scalar_one_or_none()

    if not group:
        raise HTTPException(status_code=404, detail="分组不存在")

    old_sort = group.sort_order

    # 更新其他分组的排序
    if new_sort > old_sort:
        # 向下移动: old_sort < x <= new_sort 的分组排序减1
        await db.execute(
            Group.__table__.update()
            .where(Group.sort_order > old_sort, Group.sort_order <= new_sort)
            .values(sort_order=Group.sort_order - 1)
        )
    elif new_sort < old_sort:
        # 向上移动: new_sort <= x < old_sort 的分组排序加1
        await db.execute(
            Group.__table__.update()
            .where(Group.sort_order >= new_sort, Group.sort_order < old_sort)
            .values(sort_order=Group.sort_order + 1)
        )

    group.sort_order = new_sort
    await db.commit()

    return Response(message="排序成功")


@router.post("/init-sort", response_model=Response)
async def initialize_group_sort(db: AsyncSession = Depends(get_db)):
    """初始化分组排序"""
    # 获取所有分组
    result = await db.execute(select(Group).order_by(Group.id))
    groups = result.scalars().all()

    # 按ID顺序重新分配排序
    for idx, group in enumerate(groups):
        group.sort_order = idx

    await db.commit()

    return Response(message=f"初始化排序成功，共 {len(groups)} 个分组")
