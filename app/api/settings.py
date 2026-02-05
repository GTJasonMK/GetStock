# Settings API
"""
配置管理API路由
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from pydantic import BaseModel

from app.database import get_db
from app.models.settings import AIConfig
from app.config import VERSION, VERSION_COMMIT, OFFICIAL_STATEMENT
from app.utils.helpers import normalize_stock_code
from app.schemas.settings import (
    SettingsResponse,
    SettingsUpdate,
    SettingsWithAIConfigs,
    AIConfigCreate,
    AIConfigUpdate,
    AIConfigResponse,
    ExportData,
    ImportData,
)
from app.schemas.common import Response

router = APIRouter()


# ============ Version Info ============

class VersionInfo(BaseModel):
    """版本信息"""
    version: str
    content: str
    official_statement: str


@router.get("/version", response_model=Response[VersionInfo])
async def get_version_info():
    """获取版本信息"""
    return Response(data=VersionInfo(
        version=VERSION,
        content=VERSION_COMMIT,
        official_statement=OFFICIAL_STATEMENT,
    ))


# ============ Settings API ============

@router.get("", response_model=Response[SettingsWithAIConfigs])
async def get_settings(db: AsyncSession = Depends(get_db)):
    """获取系统配置(包含AI配置)"""
    from app.services.settings_service import get_settings_singleton

    # 获取或创建 Settings（单例收敛）
    settings = await get_settings_singleton(db, create=True)
    await db.commit()
    await db.refresh(settings)

    # 获取所有AI配置
    ai_result = await db.execute(select(AIConfig).order_by(AIConfig.id))
    ai_configs = ai_result.scalars().all()

    # 构建响应
    settings_dict = {
        "id": settings.id,
        "created_at": settings.created_at,
        "updated_at": settings.updated_at,
        "local_stock_codes": settings.local_stock_codes,
        "refresh_interval": settings.refresh_interval,
        "alert_frequency": settings.alert_frequency,
        "alert_window_duration": settings.alert_window_duration,
        "browser_path": settings.browser_path,
        "summary_prompt": settings.summary_prompt,
        "question_prompt": settings.question_prompt,
        "open_alert": settings.open_alert,
        "tushare_token": settings.tushare_token,
        "language": settings.language,
        "version_check": settings.version_check,
        "ai_configs": [AIConfigResponse.model_validate(c) for c in ai_configs],
    }

    return Response(data=SettingsWithAIConfigs(**settings_dict))


@router.put("", response_model=Response[SettingsResponse])
async def update_settings(
    data: SettingsUpdate,
    db: AsyncSession = Depends(get_db)
):
    """更新系统配置"""
    from app.services.settings_service import get_settings_singleton

    settings = await get_settings_singleton(db, create=True)

    # 更新非空字段
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(settings, key, value)

    await db.commit()
    await db.refresh(settings)

    return Response(data=SettingsResponse.model_validate(settings))


# ============ AI Config API ============

@router.get("/ai-configs", response_model=Response[List[AIConfigResponse]])
async def get_ai_configs(db: AsyncSession = Depends(get_db)):
    """获取所有AI配置"""
    result = await db.execute(select(AIConfig).order_by(AIConfig.id))
    configs = result.scalars().all()
    return Response(data=[AIConfigResponse.model_validate(c) for c in configs])


@router.post("/ai-configs", response_model=Response[AIConfigResponse])
async def create_ai_config(
    data: AIConfigCreate,
    db: AsyncSession = Depends(get_db)
):
    """创建AI配置"""
    config = AIConfig(**data.model_dump())
    db.add(config)
    await db.commit()
    await db.refresh(config)
    return Response(data=AIConfigResponse.model_validate(config))


# 批量更新路由必须放在动态路由 /{config_id} 之前，避免被遮蔽
@router.put("/ai-configs/batch", response_model=Response[List[AIConfigResponse]])
async def batch_update_ai_configs(
    configs: List[AIConfigResponse],
    db: AsyncSession = Depends(get_db)
):
    """批量更新AI配置"""
    result_configs = []

    for config_data in configs:
        if config_data.id:
            # 更新已有配置
            result = await db.execute(select(AIConfig).where(AIConfig.id == config_data.id))
            config = result.scalar_one_or_none()
            if config:
                for key, value in config_data.model_dump(exclude={"id", "created_at", "updated_at"}).items():
                    setattr(config, key, value)
                result_configs.append(config)
        else:
            # 创建新配置
            config = AIConfig(**config_data.model_dump(exclude={"id", "created_at", "updated_at"}))
            db.add(config)
            result_configs.append(config)

    await db.commit()

    # 刷新所有配置
    for config in result_configs:
        await db.refresh(config)

    return Response(data=[AIConfigResponse.model_validate(c) for c in result_configs])


@router.put("/ai-configs/{config_id}", response_model=Response[AIConfigResponse])
async def update_ai_config(
    config_id: int,
    data: AIConfigUpdate,
    db: AsyncSession = Depends(get_db)
):
    """更新AI配置"""
    result = await db.execute(select(AIConfig).where(AIConfig.id == config_id))
    config = result.scalar_one_or_none()

    if not config:
        raise HTTPException(status_code=404, detail="AI配置不存在")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(config, key, value)

    await db.commit()
    await db.refresh(config)
    return Response(data=AIConfigResponse.model_validate(config))


@router.delete("/ai-configs/{config_id}", response_model=Response)
async def delete_ai_config(
    config_id: int,
    db: AsyncSession = Depends(get_db)
):
    """删除AI配置"""
    result = await db.execute(select(AIConfig).where(AIConfig.id == config_id))
    config = result.scalar_one_or_none()

    if not config:
        raise HTTPException(status_code=404, detail="AI配置不存在")

    await db.delete(config)
    await db.commit()
    return Response(message="删除成功")


# ============ Export/Import API ============

@router.post("/export", response_model=Response[ExportData])
async def export_config(db: AsyncSession = Depends(get_db)):
    """导出配置"""
    # 获取Settings
    from app.services.settings_service import get_settings_singleton

    settings = await get_settings_singleton(db, create=False)

    # 获取AI配置
    ai_result = await db.execute(select(AIConfig))
    ai_configs = ai_result.scalars().all()

    # 获取自选股代码
    from app.models.stock import FollowedStock
    stock_result = await db.execute(select(FollowedStock.stock_code))
    followed_stocks = [row[0] for row in stock_result.all()]

    # 获取分组
    from app.models.stock import Group, GroupStock
    group_result = await db.execute(select(Group))
    groups = []
    for group in group_result.scalars().all():
        stock_result = await db.execute(
            select(GroupStock.stock_code).where(GroupStock.group_id == group.id)
        )
        stocks = [row[0] for row in stock_result.all()]
        groups.append({
            "name": group.name,
            "description": group.description,
            "stocks": stocks,
        })

    # 使用 from_attributes=True 将ORM对象转换为Pydantic模型
    from app.schemas.settings import SettingsBase, AIConfigBase

    settings_data = SettingsBase.model_validate(settings, from_attributes=True) if settings else SettingsBase()
    ai_configs_data = [AIConfigBase.model_validate(c, from_attributes=True) for c in ai_configs]

    export_data = ExportData(
        settings=settings_data,
        ai_configs=ai_configs_data,
        followed_stocks=followed_stocks,
        groups=groups,
    )

    return Response(data=export_data)


@router.post("/import", response_model=Response)
async def import_config(
    data: ImportData,
    db: AsyncSession = Depends(get_db)
):
    """导入配置"""
    # 导入Settings
    if data.settings:
        from app.services.settings_service import get_settings_singleton

        settings = await get_settings_singleton(db, create=True)

        for key, value in data.settings.model_dump().items():
            if value is not None:
                setattr(settings, key, value)

    # 导入AI配置
    if data.ai_configs:
        for config_data in data.ai_configs:
            config = AIConfig(**config_data.model_dump())
            db.add(config)

    # 导入自选股
    if data.followed_stocks:
        from app.models.stock import FollowedStock
        normalized_codes = [normalize_stock_code(c) for c in (data.followed_stocks or [])]
        normalized_codes = [c for c in normalized_codes if c]

        # 用 lower 去重，避免 SH600000 / sh600000 重复写入
        unique_codes = []
        seen_lower = set()
        for code in normalized_codes:
            lower = code.lower()
            if lower in seen_lower:
                continue
            seen_lower.add(lower)
            unique_codes.append(code)

        # 批量读取已有自选股（大小写不敏感），导入保持幂等
        existing_result = await db.execute(select(FollowedStock.stock_code))
        existing_lower = {(row[0] or "").lower() for row in existing_result.all()}

        for stock_code in unique_codes:
            if stock_code.lower() in existing_lower:
                continue
            stock = FollowedStock(stock_code=stock_code)
            db.add(stock)

    # 导入分组
    if data.groups:
        from app.models.stock import Group, GroupStock
        for group_data in data.groups:
            name = (group_data.get("name", "") or "").strip()
            if not name:
                continue

            description = group_data.get("description", "")

            # 幂等：同名分组存在则复用，不存在则创建
            group_result = await db.execute(select(Group).where(Group.name == name))
            group = group_result.scalar_one_or_none()
            if not group:
                group = Group(name=name, description=description)
                db.add(group)
                await db.flush()  # 获取ID
            else:
                # 导入时允许更新描述（空值也按导入值覆盖，便于“以导入为准”）
                group.description = description

            stock_codes = [normalize_stock_code(c) for c in (group_data.get("stocks", []) or [])]
            stock_codes = [c for c in stock_codes if c]

            # 组内按 lower 去重，保持导入幂等（GroupStock 无唯一约束）
            stock_codes_unique = []
            seen_stock_lower = set()
            for code in stock_codes:
                lower = code.lower()
                if lower in seen_stock_lower:
                    continue
                seen_stock_lower.add(lower)
                stock_codes_unique.append(code)

            # 批量读取已有股票，避免重复插入
            existing_stock_result = await db.execute(
                select(GroupStock.stock_code).where(GroupStock.group_id == group.id)
            )
            existing_stock_lower = {(row[0] or "").lower() for row in existing_stock_result.all()}

            for stock_code in stock_codes_unique:
                if stock_code.lower() in existing_stock_lower:
                    continue
                db.add(GroupStock(group_id=group.id, stock_code=stock_code))
                existing_stock_lower.add(stock_code.lower())

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=400, detail="导入失败：存在重复的分组名称或股票代码冲突")

    return Response(message="导入成功")


# ============ 系统配置聚合API ============

class DataSourceConfigItem(BaseModel):
    """数据源配置项"""
    source_name: str
    enabled: bool
    priority: int
    failure_threshold: int
    cooldown_seconds: int

class SearchEngineConfigItem(BaseModel):
    """搜索引擎配置项"""
    id: int
    engine: str
    enabled: bool
    weight: int
    daily_limit: int | None = None

class TechnicalParamsResponse(BaseModel):
    """技术分析参数"""
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    rsi_periods: List[int] = [6, 12, 24]
    trend_ma_periods: List[int] = [5, 10, 20, 60]

class SystemConfigResponse(BaseModel):
    """系统配置聚合响应"""
    datasources: List[DataSourceConfigItem]
    search_engines: List[SearchEngineConfigItem]
    technical_params: TechnicalParamsResponse


@router.get("/system", response_model=Response[SystemConfigResponse])
async def get_system_config(db: AsyncSession = Depends(get_db)):
    """获取系统配置聚合"""
    from app.models.settings import DataSourceConfig, SearchEngineConfig

    # 获取数据源配置
    ds_result = await db.execute(
        select(DataSourceConfig).order_by(DataSourceConfig.priority)
    )
    ds_configs = ds_result.scalars().all()

    # 如果没有配置，返回默认值
    ds_items = []
    if ds_configs:
        ds_items = [
            DataSourceConfigItem(
                source_name=c.source_name,
                enabled=c.enabled,
                priority=c.priority,
                failure_threshold=c.failure_threshold,
                cooldown_seconds=c.cooldown_seconds,
            )
            for c in ds_configs
        ]
    else:
        # 默认数据源
        defaults = [
            ("sina", 0), ("eastmoney", 1), ("tencent", 2), ("tushare", 3)
        ]
        ds_items = [
            DataSourceConfigItem(
                source_name=name,
                enabled=True,
                priority=priority,
                failure_threshold=3,
                cooldown_seconds=300,
            )
            for name, priority in defaults
        ]

    # 获取搜索引擎配置
    se_result = await db.execute(select(SearchEngineConfig))
    se_configs = se_result.scalars().all()

    se_items = [
        SearchEngineConfigItem(
            id=c.id,
            engine=c.engine,
            enabled=c.enabled,
            weight=c.weight,
            daily_limit=c.daily_limit,
        )
        for c in se_configs
    ]

    # 技术分析参数 (目前使用默认值)
    technical_params = TechnicalParamsResponse()

    return Response(data=SystemConfigResponse(
        datasources=ds_items,
        search_engines=se_items,
        technical_params=technical_params,
    ))


@router.get("/datasources", response_model=Response[List[DataSourceConfigItem]])
async def get_datasource_configs(db: AsyncSession = Depends(get_db)):
    """获取数据源配置"""
    from app.models.settings import DataSourceConfig

    result = await db.execute(
        select(DataSourceConfig).order_by(DataSourceConfig.priority)
    )
    configs = result.scalars().all()

    if not configs:
        # 返回默认配置
        defaults = [
            ("sina", 0), ("eastmoney", 1), ("tencent", 2), ("tushare", 3)
        ]
        return Response(data=[
            DataSourceConfigItem(
                source_name=name,
                enabled=True,
                priority=priority,
                failure_threshold=3,
                cooldown_seconds=300,
            )
            for name, priority in defaults
        ])

    return Response(data=[
        DataSourceConfigItem(
            source_name=c.source_name,
            enabled=c.enabled,
            priority=c.priority,
            failure_threshold=c.failure_threshold,
            cooldown_seconds=c.cooldown_seconds,
        )
        for c in configs
    ])


@router.get("/search-engines", response_model=Response[List[SearchEngineConfigItem]])
async def get_search_engine_configs(db: AsyncSession = Depends(get_db)):
    """获取搜索引擎配置"""
    from app.models.settings import SearchEngineConfig

    result = await db.execute(select(SearchEngineConfig))
    configs = result.scalars().all()

    return Response(data=[
        SearchEngineConfigItem(
            id=c.id,
            engine=c.engine,
            enabled=c.enabled,
            weight=c.weight,
            daily_limit=c.daily_limit,
        )
        for c in configs
    ])


@router.get("/technical", response_model=Response[TechnicalParamsResponse])
async def get_technical_params():
    """获取技术分析参数"""
    return Response(data=TechnicalParamsResponse())

