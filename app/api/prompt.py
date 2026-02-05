# Prompt API
"""
Prompt模板管理API
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from datetime import datetime

from app.database import get_db
from app.models.ai import PromptTemplate
from app.schemas.common import Response

router = APIRouter()


# ============ Pydantic Models ============

class PromptTemplateCreate(BaseModel):
    """创建Prompt模板"""
    name: str
    template_type: str = "custom"
    content: str
    description: str = ""
    is_enabled: bool = True
    sort_order: int = 0


class PromptTemplateUpdate(BaseModel):
    """更新Prompt模板"""
    name: Optional[str] = None
    template_type: Optional[str] = None
    content: Optional[str] = None
    description: Optional[str] = None
    is_enabled: Optional[bool] = None
    sort_order: Optional[int] = None


class PromptTemplateResponse(BaseModel):
    """Prompt模板响应"""
    id: int
    name: str
    template_type: str
    content: str
    description: str
    is_system: bool
    is_enabled: bool
    sort_order: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PromptTemplateListResponse(BaseModel):
    """Prompt模板列表响应"""
    items: List[PromptTemplateResponse]
    total: int


# ============ API Endpoints ============

@router.get("", response_model=Response[PromptTemplateListResponse])
async def get_prompts(
    template_type: Optional[str] = Query(None, description="模板类型"),
    is_enabled: Optional[bool] = Query(None, description="是否启用"),
    db: AsyncSession = Depends(get_db)
):
    """获取Prompt模板列表"""
    query = select(PromptTemplate).order_by(PromptTemplate.sort_order, PromptTemplate.id)

    if template_type:
        query = query.where(PromptTemplate.template_type == template_type)
    if is_enabled is not None:
        query = query.where(PromptTemplate.is_enabled == is_enabled)

    result = await db.execute(query)
    items = result.scalars().all()

    return Response(data=PromptTemplateListResponse(
        items=[PromptTemplateResponse.model_validate(item) for item in items],
        total=len(items)
    ))


@router.get("/{prompt_id}", response_model=Response[PromptTemplateResponse])
async def get_prompt(
    prompt_id: int,
    db: AsyncSession = Depends(get_db)
):
    """获取单个Prompt模板"""
    result = await db.execute(
        select(PromptTemplate).where(PromptTemplate.id == prompt_id)
    )
    prompt = result.scalar_one_or_none()

    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt模板不存在")

    return Response(data=PromptTemplateResponse.model_validate(prompt))


@router.get("/name/{name}", response_model=Response[PromptTemplateResponse])
async def get_prompt_by_name(
    name: str,
    db: AsyncSession = Depends(get_db)
):
    """根据名称获取Prompt模板"""
    result = await db.execute(
        select(PromptTemplate).where(PromptTemplate.name == name)
    )
    prompt = result.scalar_one_or_none()

    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt模板不存在")

    return Response(data=PromptTemplateResponse.model_validate(prompt))


@router.post("", response_model=Response[PromptTemplateResponse])
async def create_prompt(
    data: PromptTemplateCreate,
    db: AsyncSession = Depends(get_db)
):
    """创建Prompt模板"""
    # 检查名称是否重复
    result = await db.execute(
        select(PromptTemplate).where(PromptTemplate.name == data.name)
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="模板名称已存在")

    prompt = PromptTemplate(**data.model_dump())
    db.add(prompt)
    await db.commit()
    await db.refresh(prompt)

    return Response(data=PromptTemplateResponse.model_validate(prompt))


@router.put("/{prompt_id}", response_model=Response[PromptTemplateResponse])
async def update_prompt(
    prompt_id: int,
    data: PromptTemplateUpdate,
    db: AsyncSession = Depends(get_db)
):
    """更新Prompt模板"""
    result = await db.execute(
        select(PromptTemplate).where(PromptTemplate.id == prompt_id)
    )
    prompt = result.scalar_one_or_none()

    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt模板不存在")

    # 系统模板不允许修改名称和类型
    if prompt.is_system:
        if data.name is not None and data.name != prompt.name:
            raise HTTPException(status_code=400, detail="系统模板不允许修改名称")
        if data.template_type is not None and data.template_type != prompt.template_type:
            raise HTTPException(status_code=400, detail="系统模板不允许修改类型")

    # 更新字段
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(prompt, key, value)

    await db.commit()
    await db.refresh(prompt)

    return Response(data=PromptTemplateResponse.model_validate(prompt))


@router.delete("/{prompt_id}", response_model=Response)
async def delete_prompt(
    prompt_id: int,
    db: AsyncSession = Depends(get_db)
):
    """删除Prompt模板"""
    result = await db.execute(
        select(PromptTemplate).where(PromptTemplate.id == prompt_id)
    )
    prompt = result.scalar_one_or_none()

    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt模板不存在")

    if prompt.is_system:
        raise HTTPException(status_code=400, detail="系统模板不允许删除")

    await db.delete(prompt)
    await db.commit()

    return Response(message="删除成功")


@router.post("/init-defaults", response_model=Response)
async def init_default_prompts(
    db: AsyncSession = Depends(get_db)
):
    """初始化默认Prompt模板"""
    default_prompts = [
        {
            "name": "stock_summary",
            "template_type": "summary",
            "content": """请分析以下股票信息并生成摘要:
股票代码: {stock_code}
股票名称: {stock_name}
当前价格: {current_price}
涨跌幅: {change_percent}%
成交量: {volume}
成交额: {amount}

请从以下几个方面进行分析:
1. 当前走势分析
2. 技术面分析
3. 资金流向分析
4. 投资建议

请用简洁专业的语言回答。""",
            "description": "股票摘要分析模板",
            "is_system": True,
            "sort_order": 1,
        },
        {
            "name": "stock_question",
            "template_type": "question",
            "content": """你是一个专业的股票分析师。用户正在询问关于股票 {stock_name}({stock_code}) 的问题。

请根据你的专业知识回答以下问题:
{question}

请确保回答准确、专业，并给出具体的分析依据。""",
            "description": "股票问答模板",
            "is_system": True,
            "sort_order": 2,
        },
        {
            "name": "stock_analysis",
            "template_type": "analysis",
            "content": """请对以下股票进行深度分析:

## 基本信息
- 股票代码: {stock_code}
- 股票名称: {stock_name}
- 所属行业: {industry}
- 所属概念: {concepts}

## 市场数据
- 当前价格: {current_price}
- 涨跌幅: {change_percent}%
- 成交量: {volume}
- 换手率: {turnover_rate}%
- 市盈率: {pe_ratio}
- 市净率: {pb_ratio}

## K线数据
{kline_data}

请从以下几个维度进行分析:
1. **基本面分析**: 分析公司基本面情况
2. **技术面分析**: 分析K线形态和技术指标
3. **资金面分析**: 分析资金流向和主力动向
4. **风险提示**: 指出可能的风险因素
5. **投资建议**: 给出具体的投资建议和目标价位

请确保分析专业、客观、有理有据。""",
            "description": "股票深度分析模板",
            "is_system": True,
            "sort_order": 3,
        },
        {
            "name": "market_summary",
            "template_type": "summary",
            "content": """请对今日市场行情进行总结:

## 大盘指数
{index_data}

## 行业板块
{industry_data}

## 热门概念
{concept_data}

## 资金流向
{money_flow_data}

请从以下几个方面进行分析:
1. 今日大盘走势分析
2. 热点板块分析
3. 资金面分析
4. 明日预判

请用简洁专业的语言回答。""",
            "description": "市场总结模板",
            "is_system": True,
            "sort_order": 4,
        },
    ]

    created_count = 0
    for prompt_data in default_prompts:
        result = await db.execute(
            select(PromptTemplate).where(PromptTemplate.name == prompt_data["name"])
        )
        if not result.scalar_one_or_none():
            prompt = PromptTemplate(**prompt_data)
            db.add(prompt)
            created_count += 1

    await db.commit()

    return Response(message=f"初始化完成，创建了 {created_count} 个默认模板")
