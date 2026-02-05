# Tasks API
"""
定时任务管理API
"""

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.tasks.scheduler import (
    get_jobs,
    get_job,
    remove_job,
    pause_job,
    resume_job,
    run_job_now,
    schedule_ai_analysis,
)
from app.schemas.common import Response

router = APIRouter()


# ============ Pydantic Models ============

class JobInfo(BaseModel):
    """任务信息"""
    id: str
    name: str
    next_run_time: Optional[str]
    trigger: str
    pending: bool


class JobListResponse(BaseModel):
    """任务列表响应"""
    items: List[JobInfo]
    total: int


class CreateAIAnalysisJobRequest(BaseModel):
    """创建AI分析任务请求"""
    stock_code: str
    cron_expression: str  # 例如: "0 15 * * 1-5" (每个交易日15:00)
    prompt_template: Optional[str] = None


# ============ API Endpoints ============

@router.get("", response_model=Response[JobListResponse])
async def list_jobs():
    """获取所有定时任务"""
    jobs = get_jobs()
    return Response(data=JobListResponse(
        items=[JobInfo(**job) for job in jobs],
        total=len(jobs)
    ))


@router.get("/{job_id}", response_model=Response[JobInfo])
async def get_job_info(job_id: str):
    """获取指定任务信息"""
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")
    return Response(data=JobInfo(**job))


@router.delete("/{job_id}", response_model=Response)
async def delete_job(job_id: str):
    """删除定时任务"""
    success = remove_job(job_id)
    if not success:
        raise HTTPException(status_code=404, detail="任务不存在或删除失败")
    return Response(message="删除成功")


@router.post("/{job_id}/pause", response_model=Response)
async def pause_job_endpoint(job_id: str):
    """暂停定时任务"""
    success = pause_job(job_id)
    if not success:
        raise HTTPException(status_code=404, detail="任务不存在或暂停失败")
    return Response(message="暂停成功")


@router.post("/{job_id}/resume", response_model=Response)
async def resume_job_endpoint(job_id: str):
    """恢复定时任务"""
    success = resume_job(job_id)
    if not success:
        raise HTTPException(status_code=404, detail="任务不存在或恢复失败")
    return Response(message="恢复成功")


@router.post("/{job_id}/run", response_model=Response)
async def run_job_now_endpoint(job_id: str):
    """立即执行任务"""
    success = run_job_now(job_id)
    if not success:
        raise HTTPException(status_code=404, detail="任务不存在或执行失败")
    return Response(message="已触发执行")


@router.post("/ai-analysis", response_model=Response)
async def create_ai_analysis_job(request: CreateAIAnalysisJobRequest):
    """创建AI分析定时任务"""
    job_id = schedule_ai_analysis(
        stock_code=request.stock_code,
        cron_expression=request.cron_expression,
        prompt_template=request.prompt_template
    )
    if not job_id:
        raise HTTPException(status_code=400, detail="创建任务失败，请检查cron表达式格式")
    return Response(message=f"创建成功，任务ID: {job_id}")
