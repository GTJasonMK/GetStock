# API 主路由
"""
所有 API 路由的汇总注册
"""

from fastapi import APIRouter

from app.api import settings, stock, group, news, market, ai, fund, prompt, tasks
from app.api import technical, datasource, cache
from app.api import agent_knowledge

api_router = APIRouter()

# 注册各模块路由
api_router.include_router(settings.router, prefix="/settings", tags=["配置管理"])
api_router.include_router(stock.router, prefix="/stock", tags=["股票数据"])
api_router.include_router(group.router, prefix="/group", tags=["分组管理"])
api_router.include_router(news.router, prefix="/news", tags=["资讯"])
api_router.include_router(market.router, prefix="/market", tags=["市场数据"])
api_router.include_router(ai.router, prefix="/ai", tags=["AI分析"])
api_router.include_router(fund.router, prefix="/fund", tags=["基金数据"])
api_router.include_router(prompt.router, prefix="/prompt", tags=["Prompt模板"])
api_router.include_router(tasks.router, prefix="/tasks", tags=["定时任务"])
api_router.include_router(technical.router, tags=["技术分析"])
api_router.include_router(datasource.router, tags=["数据源管理"])
api_router.include_router(cache.router, tags=["缓存管理"])
api_router.include_router(agent_knowledge.router, prefix="/agent/knowledge", tags=["Agent知识库"])
