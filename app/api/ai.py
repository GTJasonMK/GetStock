# AI API
"""
AI分析API路由 - 完整实现
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from datetime import datetime
import json
import httpx

from app.database import get_db
from app.models.ai import AIResponseResult, AIRecommendStock
from app.models.ai_session import AISession, AISessionMessage
from app.utils.helpers import normalize_stock_code
from app.schemas.ai import (
    ChatRequest,
    ChatResponse,
    StockAnalysisRequest,
    StockAnalysisResponse,
    AIHistoryItem,
    AIHistoryResponse,
    AgentResponse,
    AISessionInfo,
    AISessionMessageItem,
    AISessionDetailResponse,
    AISessionListResponse,
)
from app.schemas.common import Response

router = APIRouter()


def _map_ai_error(e: Exception) -> HTTPException:
    """将 AI/LLM 侧异常映射为更可读的 HTTPException（避免前端只看到 500）。"""
    if isinstance(e, HTTPException):
        return e

    if isinstance(e, ValueError):
        return HTTPException(status_code=400, detail=str(e)[:500] or "请求参数或配置错误")

    if isinstance(e, httpx.HTTPStatusError):
        status = int(getattr(e.response, "status_code", 0) or 0)
        detail = f"LLM 服务返回错误: HTTP {status}"
        try:
            payload = e.response.json()
            # 兼容 OpenAI 兼容格式：{"error":{"message":"..."}} 或 {"message":"..."}
            msg = ""
            if isinstance(payload, dict):
                if isinstance(payload.get("message"), str):
                    msg = payload.get("message") or ""
                elif isinstance(payload.get("error"), dict) and isinstance(payload["error"].get("message"), str):
                    msg = payload["error"].get("message") or ""
            if msg:
                detail = f"{detail} - {msg}"
        except Exception:
            pass
        return HTTPException(status_code=502, detail=detail[:500])

    if isinstance(e, httpx.RequestError):
        return HTTPException(status_code=502, detail=f"LLM 网络错误: {type(e).__name__}")

    return HTTPException(status_code=500, detail=str(e)[:500] or "AI 服务内部错误")


# ============ 额外的Pydantic模型 ============

class SummaryRequest(BaseModel):
    """摘要请求"""
    stock_code: str
    stock_name: str
    model_id: Optional[int] = None


class RecommendResponse(BaseModel):
    """推荐股票响应"""
    id: int
    stock_code: str
    stock_name: str
    score: int
    reason: str
    recommend_type: str
    target_price: float
    stop_loss_price: float
    model_name: str
    created_at: datetime

    model_config = {"from_attributes": True}


class SentimentRequest(BaseModel):
    """情感分析请求"""
    text: str
    model_id: Optional[int] = None


class SentimentResponse(BaseModel):
    """情感分析响应"""
    sentiment: str
    score: float
    keywords: List[str]
    summary: str


class NewsSentimentResponse(BaseModel):
    """新闻情感分析响应"""
    overall_sentiment: str
    positive_count: int
    negative_count: int
    neutral_count: int
    news_count: int


@router.post("/chat", response_model=Response[ChatResponse])
async def chat(
    request: ChatRequest,
    db: AsyncSession = Depends(get_db)
):
    """AI对话"""
    from app.services.ai_service import AIService

    service = AIService(db)
    try:
        response = await service.chat(request)
    except Exception as e:
        raise _map_ai_error(e)

    return Response(data=response)


@router.post("/chat/stream")
async def chat_stream(
    request: ChatRequest,
    db: AsyncSession = Depends(get_db)
):
    """AI流式对话 (SSE)"""
    from app.services.ai_service import AIService
    from app.schemas.ai import StreamChunk

    request.stream = True
    service = AIService(db)

    async def generate():
        try:
            async for chunk in service.chat_stream(request):
                yield f"data: {chunk.model_dump_json()}\n\n"
        except Exception as e:
            err = _map_ai_error(e)
            fallback = StreamChunk(content=f"Error: {err.detail}", done=False, model_name="")
            yield f"data: {fallback.model_dump_json()}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


@router.post("/analyze", response_model=Response[StockAnalysisResponse])
async def analyze_stock(
    request: StockAnalysisRequest,
    db: AsyncSession = Depends(get_db)
):
    """分析股票"""
    from app.services.ai_service import AIService

    service = AIService(db)
    try:
        response = await service.analyze_stock(request)
    except Exception as e:
        raise _map_ai_error(e)

    return Response(data=response)

@router.post("/simple", response_model=Response[ChatResponse])
async def simple_agent_chat(
    request: ChatRequest,
    db: AsyncSession = Depends(get_db),
):
    """简化版 Agent：固定数据收集 → 输出结论（不走复杂编排）。"""
    from app.services.ai_service import AIService

    service = AIService(db)
    try:
        response = await service.simple_agent_chat(request)
    except Exception as e:
        raise _map_ai_error(e)

    return Response(data=response)


@router.post("/simple/stream")
async def simple_agent_chat_stream(
    request: ChatRequest,
    db: AsyncSession = Depends(get_db),
):
    """简化版 Agent 流式输出 (SSE)"""
    from app.services.ai_service import AIService
    from app.schemas.ai import StreamChunk

    request.stream = True
    service = AIService(db)

    async def generate():
        try:
            async for chunk in service.simple_agent_chat_stream(request):
                yield f"data: {chunk.model_dump_json()}\n\n"
        except Exception as e:
            err = _map_ai_error(e)
            fallback = StreamChunk(content=f"Error: {err.detail}", done=False, model_name="")
            yield f"data: {fallback.model_dump_json()}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@router.post("/agent", response_model=Response[AgentResponse])
async def agent_chat(
    request: ChatRequest,
    db: AsyncSession = Depends(get_db)
):
    """Agent对话 (ReACT模式)"""
    from app.services.ai_service import AIService

    service = AIService(db)
    try:
        response = await service.agent_chat(request)
    except Exception as e:
        raise _map_ai_error(e)

    return Response(data=response)


@router.post("/agent/stream")
async def agent_chat_stream(
    request: ChatRequest,
    db: AsyncSession = Depends(get_db)
):
    """Agent流式对话 (SSE)"""
    from app.services.ai_service import AIService

    request.stream = True
    service = AIService(db)

    async def generate():
        try:
            async for chunk in service.agent_chat_stream(request):
                yield f"data: {chunk}\n\n"
        except Exception as e:
            err = _map_ai_error(e)
            yield f"data: {json.dumps({'type': 'error', 'message': err.detail}, ensure_ascii=False)}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


# ============ Session API ============

@router.get("/sessions", response_model=Response[AISessionListResponse])
async def list_sessions(
    mode: Optional[str] = Query(None, description="会话模式：chat/agent"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """列出会话（按最近活跃排序）。"""
    query = select(AISession).order_by(AISession.updated_at.desc())
    if mode:
        query = query.where(AISession.mode == mode)

    offset = (page - 1) * page_size
    result = await db.execute(query.offset(offset).limit(page_size))
    items = result.scalars().all()

    count_query = select(func.count(AISession.id))
    if mode:
        count_query = count_query.where(AISession.mode == mode)
    total_result = await db.execute(count_query)
    total = int(total_result.scalar() or 0)

    return Response(
        data=AISessionListResponse(
            items=[
                AISessionInfo(
                    id=s.id,
                    mode=s.mode,
                    title=s.title,
                    stock_code=s.stock_code or "",
                    stock_name=s.stock_name or "",
                    model_name=s.model_name or "",
                    message_count=int(s.message_count or 0),
                    created_at=s.created_at,
                    updated_at=s.updated_at,
                )
                for s in items
            ],
            total=total,
        )
    )


@router.get("/sessions/{session_id}", response_model=Response[AISessionDetailResponse])
async def get_session_detail(
    session_id: str,
    limit: int = Query(200, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
):
    """获取会话详情（含消息）。"""
    sid = (session_id or "").strip()
    if not sid or len(sid) > 64:
        raise HTTPException(status_code=400, detail="session_id 不合法")

    result = await db.execute(select(AISession).where(AISession.id == sid))
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    msg_result = await db.execute(
        select(AISessionMessage)
        .where(AISessionMessage.session_id == sid)
        .order_by(AISessionMessage.id.asc())
        .limit(limit)
    )
    messages = msg_result.scalars().all()

    return Response(
        data=AISessionDetailResponse(
            session=AISessionInfo(
                id=session.id,
                mode=session.mode,
                title=session.title,
                stock_code=session.stock_code or "",
                stock_name=session.stock_name or "",
                model_name=session.model_name or "",
                message_count=int(session.message_count or 0),
                created_at=session.created_at,
                updated_at=session.updated_at,
            ),
            messages=[
                AISessionMessageItem(
                    id=m.id,
                    role=m.role,
                    content=m.content,
                    created_at=m.created_at,
                )
                for m in messages
            ],
        )
    )


@router.delete("/sessions/{session_id}", response_model=Response)
async def delete_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    """删除会话（含消息）。"""
    sid = (session_id or "").strip()
    if not sid or len(sid) > 64:
        raise HTTPException(status_code=400, detail="session_id 不合法")

    result = await db.execute(select(AISession).where(AISession.id == sid))
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    # 先删消息再删会话，兼容 sqlite 未启用外键约束的情况
    await db.execute(delete(AISessionMessage).where(AISessionMessage.session_id == sid))
    await db.delete(session)
    await db.commit()

    return Response(message="删除成功")


# ============ History API ============

@router.get("/history", response_model=Response[AIHistoryResponse])
async def get_history(
    stock_code: Optional[str] = Query(None),
    analysis_type: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, le=100),
    db: AsyncSession = Depends(get_db)
):
    """获取AI分析历史"""
    query = select(AIResponseResult).order_by(AIResponseResult.created_at.desc())

    if stock_code:
        normalized_code = normalize_stock_code(stock_code)
        query = query.where(func.lower(AIResponseResult.stock_code) == normalized_code.lower())
    if analysis_type:
        query = query.where(AIResponseResult.analysis_type == analysis_type)

    # 分页
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)

    result = await db.execute(query)
    items = result.scalars().all()

    # 获取总数
    count_query = select(func.count(AIResponseResult.id))
    if stock_code:
        normalized_code = normalize_stock_code(stock_code)
        count_query = count_query.where(func.lower(AIResponseResult.stock_code) == normalized_code.lower())
    if analysis_type:
        count_query = count_query.where(AIResponseResult.analysis_type == analysis_type)

    count_result = await db.execute(count_query)
    total = count_result.scalar()

    return Response(data=AIHistoryResponse(
        items=[AIHistoryItem(
            id=item.id,
            stock_code=item.stock_code,
            stock_name=item.stock_name,
            question=item.question,
            response=item.response,
            model_name=item.model_name,
            analysis_type=item.analysis_type,
            created_at=item.created_at,
        ) for item in items],
        total=total,
    ))


@router.delete("/history/{history_id}", response_model=Response)
async def delete_history(
    history_id: int,
    db: AsyncSession = Depends(get_db)
):
    """删除AI分析历史"""
    result = await db.execute(
        select(AIResponseResult).where(AIResponseResult.id == history_id)
    )
    item = result.scalar_one_or_none()

    if not item:
        raise HTTPException(status_code=404, detail="记录不存在")

    await db.delete(item)
    await db.commit()

    return Response(message="删除成功")


@router.delete("/history", response_model=Response)
async def clear_history(
    stock_code: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """清空AI分析历史"""
    query = delete(AIResponseResult)
    if stock_code:
        normalized_code = normalize_stock_code(stock_code)
        query = query.where(func.lower(AIResponseResult.stock_code) == normalized_code.lower())

    await db.execute(query)
    await db.commit()

    return Response(message="清空成功")


# ============ 股票摘要 ============

@router.post("/summary", response_model=Response[str])
async def generate_summary(
    request: SummaryRequest,
    db: AsyncSession = Depends(get_db)
):
    """生成股票摘要"""
    from app.services.ai_service import AIService

    service = AIService(db)
    try:
        summary = await service.generate_stock_summary(
            request.stock_code,
            request.stock_name,
            request.model_id
        )
    except Exception as e:
        raise _map_ai_error(e)

    return Response(data=summary)


# ============ AI推荐 ============

@router.get("/recommendations", response_model=Response[List[RecommendResponse]])
async def get_recommendations(
    limit: int = Query(10, le=50),
    db: AsyncSession = Depends(get_db)
):
    """获取AI推荐股票"""
    from app.services.ai_service import AIService

    service = AIService(db)
    try:
        recommendations = await service.get_ai_recommendations(limit)
    except Exception as e:
        raise _map_ai_error(e)

    return Response(data=[RecommendResponse.model_validate(r) for r in recommendations])


@router.post("/recommendations/generate", response_model=Response[List[RecommendResponse]])
async def generate_recommendations(
    model_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """生成AI推荐股票"""
    from app.services.ai_service import AIService

    service = AIService(db)
    try:
        recommendations = await service.generate_ai_recommendations(model_id)
    except Exception as e:
        raise _map_ai_error(e)

    return Response(data=[RecommendResponse.model_validate(r) for r in recommendations])


# ============ 情感分析 ============

@router.post("/sentiment", response_model=Response[SentimentResponse])
async def analyze_sentiment(
    request: SentimentRequest,
    db: AsyncSession = Depends(get_db)
):
    """分析文本情感"""
    from app.services.ai_service import AIService

    service = AIService(db)
    try:
        result = await service.analyze_sentiment(request.text, request.model_id)
    except Exception as e:
        raise _map_ai_error(e)

    return Response(data=SentimentResponse(**result))


@router.get("/sentiment/news/{stock_code}", response_model=Response[NewsSentimentResponse])
async def analyze_news_sentiment(
    stock_code: str,
    model_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """分析股票相关新闻的情感"""
    from app.services.ai_service import AIService

    service = AIService(db)
    try:
        result = await service.analyze_news_sentiment(stock_code, model_id)
    except Exception as e:
        raise _map_ai_error(e)

    return Response(data=NewsSentimentResponse(**result))


# ============ Share Analysis ============

class ShareAnalysisRequest(BaseModel):
    """分享分析请求"""
    stock_code: str
    stock_name: str
    content: Optional[str] = None


@router.post("/share", response_model=Response[str])
async def share_analysis(
    request: ShareAnalysisRequest,
    db: AsyncSession = Depends(get_db)
):
    """分享股票分析结果"""
    from app.services.ai_service import AIService

    service = AIService(db)
    try:
        share_url = await service.share_analysis(
            request.stock_code,
            request.stock_name,
            request.content
        )
    except Exception as e:
        raise _map_ai_error(e)

    return Response(data=share_url)


# ============ News AI Summary ============

class NewsSummaryRequest(BaseModel):
    """新闻AI总结请求"""
    question: str
    model_id: Optional[int] = None


@router.post("/news-summary", response_model=Response[str])
async def summary_news(
    request: NewsSummaryRequest,
    db: AsyncSession = Depends(get_db)
):
    """AI总结新闻资讯"""
    from app.services.ai_service import AIService

    service = AIService(db)
    try:
        summary = await service.summary_news(request.question, request.model_id)
    except Exception as e:
        raise _map_ai_error(e)

    return Response(data=summary)


@router.post("/news-summary/stream")
async def summary_news_stream(
    request: NewsSummaryRequest,
    db: AsyncSession = Depends(get_db)
):
    """AI总结新闻资讯 (流式)"""
    from app.services.ai_service import AIService

    service = AIService(db)

    async def generate():
        try:
            async for chunk in service.summary_news_stream(request.question, request.model_id):
                yield f"data: {chunk}\n\n"
        except Exception as e:
            err = _map_ai_error(e)
            yield f"data: {json.dumps({'type': 'error', 'message': err.detail}, ensure_ascii=False)}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )
