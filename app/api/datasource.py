# 数据源管理API
"""
数据源管理相关的API端点
"""

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.settings import DataSourceConfig
from app.schemas.common import Response
from app.schemas.technical import (
    DataSourceStatus,
    DataSourceConfigRequest,
    DataSourceConfigResponse,
    CircuitStateEnum,
)
from app.datasources.manager import get_datasource_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/datasources", tags=["数据源管理"])


@router.get("", response_model=Response[List[DataSourceStatus]])
async def get_all_datasources(
    db: AsyncSession = Depends(get_db),
):
    """获取所有数据源状态"""
    manager = get_datasource_manager()
    await manager.initialize(db)

    statuses = manager.get_all_status()

    return Response(data=[
        DataSourceStatus(
            name=s["name"],
            state=CircuitStateEnum(s["state"]),
            failure_count=s["failure_count"],
            failure_threshold=s["failure_threshold"],
            cooldown_seconds=s["cooldown_seconds"],
            last_failure_time=s["last_failure_time"],
            priority=s["priority"],
        )
        for s in statuses
    ])


@router.get("/configs", response_model=Response[List[DataSourceConfigResponse]])
async def get_all_configs(
    db: AsyncSession = Depends(get_db),
):
    """获取所有数据源配置"""
    result = await db.execute(
        select(DataSourceConfig).order_by(DataSourceConfig.priority)
    )
    configs = result.scalars().all()

    return Response(data=[
        DataSourceConfigResponse(
            id=c.id,
            source_name=c.source_name,
            enabled=c.enabled,
            priority=c.priority,
            failure_threshold=c.failure_threshold,
            cooldown_seconds=c.cooldown_seconds,
            api_key=c.api_key if c.api_key else None,
        )
        for c in configs
    ])


@router.get("/{name}", response_model=Response[DataSourceStatus])
async def get_datasource(
    name: str,
    db: AsyncSession = Depends(get_db),
):
    """获取指定数据源状态"""
    manager = get_datasource_manager()
    await manager.initialize(db)

    status = manager.get_status(name)
    if not status:
        raise HTTPException(status_code=404, detail=f"数据源 {name} 不存在")

    # 获取优先级
    all_status = manager.get_all_status()
    priority = 0
    for s in all_status:
        if s["name"] == name:
            priority = s["priority"]
            break

    return Response(data=DataSourceStatus(
        name=status["name"],
        state=CircuitStateEnum(status["state"]),
        failure_count=status["failure_count"],
        failure_threshold=status["failure_threshold"],
        cooldown_seconds=status["cooldown_seconds"],
        last_failure_time=status["last_failure_time"],
        priority=priority,
    ))


@router.put("/{name}", response_model=Response[DataSourceConfigResponse])
async def update_datasource(
    name: str,
    request: DataSourceConfigRequest,
    db: AsyncSession = Depends(get_db),
):
    """更新数据源配置"""
    # 查找或创建配置
    result = await db.execute(
        select(DataSourceConfig).where(DataSourceConfig.source_name == name)
    )
    config = result.scalar_one_or_none()

    if not config:
        # 创建新配置
        config = DataSourceConfig(
            source_name=name,
            enabled=request.enabled if request.enabled is not None else True,
            priority=request.priority if request.priority is not None else 0,
            failure_threshold=request.failure_threshold if request.failure_threshold is not None else 3,
            cooldown_seconds=request.cooldown_seconds if request.cooldown_seconds is not None else 300,
            api_key=request.api_key or "",
        )
        db.add(config)
    else:
        # 更新现有配置
        if request.enabled is not None:
            config.enabled = request.enabled
        if request.priority is not None:
            config.priority = request.priority
        if request.failure_threshold is not None:
            config.failure_threshold = request.failure_threshold
        if request.cooldown_seconds is not None:
            config.cooldown_seconds = request.cooldown_seconds
        if request.api_key is not None:
            config.api_key = request.api_key

    await db.commit()
    await db.refresh(config)

    # 刷新内存中的数据源配置，确保后续故障转移按最新配置执行
    manager = get_datasource_manager()
    await manager.initialize(db)

    return Response(data=DataSourceConfigResponse(
        id=config.id,
        source_name=config.source_name,
        enabled=config.enabled,
        priority=config.priority,
        failure_threshold=config.failure_threshold,
        cooldown_seconds=config.cooldown_seconds,
        api_key=config.api_key if config.api_key else None,
    ))


@router.post("/{name}/reset", response_model=Response)
async def reset_datasource(
    name: str,
    db: AsyncSession = Depends(get_db),
):
    """重置数据源熔断状态"""
    manager = get_datasource_manager()
    await manager.initialize(db)

    if not manager.reset_breaker(name):
        raise HTTPException(status_code=404, detail=f"数据源 {name} 不存在")

    return Response(message=f"数据源 {name} 熔断状态已重置")


@router.post("/priority", response_model=Response)
async def set_priority(
    priority: List[str],
    db: AsyncSession = Depends(get_db),
):
    """设置数据源优先级顺序"""
    manager = get_datasource_manager()
    await manager.initialize(db)

    # 更新数据库中的优先级
    for i, name in enumerate(priority):
        result = await db.execute(
            select(DataSourceConfig).where(DataSourceConfig.source_name == name)
        )
        config = result.scalar_one_or_none()

        if config:
            config.priority = i
        else:
            # 创建新配置
            new_config = DataSourceConfig(
                source_name=name,
                priority=i,
            )
            db.add(new_config)

    await db.commit()

    # 更新内存中的数据源配置（以 DB enabled/priority 为准），避免短暂不一致
    await manager.initialize(db)

    return Response(message="优先级已更新")
